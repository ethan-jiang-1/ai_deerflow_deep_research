# Plan: Demo 设计决策的测试覆盖

> 类型: 分析 | 更新: 2026-07-17
> 来源: `deep-research-demo-full-pipeline.md` 中的 5 个设计决策
> 用途: 从设计决策推导出需要什么测试来验证决策正确落地

## 决策 → 测试推导

### 决策 1: 独立脚本，不用 `--real` 开关

**设计**: `demo.py`（fake）和 `demo_real.py`（real）是两个独立脚本。

**测试关注点**:
- `demo.py` 在任何环境下都能跑（无凭据、无网络、无 config.yaml）——已有 `test_demo_cli.py`
- `demo_real.py` 无凭据时给出清晰错误后退出——**缺测试**
- 两个脚本使用相同的 `_demo_core` 导入，但 fake 不走 `RuntimeNodeAgentBridge`，real 走——**缺对比测试**

```
需补: test_demo_cli.py::test_demo_real_rejects_missing_credentials
需补: test_demo_core.py::test_fake_recipe_no_bridge_vs_real_recipe_has_bridge
```

### 决策 2: 共享代码 → `_demo_core.py`

**设计**: `DemoAdapter`、helpers、`PHASE_META`、`build_demo_recipe()` 提取到共享模块。

**测试关注点**:
- `PHASE_META` 覆盖所有 11 个 `LOGICAL_NODES`——已有 `test_phase_meta_covers_all_logical_nodes`
- `build_demo_recipe(mode="fake")` 返回的 recipe 不需要 node-agent bridge——已有 `test_build_fake_recipe`
- `build_demo_recipe(mode="real")` 返回的 recipe 需要 node-agent bridge——已有 `test_build_real_recipe`
- `DemoAdapter` 创建的 sandbox 是合法的——**缺测试**（跟 Bug #4 重叠）
- `_runtime()` 的 `context` 参数正确传递——已有 `test_runtime_with_custom_context`
- `create_hitl_response()` 的 option 模式正确设置 `option_id`——已有 `test_create_hitl_response_option`

### 决策 3: 阶段进度 → checkpoint `execution_trace` 驱动

**设计**: 每次 `graph.ainvoke()` 后 diff `execution_trace`，展示新增阶段。

**测试关注点**:
- `display_phase_progress()` 对已完成阶段输出 `→`——已有 `test_display_phase_progress_output`
- `display_phase_progress()` 对暂停阶段输出 `⏸`——已有 `test_display_phase_progress_suspended`
- `DeepResearchControlResult` 包含 `execution_trace` 字段——**缺测试**（验证 field exists + populated）
- trace diff 逻辑正确（不重复、不遗漏）——**缺测试**

```
需补: test_demo_core.py::test_control_result_includes_execution_trace
需补: test_demo_core.py::test_phase_trace_diff_logic
```

### 决策 4: Real 模式 → `ResearchGraphRecipe.create()` 正路

**设计**: 不绕过 `create()` 的依赖链验证，正确传 `implementation_modes=ALL_REAL_MODES`。

**测试关注点**:
- all-real recipe 编译不抛异常——已有（`test_build_real_recipe` 间接验证）
- recipe 的 `requires_*` 标志与 implementation_modes 一致——已有
- **缺**：验证 all-real 模式下 `_context()` 为 wave0 和 wave1 构建了**不同的** capabilities——跟 Bug #8 重叠

### 决策 5: TUI → real-only

**设计**: TUI 不支持 fake 模式，启动时检查凭据。

**测试关注点**:
- TUI 测试 mock 掉 bridge，用 fake 配方跑——已有 `test_demo_tui.py`（3 个测试）
- TUI 无凭据时退出——**缺测试**（当前被 mock 绕过）
- TUI 显示阶段进度面板——**已有**（`test_demo_tui_happy_path` 间接验证 banner 内容）

## 已有的 vs 缺失的

| 决策 | 已有测试 | 缺失测试 |
|------|---------|---------|
| 1. 独立脚本 | `test_demo_cli.py` (1) | `demo_real` 无凭据退出、fake vs real recipe 对比 |
| 2. 共享代码 | `test_demo_core.py` (15) | DemoAdapter sandbox 合法性 |
| 3. 阶段进度 | `test_demo_core.py` (2) | control result 包含 trace、trace diff 逻辑 |
| 4. Real 正路 | `test_demo_core.py` (2) | wave0/wave1 capabilities 区分（重叠 Bug #8） |
| 5. TUI real | `test_demo_tui.py` (3) | TUI 无凭据退出 |

## 跟其他 test-assets plan 的关系

- 本 plan 覆盖的是**demo 脚本层面**的测试缺口（`demo.py`、`demo_real.py`、`demo_tui.py`、`_demo_core.py`）
- `test-assets-bug-to-test-mapping.md` 覆盖的是**生产代码层面**的回归测试（middleware、policy、parser、gate）
- `test-assets-layered-strategy.md` 覆盖的是**分层测试架构**（unit → integration → smoke → e2e）
- `test-assets-postmortem-real-mode-integration.md` 覆盖的是**根因复盘**（11 个 bug 怎么被漏掉的）
