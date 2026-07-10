# DPT Phase Chain — 详细分析

> 从 `ai_tool_deepresearch` 分析，用于在 DeerFlow 上重实现。
> 主控文档: [../dpt-to-deerflow-mapping.md](../dpt-to-deerflow-mapping.md)
> 相关: [01-execution-model.md](01-execution-model.md) · [03-bundle-structure.md](03-bundle-structure.md) · [06-subagent-roles.md](06-subagent-roles.md)
>
> **DPT 源文件**: `DPT_FRAMEWORK/workflows/nodes/phases/phase-*.md` (11 个文件), `DPT_FRAMEWORK/workflows/nodes/shared/shared-*.md`, `DPT_FRAMEWORK/workflows/nodes/brief/`, `DPT_FRAMEWORK/workflows/manifest.json`, `DPT_FRAMEWORK/cli/gates/check-gate-*.mjs`

## 概述

DPT 的 11 个 phase 组成完整的研究流水线。每个 phase 是一个 Markdown 文件，告诉 Phase Agent 在该阶段的目标、允许动作、gate 命令、以及 pass/fail 后的行为。

## Phase 列表

| # | Phase | Gate | stop | 职责 |
|---|-------|------|------|------|
| 1 | instantiation | instantiation-complete | no | 创建 run bundle |
| 2 | hitl1 | hitl1-recorded | **yes** | 人类确认方向/profile/topics |
| 3 | setup | setup-ready | no | 验证 bundle 结构一致性 |
| 4 | seed-topics | seed-topics-ready | no | 物化 topic 文件 |
| 5 | wave0 | wave0-complete | no | 基础证据收集（per-topic source.yaml） |
| 6 | wave1 | wave1-complete | no | 深度证据收集（evidence-summary + question-list） |
| 7 | wave2 | wave2-complete | no | 跨 topic 综合（synthesis + cross-topic-ledger） |
| 8 | hitl2 | hitl2-recorded | **yes** | 人类审阅 synthesis |
| 9 | readiness | readiness-passed | no | 最终 deterministic precheck |
| 10 | rerun | rerun-ready | no | HITL2 rerun 后的增量分析 |
| 11 | final | null (terminal) | no | 最终报告生成 |

## Phase 文件的结构

每个 phase markdown 有统一结构：

```markdown
---
node_type: phase
id: phase-wave0
phase: wave0
gate: wave0-complete
stop: "no"
execution_contract:
  surface: phase-agent
  search_policy: work_unit_required        # no_search | work_unit_required | work_unit_required_for_new_evidence
  delegated_role_keys: [dpt-source-intake] # subagent roles used
requires:                                   # 必须加载的 shared context
  - shared/shared-profile
  - shared/shared-schemas
  - shared/shared-silent-execution
suggested_context:                          # 建议加载的 context
  - phases/subagent-dpt-source-intake
---

# Phase: Wave0 — Foundation Shared Reference

## 0. Execution Brief
目标、起点、路径、completion check、failure posture

## 1. Stage Goal
详细的阶段目标

## 2. Required Inputs
需要哪些文件/状态

## 3. Allowed Actions
允许做什么（通常分多个子阶段：Filling/Execute/Drain）

## 4. Expected Artifacts
产出什么文件

## 5. Gate Command
运行哪个 gate CLI

## 6. On Gate Pass
gate 过了之后做什么（加载下一个 phase）

## 7. On Gate Fail
gate 失败后的修复策略
```

## 三个 Wave 的递进关系

### Wave0 — Foundation Shared Reference
- **目标**: 为每个 topic 收集基础 source metadata
- **产出**: `artifacts/wave0/{topic}/source.yaml` + `reference/00-shared-*.md`
- **Subagent**: `dpt-source-intake`
- **特点**: 广度优先，establish baseline sources

### Wave1 — Topic-Specific Deepening
- **目标**: 深度阅读、提取证据、识别 open questions
- **产出**: `artifacts/wave1/{topic}/evidence-summary.md` + `question-list.md` + `depth-review.yaml`
- **Subagent**: `dpt-evidence-extractor`
- **特点**: 深度优先，每个 topic 独立 deepen
- **关键约束**: Wave0 URLs 可作背景，但不计入 Wave1 new-source floor

### Wave2 — Cross-Topic Synthesis
- **目标**: 跨 topic 综合分析 + 补证据缺口
- **产出**: `synthesis.md` + `cross-topic-ledger.md` + `finding-index.yaml`
- **Subagents**: `dpt-topic-scout` + `dpt-evidence-extractor`
- **特点**: Phase Agent 自己做 synthesis（不委托 subagent），只有新证据搜索才走 work unit
- **双重路径**: Pure synthesis（Agent 读已有 evidence 直接写）+ Delegated evidence（work unit 补缺口）

## Execution Contract 字段详解

| 字段 | 含义 | 可选值 |
|------|------|--------|
| `surface` | 谁执行 | `phase-agent`（主 Agent 自己）、`work-unit-subagent-role`（subagent role spec） |
| `search_policy` | 搜索策略 | `no_search`（不搜索）、`work_unit_required`（必须通过 work unit 搜索）、`work_unit_required_for_new_evidence`（新证据走 work unit，已有 evidence 可直接读） |
| `delegated_role_keys` | 该阶段使用的 subagent role | 如 `[dpt-source-intake, dpt-evidence-extractor]` |
| `loaded_by` | 谁加载这个文件 | `phase-agent` |
| `delivered_via` | 内容如何传递给 subagent | `work_unit_task_md`（Phase Agent 读 role spec → 生成 task.md → subagent 读 task.md） |
| `filesystem_write` | subagent 是否需要写文件 | `required` |

## 静默执行纪律 (`shared-silent-execution.md`)

所有 `stop: no` 的 phase 必须遵守：

1. **绝对不能向用户浮出水面** — 不展示消息、不提问、不报告进度
2. **Gate 失败不是紧急情况** — 正常修复、重试、降级
3. **四个合法降级路径**: (a) 修复后过 gate、(b) 换策略重跑、(c) gate 返回合法 degraded pass、(d) 静默 hold
4. **疲劳保护**: 3+ gate 失败时暂停、换策略、用 `--attempt N`
5. **不能自己加载下一个 phase** — 只能通过 gate 的 `check.next`

## HITL Phase 的特殊性

### HITL1 (`stop: yes`)
- **Step 1**: Topic rewrite — 如果用户输入只有一句话，展开为 structured original topic
- **Step 2**: 推导 3-5 个 seed topics → 写入 topic_registry（不创建文件，那由 seed-topics phase 做）
- **Step 3**: 展示 structured questions（research profile、root must-answer set、view preference）
- **Step 4**: 用户回答 → 写入 `rb_profile.yaml`

### HITL2 (`stop: yes`)
- **Step 1**: 产出 decision brief → 写 `artifacts/hitl2/decision-brief.md`
- **Step 2**: 设置 `hitl2.status = pending_user`（先写状态再展示 prompt——session 断了能恢复）
- **Step 3**: 展示决策 prompt（包含三个动态填入部分：已确认发现、不足/不确定、优先补证方向）
- **Step 4**: 用户 decision → 写入 `rb_profile.yaml`（proceed_to_readiness | request_view_revision | repair | rerun | stop_blocked）

## → DeerFlow 映射

### Phase Node → Custom Skill

每个 phase markdown 变成一个 `skills/custom/dpt/phases/phase-*.md`：

```yaml
# DeerFlow skill frontmatter 不需要改——直接复用 DPT 的 markdown
# Phase Agent 通过 describe_skill 或 read_file 加载当前 phase skill
```

### 加载机制

两种方案：
1. **Deferred discovery**: 所有 phase skill 在 skill index 中列名，Agent 用 `describe_skill` 按需加载当前 phase
2. **Active read**: Phase Agent 直接用 `read_file` 读 `skills/custom/dpt/phases/phase-wave0.md`

推荐方案 1（deferred discovery），因为：
- 不会把 11 个 phase 同时注入 system prompt
- Agent 在 phase transition 时主动 describe 下一个 phase skill
- 与 DPT 的动态加载哲学一致

### Gate Command → Custom Tool

每个 phase 的 "Gate Command" 段改为调用 DeerFlow tool：

```
## 5. Gate Command
Use tool `dpt_gate_check` with:
- gate: "wave0-complete"
- bundle_dir: "<sandbox _bundle path>"
```

### HITL → ask_clarification

```
## HITL1: Present structured questions via `ask_clarification` tool
## HITL2: Present decision brief via `ask_clarification` with A/B/C/D/E options
```

### Silent Execution → Natural Agent Behavior

DeerFlow 的 Agent 在 tool call loop 中自然静默——不需要额外的 `shared-silent-execution.md`。但需要在 phase skill 中强调 "Do not surface to user mid-phase" 规则。
