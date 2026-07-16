# Plan: Bug → Test 映射表

> 类型: 分析 | 更新: 2026-07-17
> 输入: `test-assets-postmortem-real-mode-integration.md` 中记录的 11 个 bug
> 用途: 每个 bug 映射到一个或多个应该在 CI 中跑的具体测试，确保同类问题不再以端到端方式暴露

## 原则

1. 每个 bug 至少有一个**确定性测试**（FakeModel / ReplayModel / 纯函数），< 1 秒，CI 每次跑
2. 测试失败消息必须包含足够上下文，让人不需要跑端到端就能定位
3. 如果 bug 的根本原因是"两个模块之间的接口契约不匹配"，测试应该放在接口的**消费方**（谁调用谁负责验证）

## 映射表

### Bug #1: `real_final_delivery_gate_def` import 缺失

- **根因**: `builder.py` 用了函数但没 import
- **测试**: 编译期检查。不需要新测试——现有的 `build_research_graph(implementation_modes=ALL_REAL)` 调用链在引入这个 import 后自动覆盖
- **位置**: `tests/unit/test_research_runtime_capabilities.py::test_all_real_mode_compiles`

### Bug #2: `non_interactive_policy` 未转发

- **根因**: `run_deep_research()` 构造 `ResearchActionInput` 时没传 `non_interactive_policy=`
- **测试**: 用 mock runtime 调 `run_deep_research(action="start")`，runtime.context 带 `non_interactive_policy`，验证 `ResearchActionInput.non_interactive_policy` 不为 None
- **位置**: `tests/unit/test_tool_dispatch.py::test_non_interactive_policy_forwarded_to_action_input`

### Bug #3: `DemoAppConfig` 没模型

- **根因**: 模型解析链路 `envelope.app_config → models[0] → create_chat_model()` 全空
- **测试**: 构造 `DemoAppConfig`(无模型)，调 `_default_model_resolver(envelope)`，验证 raise 明确的错误信息（不是 `NoneType has no attribute`）
- **位置**: `tests/unit/test_node_agent_bridge.py::test_model_resolver_rejects_empty_config`

### Bug #4: sandbox 用 `object()` 导致 storage verifier 崩溃

- **根因**: `DemoAdapter` 传 `parent_sandbox=object()`，storage verifier 调 `provider.get(parent.id)` → AttributeError
- **测试**: `DemoAdapter.adapt()` 后验证 `envelope.parent_sandbox` 要么是 None，要么是合法的 sandbox（有 `id` 属性）
- **位置**: `tests/unit/test_demo_core.py::test_demo_adapter_provides_valid_sandbox_or_none`

### Bug #5: storage probe 在 temp dir 失败

- **根因**: `WorkUnitStore.create()` / `BootstrapBundleStore.create()` / `RequestBundleStore.create()` 在每次调用时跑真实 POSIX 探针（lock/fsync/aliased-readback），temp dir 下不稳定
- **测试**: 用 temp dir 调 `WorkUnitStore.create()`，验证不抛异常
- **位置**: `tests/unit/test_bootstrap_bundle.py::test_create_with_temp_dir`（已有类似测试，需确认覆盖）

### Bug #6: tools resolver 读空 config 导致 0 tools

- **根因**: `_default_tools_resolver` 从 `envelope.app_config.tools` 读工具列表，`DemoAppConfig.tools=[]`，没有回退逻辑时返回空
- **测试**: 构造 `DemoAppConfig(tools=[])` + `ExecutionPolicy(allowed_tool_names={"web_search"})`，调 `_default_tools_resolver(envelope, policy)`，验证返回空列表并给出 warning（不静默）
- **位置**: `tests/unit/test_node_agent_bridge.py::test_tools_resolver_reports_empty_config`

### Bug #7: ToolPolicySpec 从来没注册过

- **根因**: wave0/wave1 `ExecutionPolicy` 的 `tool_specs` 默认空 tuple → `spec_for()` 永远返回 None → middleware 拒绝所有工具
- **测试 #1**: 调 `_wave0_worker_policy(ctx)`，对每个 `allowed_tool_names` 调 `spec_for(name)`，验证全部非 None
- **测试 #2**: 同上 for `_wave1_worker_policy`
- **测试 #3**: 用 `ToolPolicyMiddleware(policy)` 拦截 `web_search` 工具调用，验证不抛 `AgentPolicyError`
- **位置**: `tests/unit/test_worker_policy.py::test_wave0_all_tools_have_specs` 等

### Bug #8: `worker_caps = wave1_capabilities or wave0_capabilities` 覆盖

- **根因**: `_context()` 中当 wave0 和 wave1 都是 real 时，wave1_capabilities 非 None → `worker_caps = wave1_capabilities` → 所有 worker 都拿 wave1 的 bridge（包括 wave0 的 worker）
- **测试 #1**: 用 all-real recipe 构建 context，从 `work_units.resolver` 分别 resolve `logical_name="wave0"` 和 `logical_name="wave1"`，验证两者的 capabilities 使用不同的 policy（不是同一个对象）
- **测试 #2**: resolve `logical_name="wave0"`，验证 `capabilities.policy.policy_name == "wave0-source-intake"`
- **测试 #3**: resolve `logical_name="wave1"`，验证 `capabilities.policy.policy_name == "wave1-evidence-extraction"`
- **位置**: `tests/unit/test_worker_caps_resolution.py::test_wave0_and_wave1_use_distinct_policies` 等

### Bug #9: token admission check 太严

- **根因**: `BudgetMiddleware._request_upper_bound()` 把整个 chat history（包括工具返回的大段网页内容）都计入 admission 预估，导致 `tokens_used + projected > total_token_budget` 提前触发
- **测试 #1**: 用 `ReplayChatModel`（预制 conversation）跑一次 agent loop（3 次 model call + 3 次 tool call），验证不触发 budget_exhausted
- **测试 #2**: 超过 `total_token_budget` 时验证触发 budget_exhausted（确保 admission 仍然有效）
- **测试 #3**: 工具结果（tool_result）的 content 长度不影响下一次 model call 的 admission 预估
- **位置**: `tests/unit/test_budget_middleware.py::test_admission_with_large_tool_results` 等

### Bug #10: `max_model_calls` / `max_parallel_tool_calls` 太小

- **根因**: deepseek 的 agent loop 模式需要多于 6 次 model call 和多于 2 个并行工具调用
- **测试 #1**: 用 `ExecutionBudget(max_model_calls=N)` 跑 `ReplayChatModel`（N 次 conversation），验证边界：N 次成功、N+1 次触发 exhausted
- **测试 #2**: 用 `ExecutionBudget(max_parallel_tool_calls=N)` + 单次 model response 带 N+1 个 tool_calls，验证触发 exhausted
- **位置**: `tests/unit/test_budget_middleware.py`（已有类似测试，需确认覆盖并行工具调用场景）

### Bug #11: topic_planning parser 太严 + 重试不够

- **根因**: `parse_plan_output()` 用 `TopicPlan.model_validate_json()` 严格验证 → LLM 输出稍有格式偏差就 ValueError → 2 次重试后 exhaust → gate_blocked
- **测试 #1**: `parse_plan_output('{"schema_version":1,"topics":[{"title":"T","scope":"S","must_answer_bindings":["q"],"search_dimensions":["d"],"exclusions":[]}]}')` → 成功
- **测试 #2**: `parse_plan_output('not json')` → ValueError
- **测试 #3**: `parse_plan_output('{"schema_version":1}')` → ValueError（缺 topics）
- **测试 #4**: `_synthesize_fallback_plan(("Q1",))` → 返回至少 1 个 topic 的 MaterializedTopics
- **测试 #5**: `_generate_plan()` 在 `run_agent` 连续 4 次返回 malformed 输出后返回 fallback（不是 None）
- **位置**: `tests/unit/test_topic_planning_parser.py`

## 汇总

| Bug # | 需要的新测试文件 | 测试数 | 优先级 |
|-------|-----------------|--------|--------|
| 7, 10 | `tests/unit/test_worker_policy.py` | 5 | P0 |
| 8 | `tests/unit/test_worker_caps_resolution.py` | 3 | P0 |
| 11 | `tests/unit/test_topic_planning_parser.py` | 5 | P0 |
| 2 | `tests/unit/test_tool_dispatch.py` | 2 | P1 |
| 3, 6 | `tests/unit/test_node_agent_bridge.py`（补充） | 2 | P1 |
| 4 | `tests/unit/test_demo_core.py`（补充） | 1 | P1 |
| 9 | `tests/unit/test_budget_middleware.py`（补充） | 3 | P1 |
| 1, 5 | 已有测试覆盖 | 0 | — |

**总计：7 个文件（5 个新建 + 2 个补充），21 个新测试。全部 < 1 秒，全部用 FakeModel/ReplayModel/纯函数，零外部依赖。**
