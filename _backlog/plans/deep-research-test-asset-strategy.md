# Plan: Deep Research 测试资产补充策略

> 类型: 分析 / 设计 | 更新: 2026-07-17
> 触发: `add-deep-research-demo-full-pipeline` change 的 real-mode 集成在端到端暴露了 11 个 bug，当前测试资产（19 个测试，全部基于 fake/mock）一个都没抓到

## 结论先行

当前测试资产的致命缺陷：**所有测试都在 fake 路径上跑，fake 路径跳过整个 worker 执行链（middleware → tools → budget → submit → gate）。** 11 个 bug 里有 9 个是 real 路径独有的——fake 测试根本不可能发现它们。

需要的不是"更多端到端测试"，而是**针对每个集成点的确定性单元测试**——用 FakeModel + 真实 middleware + 真实 policy + 真实 submit validator 跑一次最小工作单元。每次 < 1 秒，CI 日常跑，秒级定位。

## 现状

### 当前测试资产

```
agent/tests/
├── unit/
│   ├── test_demo_core.py                    15 tests   ← fake-only, 检查 import/常量
│   ├── test_bootstrap_bundle.py              ~10 tests  ← unit tests for bootstrap store
│   ├── test_research_runtime_capabilities.py ~20 tests  ← recipe mode switching
│   ├── test_budget_middleware.py             ~10 tests  ← budget violation tests
│   ├── test_node_agent_bridge.py             ~10 tests  ← bridge construction
│   ├── test_critic_factory.py                ~5 tests
│   ├── test_structured_output.py             ~5 tests
│   ├── test_tool_policy.py                   ~5 tests
│   ├── test_policies.py                      ~5 tests
│   └── ...                                   ~30 more
├── integration/
│   ├── test_demo_cli.py                      1 test     ← subprocess, fake demo only
│   ├── test_demo_tui.py                      3 tests    ← Textual pilot, fake recipe
│   ├── test_hitl1_lifecycle.py               ~5 tests   ← mixed fake/real
│   ├── test_bootstrap_lifecycle.py           ~5 tests   ← mixed fake/real
│   └── ...
└── contract/ + viability/ + blocking_io/ + durability/
```

**总量：~200 tests。覆盖率：fake 图拓扑 + 状态迁移 + storage/bundle 基础设施。**

### 覆盖盲区

```
fake 测试覆盖的：
  ✓ 图拓扑 (bootstrap → ... → final_delivery)
  ✓ 状态迁移 (ResearchState 字段、reducer)
  ✓ checkpoint 读写
  ✓ storage/bundle 存储
  ✓ recipe mode switching (fake vs real 标志)
  ✓ 工具名声明 (WAVE0_WORKER_TOOL_NAMES)

fake 测试不覆盖的（= real-mode 11 个 bug 的来源）：
  ✗ ToolPolicyMiddleware._authorize() — 工具 spec 查找
  ✗ BudgetMiddleware.awrap_model_call() — token admission check
  ✗ BudgetMiddleware.awrap_tool_call() — tool call limits
  ✗ Structured output 解析 (parse_plan_output → TopicPlan Pydantic)
  ✗ Submit validation (validate_submission_candidate → Wave0SourceIntakeResult)
  ✗ Gate evaluation with real failure fingerprints (fatigue detection)
  ✗ 工具名与 config.yaml 名的一致性（编译期不检查的字符串）
  ✗ ExecutionPolicy 值（budget/calls/wall_time）的合理性
```

**核心断裂：fake 路径把整个 agent loop（model → tools → middleware → output → submit → gate）替换成了预制的 fixture。这 6 个环节每个都有独特的失败模式，但 fake 测试一个都没碰到。**

## 发现的所有 Bug（已确认 11 个 + 怀疑 3 个）

### 已确认（端到端定位）

| # | 症状 | 根因 | 文件:行号 | 本应被什么测试抓到 |
|---|------|------|----------|-------------------|
| 1 | `NameError: real_final_delivery_gate_def` | import 缺失 | `builder.py:36` | import-linter / 编译期检查 |
| 2 | `--scripted` 静默失效 | `non_interactive_policy` 未转发 | `tool.py:178` | 单元测试：`run_deep_research` with context |
| 3 | `no model configured` | `DemoAppConfig.models=[]` | `_demo_core.py` | 集成测试：bridge 创建 chat model |
| 4 | `parent sandbox is None` | `DemoAdapter` 用 `object()` | `_demo_core.py` | 集成测试：storage verifier |
| 5 | storage probe POSIX 错误 | 3 个 Store 的 `.create()` 跑真实探针 | `*_bundle.py`, `work_unit_store.py` | 集成测试：store.create() with temp dir |
| 6 | `0 tools available` | resolver 读 `app_config.tools=[]` | `node_agent_bridge.py:62` | 单元测试：`_default_tools_resolver` |
| 7 | `tool has no typed policy spec` | `tool_specs=()` 默认空，所有工具拒绝 | `research.py` wave0/wave1 policy | 单元测试：policy.spec_for(tool_name) |
| 8 | **wave0 用 wave1 的 bridge** | `worker_caps = wave1_capabilities or wave0_capabilities` | `research.py:431` | 单元测试：resolver.resolve("wave0") vs ("wave1") |
| 9 | `token admission upper bound exceeds budget` | deepseek agent loop 消耗远超 48K | `research.py` budget | 集成测试：FakeModel + 真实 BudgetMiddleware |
| 10 | `maximum model calls reached` | `max_model_calls=6`，deepseek 循环 >6 次 | `research.py` budget | 集成测试：同上 |
| 11 | topic_planning `gate_blocked` | `parse_plan_output()` 严格的 Pydantic 验证，重试 2 次不够 | `topic_planning/node.py` | 单元测试：parse_plan_output with various malformed JSON |

### 怀疑但未确认

| # | 怀疑 | 理由 | 需要什么测试 |
|---|------|------|------------|
| A | wave0 gate 的 fatigue detection 在 mixed success/failure 时误判 | 曾有一次 worker OK 但 gate 仍 blocked | gate 单元测试：3 次 evaluation，1 OK + 2 FAIL 混合 |
| B | wave1/targeted_evidence/readiness 节点也有类似结构化输出问题 | 还没跑到这些节点 | 集成测试：wave1 worker with FakeModel |
| C | `ExecutionBudget.__post_init__` 可能拒绝极端值 | 未验证 | 单元测试：ExecutionBudget 边界值 |

## 需要的测试资产（按优先级分层）

### Layer 1: Policy + Middleware 单元测试（最高优先级，CI 每次跑）

这些测试用 FakeModel/ReplayModel，不调真实 LLM，秒级完成。

```
tests/unit/test_wave0_policy.py
───────────────────────────────
test_tool_specs_cover_all_allowed_tools       ← 防 bug #7
test_spec_for_unknown_tool_returns_none       ← 防 tools resolver mismatch
test_all_specs_are_eligible                   ← 防 native_cancellable=False
test_budget_values_are_positive               ← 防 budget 配置错误
test_max_parallel_tool_calls_reasonable       ← 防 bug #10 (#8 的预算部分)

tests/unit/test_topic_planning_parser.py
────────────────────────────────────────
test_parse_valid_json_produces_topic_plan     ← 正常路径
test_parse_malformed_json_raises              ← 错误路径
test_parse_missing_topics_field_raises        ← 字段缺失
test_parse_empty_topics_raises                ← min_length=1
test_synthesize_fallback_plan_not_empty       ← 防 bug #11
test_synthesize_fallback_plan_respects_input  ← fallback 用到了输入问题

tests/unit/test_worker_caps_resolution.py
─────────────────────────────────────────
test_wave0_uses_wave0_policy                  ← 防 bug #8（当前会 FAIL）
test_wave1_uses_wave1_policy                  ← 防 bug #8
test_hitl1_uses_hitl1_policy                  ← 防 policy 泄漏

tests/unit/test_budget_middleware_admission.py
─────────────────────────────────────────────
test_admission_allows_small_request            ← 正常
test_admission_rejects_over_budget             ← 拒绝
test_admission_accumulates_tokens              ← 累积
test_tool_result_does_not_count_as_model_token ← 关键：工具结果不应该计入 admission
```

### Layer 2: Worker 集成测试（CI 跑，用 ReplayModel）

这些测试构造完整的 worker 执行环境（bridge + middleware + policy + submit validator），用 ReplayChatModel 注入预制 LLM 输出。

```
tests/integration/test_wave0_worker_submit.py
─────────────────────────────────────────────
test_valid_output_passes_submit               ← 防 submit validation bug
test_missing_identity_fields_rejected         ← 防 Pydantic schema mismatch
test_empty_sources_accepted_with_limitations  ← 边界情况

tests/integration/test_topic_planner_agent.py
─────────────────────────────────────────────
test_planner_with_replay_output_succeeds      ← 防 parse 失败
test_planner_retry_on_malformed_output        ← 防重试逻辑 bug
test_planner_fallback_on_all_retries_fail     ← 防 fallback 不工作
```

### Layer 3: 真实 LLM 烟雾测试（PR 前手动跑，标记 @requires_llm）

```
tests/integration/test_real_llm_smoke.py
────────────────────────────────────────
test_start_reaches_hitl1                     ← 30s, 一次 LLM 调用
test_topic_planning_completes                 ← 20s, 一次 LLM 调用
test_wave0_one_topic_worker_completes         ← 60s, agent loop
```

### Layer 4: 完整端到端（release gate，CI 不跑）

```
make demo-real-scripted                       ← 5-15 分钟，全 11 节点
```

## 实施路线图

### Change 1: `add-worker-policy-regression-tests`
- Layer 1 的全部 10 个单元测试
- 补 Policy/Middleware/Parser/Gate 的确定性测试
- 覆盖 bug #7, #8, #9, #10, #11, A, B, C

### Change 2: `add-worker-integration-tests`
- Layer 2 的 6 个集成测试（ReplayModel）
- 覆盖 submit validation、topic planner agent 的完整路径

### Change 3: `add-real-llm-smoke-tests`
- Layer 3 的 3 个烟雾测试（真实 LLM）
- 标记 @requires_llm，CI 默认跳过

### Change 4: `fix-worker-policy-resolver`
- 修 bug #8（`worker_caps` 覆盖）
- 修 bug #2（`non_interactive_policy` 转发）
- 统一 wave0/wave1 budget
- 跑通 `make demo-real-scripted`

## 落地关联

- 本 plan 不直接产生 OpenSpec change——它是指挥后续 4 个 change 的战略文档
- 测试资产的 change 和 bug 修复的 change 可以并行推进
- 每个 change 对应一个 OpenSpec `add-*` 或 `fix-*`
