# Active Plans — 活跃 plan/分析文档列表

> 最后更新: 2026-07-15 | `_backlog/plans/` — 活跃 plan 在此，完成移入 [`../_done/_closed_plans/`](../_done/_closed_plans/)。
>
> **plan 没有编号，文件名即标识。完成后文件名不变，位置即状态。**

## 完成一个 plan 的步骤

1. `git mv plans/<name>.md _done/_closed_plans/<name>.md`
2. 更新 `_done/_closed_plans/README.md`（加一行 + 更新 Next available plan ID）
3. 更新本文件（删掉该 plan）
4. 更新 `../_done/README.md`（计数 +1 closed）

**plan 是"分析/设计/复盘"文档，不是活跃 change 本身。** 真正的实施走 `openspec/changes/`；plan 记录的是思考、取舍、复盘（postmortem），一旦其结论已落地或被 change 吸收即可关闭。

---

## 活跃列表

| Plan | 简述 |
|------|------|
| [deerflow-native-deep-research-graph.md](deerflow-native-deep-research-graph.md) | 总体架构、DPT 同构映射、00–18 路线图（00–05 ✅ 已归档，06 起待做） |
| [deep-research-spec-gates-and-coverage.md](deep-research-spec-gates-and-coverage.md) | 治理：spec 门禁与 requirement-test 覆盖目录（提案，未立 change） |
| [deep-research-structured-output-linting.md](deep-research-structured-output-linting.md) | 治理：agent YAML/JSON 结构化输出 lint（提案，Phase 2 已随 04 解锁） |
| [deep-research-07-topic-planning-node.md](deep-research-07-topic-planning-node.md) | 真实 topic planning 与 seed materialization node |
| [deep-research-08-wave0-node.md](deep-research-08-wave0-node.md) | 真实 Wave0 source-intake phase |
| [deep-research-09-evidence-critic-nodes.md](deep-research-09-evidence-critic-nodes.md) | 独立 source diagnostic 与 claim verifier nodes |
| [deep-research-10-wave1-node.md](deep-research-10-wave1-node.md) | 真实 Wave1 evidence-depth phase |
| [deep-research-11-wave2-synthesis-node.md](deep-research-11-wave2-synthesis-node.md) | 无 web 工具的真实 Wave2 pure-synthesis node |
| [deep-research-12-targeted-evidence-loop.md](deep-research-12-targeted-evidence-loop.md) | gap planner、targeted workers 与 Wave2 convergence gate |
| [deep-research-13-hitl2-node.md](deep-research-13-hitl2-node.md) | 真实 HITL2 typed decision node |
| [deep-research-14-rerun-node.md](deep-research-14-rerun-node.md) | rerun generation、scoped invalidation 与 graph 回边 |
| [deep-research-15-readiness-node.md](deep-research-15-readiness-node.md) | answerability、citation closure 与 readiness gate |
| [deep-research-16-final-delivery-node.md](deep-research-16-final-delivery-node.md) | final writer、integrity gate 与 workspace-to-outputs artifact publish |
| [deep-research-17-runtime-operations.md](deep-research-17-runtime-operations.md) | cancellation、non-interactive、progress 与 operator recovery |
| [deep-research-18-evaluation-hardening.md](deep-research-18-evaluation-hardening.md) | 全链路质量评估、故障注入与 production hardening |

**Next available plan ID: CLS-003**（移入 `_closed_plans/` 时分配）

---

## 卡片模板

新建 plan 文件 `<name>.md`（kebab-case slug 即标识）：

```markdown
# Plan: <标题>

> 类型: 设计 / 分析 / 复盘（postmortem） | 更新: 2026-MM-DD

## 背景 / 现状
触发这份 plan 的问题、当前状态、约束。

## 决策 / 方案
关键技术选择与理由（为什么 X 不是 Y），含考虑过的备选。

## 风险 / 取舍
已知限制、可能出问题的点。格式：[风险] → 缓解。

## 落地关联
计划如何变成 `openspec/changes/` 里的 change（或已被哪个 change 吸收）。
```
