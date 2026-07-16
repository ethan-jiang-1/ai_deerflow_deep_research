# Postmortem: Real-Mode Demo Integration — 为什么到尾巴上才发现这么多问题

> 类型: 复盘（postmortem） | 更新: 2026-07-17
> 触发: `add-deep-research-demo-full-pipeline` change 实现完成、`make demo-real-scripted` 首次执行

## 背景

这个 change 的目标是三个 demo：CLI fake、CLI real、TUI real。从 proposal → design → specs → tasks 做了三轮打磨，修了 16 处文稿问题。28 个 task 完成，19 个测试全绿，lint clean，fake 管线完美运行。

然后 `make demo-real-scripted` 一跑——挂了。不是挂一个地方，是挂了五六层。

## 发现的所有 Bug（逐层剥离）

### 第一层：Import 和编译期错误

| # | 症状 | 根因 | 文件 | 为什么 fake 测试没发现 |
|---|------|------|------|----------------------|
| 1 | `NameError: real_final_delivery_gate_def is not defined` | 函数在 `gate_adapter.py` 导出但 `builder.py` 没 import | `graph/builder.py` line 154 | fake 模式不设置 `final_delivery=real`，这行代码不会执行 |
| 2 | `non_interactive_policy` 未转发，`--scripted` 静默失效 | `ResearchActionInput` 有 `non_interactive_policy` 字段但 `run_deep_research()` 构造时没传 | `tool.py` | fake 模式的 HITL 走 `_answer()` 绕过 stdin，不走 context 路径 |

### 第二层：运行时配置和集成胶水

| # | 症状 | 根因 | 文件 | 为什么 fake 测试没发现 |
|---|------|------|------|----------------------|
| 3 | `no model configured` | `DemoAppConfig` 没有 model 配置——real 模式的 `create_chat_model()` 解析不到模型 | `_demo_core.py` | fake 节点不需要模型 |
| 4 | `parent sandbox is None` / `object has no attribute` | `DemoAdapter` 用 `object()` 当 parent_sandbox——work-unit storage verifier 拿不到合法 sandbox | `_demo_core.py` | fake 节点不访问 sandbox |
| 5 | storage probe 报 `POSIX` 错误 | `WorkUnitStore.create()` 跑真实 POSIX 存储探针，temp dir 下锁/fsync/aliased-readback 不稳定 | `work_unit_store.py`, `bootstrap_bundle.py`, `request_bundle.py` | fake 模式不创建这些 store |

### 第三层：工具链断裂

| # | 症状 | 根因 | 文件 | 为什么 fake 测试没发现 |
|---|------|------|------|----------------------|
| 6 | `0 tools available` | `_default_tools_resolver` 从 `envelope.app_config.tools` 读工具列表，但 `DemoAppConfig.tools = []`。虽然后来加了 `get_app_config()` 回退，但 config.yaml 的工具名是 `web_search`/`web_fetch` | `node_agent_bridge.py`, `_demo_core.py` | fake worker 不调用工具 |
| 7 | `tool has no typed policy spec: web_search` | `ToolPolicyMiddleware._authorize()` 要求每个工具都有 `ToolPolicySpec`，但 wave0/wave1 的 `ExecutionPolicy` 从来没注册过 `tool_specs`。默认 `tool_specs=()` → 任何工具都找不到 spec → 全部拒绝 | `agents/middleware.py` line 167, `research.py` | fake worker 不经过 ToolPolicyMiddleware |
| 8 | `parallel tool-call limit exceeded` | `max_parallel_tool_calls=2`，deepseek 倾向于并行调用 4+ 个搜索工具 | `research.py` wave0/wave1 policy | fake 节点不调用工具 |

### 第四层：预算耗尽

| # | 症状 | 根因 | 文件 | 为什么 fake 测试没发现 |
|---|------|------|------|----------------------|
| 9 | `token admission upper bound exceeds budget` | `total_token_budget=48_000`，deepseek 每次 agent loop 带动大段搜索结果，实际消耗远超此值 | `research.py` wave0/wave1 policy | fake 工作单元不消耗 token |
| 10 | `maximum model calls reached` | `max_model_calls=6`，deepseek agent loop 中每个 topic 都要多次模型调用（规划→搜索→摘要→整合） | `research.py` wave0/wave1 policy | fake agent loop 不存在 |

### 第五层：结构化输出质量

| # | 症状 | 根因 | 文件 | 为什么 fake 测试没发现 |
|---|------|------|------|----------------------|
| 11 | topic_planning `gate_blocked` | `_generate_plan()` 只重试 2 次就 exhaust。deepseek 的结构化 JSON 有时能被 `parse_plan_output()` 解析，有时不能——非确定性失败 | `topic_planning/node.py` | fake planner 返回预制 fixture |
| 12 | wave0 worker 成功执行但 gate 仍然 blocked | worker 跑通了（`finish_reason=success`），但 gate 的 fatigue detection（连续 3 次相同 failure fingerprint → BLOCKED）在 worker 曾经失败的 attempt 累积后触发 | `gate_kernel.py` line 139 | fake 的 gate 永远 PASS |

### 第六层：基础设施缺口

| # | 症状 | 根因 | 文件 |
|---|------|------|------|
| 13 | 重复运行时被旧 checkpoint 阻塞 | `outer_thread_id="demo-thread"` 硬编码 → 每次运行生成相同 research_id → 上次 blocked 的 checkpoint 阻止新运行 | `_demo_core.py` |

## 发现过程的时间线

```
第1次 run  → NameError (real_final_delivery_gate_def)     ← 秒级
第2次 run  → blocked at wave0 (gate_blocked)              ← 33秒
加日志     → model not configured                          ← 秒级
第3次 run  → no tools                                      ← 秒级
加 lenient → Pydantic validation passed, envelope mismatch ← 分钟级
加 submit  → 仍然是 blocked                                ← 分钟级  
抓 bridge  → budget_exhausted: parallel tool-call limit    ← 分钟级
加 spec    → 工具可用但 token admission upper bound         ← 分钟级
加 budget  → max_model_calls reached                        ← 分钟级
```
**总计：~10 次端到端运行，每次 30 秒到数分钟，花费数小时定位 13 个 bug。**

如果有一个 **worker 单元测试** 用 `FakeToolCallingModel` + 真实 `ToolPolicyMiddleware` + 真实 `ExecutionPolicy` 跑一次 wave0 工作单元，前 12 个 bug 里的 8 个会在秒级被发现。

## 根因分析

```
                    ┌───────────────────────────────┐
                    │   所有验证在 fake 路径上通过    │
                    │   零次 real 路径集成测试        │
                    └───────────────┬───────────────┘
                                    │
            ┌───────────────────────┼───────────────────────┐
            ▼                       ▼                       ▼
    ┌──────────────┐       ┌──────────────┐       ┌──────────────┐
    │ 编译期/import  │       │ 胶水代码      │       │ 策略/budget   │
    │ fix: 1 个     │       │ fix: 6 个     │       │ fix: 4 个     │
    │ (秒级发现)    │       │ (分钟级发现)  │       │ (分钟级发现)  │
    └──────────────┘       └──────────────┘       └──────────────┘
```

**fake 管线验证了"图拓扑正确"**，但 real 管线的风险不在拓扑，在集成点：
- 工具名匹配（字符串一致性，编译期检查不到）
- 工具策略 spec（ToolPolicySpec 注册，只有运行时 middleware 才触发）
- Token 预算（值是否正确取决于实际 LLM 行为，fake 根本不消耗 token）
- 结构化输出解析（LLM 的非确定性输出 vs 严格 Pydantic schema）

这些集成点恰好在 fake 路径上被彻底跳过。

## 应该怎么测：分层策略

### 当前测试资产（几乎为零）

```
test_demo_core.py (15 单元测试)
  - build_demo_recipe fake/real 模式标志检查
  - PHASE_META 覆盖所有节点
  - create_hitl_response / check_credentials / _runtime
  - display_phase_progress 输出格式

test_demo_cli.py (1 集成测试)
  - 子进程跑 demo.py --scripted，检查中文阶段标签

test_demo_tui.py (3 集成测试)
  - Textual pilot 驱动 fake 配方，检查 happy path/cancel/invalid
```

**问题**：没有一个测试让 `ToolPolicyMiddleware` 真正跑过，没有一个测试让 `ExecutionPolicy.tool_specs` 被 lookup 过，没有一个测试让 `BudgetMiddleware` 在真实 agent loop 中被触发过。

### 需要补的测试层

```
┌──────────────────────────────────────────────────────────────┐
│ Layer 1: Policy + Tool 单元测试（缺失）                       │
├──────────────────────────────────────────────────────────────┤
│ test_wave0_policy_tool_specs:                                │
│   构造 ExecutionPolicy(wave0 budget + tool_specs)             │
│   跑一次 FakeToolCallingModel agent loop                      │
│   → 验证 ToolPolicyMiddleware 不拒绝工具                      │
│   → 验证 BudgetMiddleware 不拒绝假模型调用                     │
│   时间: < 1 秒                                               │
│                                                              │
│ test_wave0_worker_with_mock_model:                           │
│   用 ReplayChatModel(预制输出) 跑一次完整 wave0 工作单元       │
│   → 验证 worker 输出通过 submit validation                    │
│   时间: < 2 秒                                               │
│                                                              │
│ 这层能发现 bug #7, #8, #9, #10（当前在端到端才发现）         │
└──────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────┐
│ Layer 2: 真实 LLM 烟雾测试（缺失）                            │
├──────────────────────────────────────────────────────────────┤
│ @requires_llm                                                │
│ test_real_start_reaches_hitl1:                               │
│   run_deep_research(action="start") → 验证返回 HITL1 Command  │
│   时间: ~30 秒（一次 LLM 调用）                               │
│                                                              │
│ test_real_topic_planning_completes:                          │
│   从 HITL1 resume → 验证 topic_planning 不出错               │
│   时间: ~20 秒                                               │
│                                                              │
│ test_real_wave0_worker_completes_one_topic:                  │
│   从 topic_planning resume → 验证至少一个 topic 的 worker 成功 │
│   时间: ~60 秒                                               │
│                                                              │
│ 这层能发现 bug #11, #12（结构化输出质量 + gate fatigue）      │
│ 标记 @requires_llm，日常 CI 跳过，PR 前手动跑                 │
└──────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────┐
│ Layer 3: 完整端到端（当前唯一的测试方式，保留但降级为 smoke） │
├──────────────────────────────────────────────────────────────┤
│ make demo-real-scripted                                      │
│   全 11 节点真实管线                                          │
│   时间: 5-15 分钟                                            │
│   用途: release gating, not daily CI                         │
└──────────────────────────────────────────────────────────────┘
```

## 发现过程改进：前置门禁

**当前流程（错的）**：
```
plan → design → specs → tasks → 全部实现 → fake 测试 → lint → 首次 make demo-real → 发现 13 个 bug
```

**应该的流程**：
```
plan → design → specs → tasks
  → 实现 _demo_core.py（DemoAdapter + 模型自动检测）
  → **Layer 1 单元测试**（FakeToolCallingModel + real policy）  ← 秒级，发现 bug #7-10
  → 实现 demo_real.py 骨架（start → HITL1 路径）
  → **Layer 2 烟雾测试**（真实 LLM, start→HITL1）              ← 30秒，发现 bug #11
  → **Layer 2 烟雾测试**（HITL1 resume → wave0）               ← 60秒，发现 bug #12
  → 继续实现剩余
  → fake 测试 + lint
  → **Layer 3 完整端到端**（release gate）                     ← 此时应只有 0-1 个新 bug
```

**关键改变**：不要等"全部实现完成"才第一次跑 real 管线。在实现早期（骨架阶段）就跑最小 real 路径。

## 教训总结

1. **"能 fake 跑通" ≠ "能 real 跑通"** — fake 不走过 middleware、不消耗 token、不调 LLM、不解析结构化输出
2. **端到端测试是发现 bug 最慢最贵的方式** — 每次 30 秒到数分钟，13 个 bug 每个都要跑完整管线才能暴露
3. **集成胶水是最脆弱的** — tool name 字符串、import、字段转发、策略 spec 注册，都是 trivial 但能 kill 整个管线
4. **预算值不能拍脑袋** — `max_parallel_tool_calls=2`、`total_token_budget=48_000` 这些值必须通过真实执行验证
5. **在最早可行的点做集成** — start→HITL1 只需要一个 LLM 调用，发现 6 个 bug（模型配置、sandbox、storage probe、凭据、non_interactive_policy）
