# Plan: Deep Research Demo — CLI Fake + CLI Real + TUI Real Full Pipeline

> 类型: 设计 | 更新: 2026-07-16
> 依赖: change 00-15（所有 11 个节点都有 real+fake factory）
> 对应 OpenSpec change: `add-deep-research-demo-full-pipeline`

## 背景 / 现状

### 问题

1. `demo.py` 只在 HITL 暂停点 dump JSON，用户看不到 bootstrap → topic_planning → wave0 → ... → final_delivery 的管道流动
2. 没有真实模式 demo — 无法用真实 LLM + web search 跑完整研究
3. `demo_tui.py` 直接 `from demo import DemoAdapter, ...` — 紧耦合，无共享抽象
4. 上一个尝试（`demo_fake.py`，已 revert）用硬编码静态阶段列表，不来自真实图执行状态

## 决策

### 1. 独立脚本，不用开关

`demo.py`（fake）和 `demo_real.py`（real）是两个独立脚本，不用 `--real` flag。
- fake 脚本零依赖，责任单一
- real 脚本有自己的凭据检查、bridge 注入、错误处理
- Makefile 天然隔离：`make demo` vs `make demo-real`

### 2. 共享代码 → `_demo_core.py`

提取 `DemoAdapter`、helpers、`PHASE_META`、`build_demo_recipe()` 到 `agent/scripts/_demo_core.py`。
三个 demo 脚本都从它导入。

### 3. 阶段进度 → checkpoint execution_trace 驱动

`ResearchState.execution_trace` 是每个节点的 `node_update()` 自动追加的 tuple。
每次 `graph.ainvoke()` 返回后 diff trace，显示新完成的阶段。不硬编码。

### 4. Real 模式 → `ResearchGraphRecipe.create()` 正路

```python
ALL_REAL_MODES = {name: "real" for name in LOGICAL_NODES}
ResearchGraphRecipe.create(
    implementation_modes=ALL_REAL_MODES,
    work_unit_store_factory=...,
    node_agent_bridge_factory=RuntimeNodeAgentBridge,
)
```

### 5. TUI → real-only

用户说"没有fake TUI"。TUI 启动时检查凭据，无凭据则退出报错。

## 文件变更

| 文件 | 操作 |
|------|------|
| `agent/scripts/_demo_core.py` | **新建** |
| `agent/scripts/demo.py` | **修改** — 导入 _demo_core，阶段展示 |
| `agent/scripts/demo_real.py` | **新建** |
| `agent/scripts/demo_tui.py` | **修改** — real-only，导入 _demo_core |
| `agent/Makefile` | **修改** — demo-real, demo-real-scripted |
| `agent/tests/integration/test_demo_cli.py` | **修改** |
| `agent/tests/integration/test_demo_tui.py` | **修改** |
| `agent/tests/unit/test_demo_core.py` | **新建** |

## 实现步骤

见 `openspec/changes/add-deep-research-demo-full-pipeline/tasks.md`

## 落地关联

- 一个 OpenSpec change：`add-deep-research-demo-full-pipeline`
- 不改 `backend/`、`frontend/`、`deerflow_deep_research` 包
