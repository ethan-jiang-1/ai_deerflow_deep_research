# DPT Schema 系统 — 详细分析

> 从 `ai_tool_deepresearch` 分析，用于在 DeerFlow 上重实现。
> 主控文档: [../dpt-to-deerflow-mapping.md](../dpt-to-deerflow-mapping.md)
> 相关: [01-execution-model.md](01-execution-model.md) · [02-engine.md](02-engine.md)
>
> **DPT 源文件**: `DPT_FRAMEWORK/schema/enums.mjs`, `DPT_FRAMEWORK/schema/contracts/*.mjs`, `DPT_FRAMEWORK/schema/gate_definitions/*.json`, `DPT_FRAMEWORK/schema/research-styles/`, `DPT_FRAMEWORK/workflows/manifest.json`, `DPT_FRAMEWORK/workflows/transitions.chain.json`

## 概述

DPT 的 schema 系统分三层：enums（领域常量）、contracts（Zod/JS 可执行合约）、gate definitions（JSON 门禁定义）。

## 1. Domain Enums (`schema/enums.mjs`)

10 个 Zod enum，覆盖所有运行时状态：

```javascript
CurrentGate: instantiation_complete | hitl1_recorded | setup_ready | seed_topics_ready
           | wave0_complete | wave1_complete | wave2_complete | hitl2_recorded
           | rerun_ready | readiness_passed | none

StopAuthorizationState: unauthorized_continue_required | final_delivery
                      | decision_blocker | empty_queue_after_refill

QueueHealth: ready | thin | blocked | closed
RunState: not_started | in_progress | blocked | completed

ResearchProfile: not_selected | quick_factual | exploratory_map
               | claim_verification | debug

GateResult: pass | fail

HumanCheckpointStatus: not_started | pending_user | recorded | blocked | not_applicable
AnswerabilityClass: not_assessed | ready_substantive | ready_insufficient_judgment | blocked_repair_required

HITL2UserDecision: not_started | proceed_to_readiness | request_view_revision
                 | repair | rerun | stop_blocked

FinalReportView: not_started | profile_default | executive_brief | evidence_map
               | claim_judgment | technical_deep_dive | custom
```

## 2. Schema Contracts (`schema/contracts/`)

可执行合约（Zod schemas），被 engine 和 CLI 引用：

| Contract | 文件 | 内容 |
|----------|------|------|
| Gate | `gate.mjs` | GateResult, gate transition table schema |
| Plan | `plan.mjs` | rb_plan.md frontmatter schema (topic_registry) |
| Profile | `profile.mjs` | rb_profile.yaml schema (research_style_params, thresholds) |
| Queue | `queue.mjs` | QueueDemandItem, DelegatedInFlight, QueueSchema, TerminalHistory |
| Status | `status.mjs` | rb_status.json schema |
| Trace | `trace.mjs` | Trace event schema |

每个 contract 定义：
- 数据结构 shape (Zod)
- 必需字段 + 可选字段
- 字段级别的验证规则
- Schema version 字段（用于迁移）

## 3. Gate Definitions (`schema/gate_definitions/`)

Read-only JSON 文件，每个 gate 一个：

```
gate_definitions/
├── instantiation-complete.json
├── hitl1-recorded.json
├── setup-ready.json
├── seed-topics-ready.json
├── wave0-complete.json
├── wave1-complete.json
├── wave2-complete.json
├── hitl2-recorded.json
├── readiness-passed.json
└── rerun-ready.json
```

每个 gate definition 包含：
- `gate_key`: 对应 CurrentGate enum 值
- `phase_node`: 对应 phase markdown 路径
- `rules`: 规则数组，每条 { key, check_type, field?, condition?, say }
- `next_on_pass`: transitions.chain.json 中查到的 next phase

**重要**：gate definition JSON 是 read-only definition，不放 pass/fail 结果。Pass/fail 结果存在 bundle `_cache/gate-results/`。

## 4. Research Styles (`schema/research-styles/`)

预定义的 research profile 模板：

| Style | 特点 | 适用场景 |
|-------|------|---------|
| quick_factual | 浅层搜索，少 wave，低 source 要求 | 快速事实查询 |
| exploratory_map | 广度优先，多 topic，覆盖广 | 领域全景探索 |
| claim_verification | 深度验证，交叉引用 | 声明真伪判断 |
| debug | 最小化一切，快速跑通 | 调试/开发 |

每个 style 定义：
- 默认的 `wave0_per_topic_source_floor`
- 默认的 `wave1_per_topic_source_floor`
- 是否需要 wave2
- 默认的 subagent timeout
- 默认的 max_turns

## 5. Workflow Foundation (`workflows/`)

### manifest.json
```json
{
  "phases": [
    { "key": "instantiation", "node": "phases/phase-instantiation.md", "gate": "instantiation-complete" },
    ...
  ],
  "shared": [
    "shared/shared-profile.md",
    "shared/shared-gate-rules.md",
    ...
  ]
}
```
- 声明所有 phase 和它们的 gate 对应关系
- 声明所有 shared context 文件

### transitions.chain.json
```
{ currentNodeRef, outcome } → nextNodeRef
```
- 纯静态路由表
- Gate CLI 查表返回 `next`
- 不编码分支逻辑（fail/repair 由 Agent 处理）

## → DeerFlow 映射

### Enums → Python Literal types or StrEnum
```python
from enum import StrEnum
class CurrentGate(StrEnum):
    INSTANTIATION_COMPLETE = "instantiation_complete"
    HITL1_RECORDED = "hitl1_recorded"
    ...
```

### Contracts → Python Pydantic models
```python
from pydantic import BaseModel
class QueueDemandItem(BaseModel):
    queue_item_id: str
    kind: str
    priority_class: str
    action: str
    writes_to: list[str]
    required_receipts: list[str]
```

### Gate Definitions → Python dataclasses or Pydantic
- Gate 规则用 Python predicate 函数替代 Zod schema
- 返回结构：`{passed: bool, say: str, next: str|None, errors: list|None}`

### Research Styles → config.yaml 或 skills/custom/dpt/shared/
- 预定义 profile 放 shared context markdown
- 阈值放 rb_profile.yaml（由 Agent 在 setup phase 写入）

### Workflows → skills/custom/dpt/
- manifest.json → skills 目录结构
- transitions.chain.json → 内嵌在每个 phase skill 的 "On Gate Pass" 段落
