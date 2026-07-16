# Plan: Deep Research 14 - Rerun Node

> 类型: 设计 | 更新: 2026-07-16
> 对应 OpenSpec change: `implement-deep-research-rerun-node`（已 proposal，待 apply）
> 依赖: 04 Work Unit Kernel ✅、13 HITL2 Node ✅
> 替换范围: fake rerun planner、generation increment 和回边（`agent/src/deerflow_deep_research/graph/nodes/rerun/fake.py`）

## 地基已具备（来自 01 + 08–13 实际实现）

- **rerun node 位置**: 01 的 rerun node 已在拓扑中，HITL2 → rerun → topic planning/Wave0 回边已定义。HITL2（13）现在是 real，用户 rerun 决策携带实际 findings/scope 上下文，不再是无上下文的 fixture 选择。
- **generation 概念**: 01 的 state 已有 generation 字段占位。03 gate kernel 已定义 generation 的 writer 所有权（仅 gate 和 rerun node 可写）。HITL2（13）的 `request_id` 已编码 generation，提供 stale-resume 检测。
- **work-unit kernel 已验证**: 04 的 WorkSpec/fan-out/fan-in/ledger 模式在 wave0（08）、wave1（10）、targeted evidence（12）中经过三轮真实使用，rerun 的 scoped WorkSpec 创建是同一模式的第四次应用。
- **实际变更**: OpenSpec change `implement-deep-research-rerun-node` 已 proposal 完成（proposal/design/specs/tasks 就绪），待 apply。

## 目标

实现 HITL2 rerun 的增量新 generation，不覆盖上一代 accepted evidence，也不把旧决策误用到新一代。

## Scope

- typed rerun request：原因、目标 topics/findings、保留/失效范围、budget。
- `generation += 1` 单调更新；旧 ledger append-only 保留。
- deterministic invalidation 只失效派生 projection/decision，不删除原始 submission。
- rerun planner 生成新增/修订 WorkSpecs，复用 work-unit kernel。
- 回到 topic planning 或 Wave0/Wave1 的 edge 由 rerun scope 决定且闭集化。
- 新 generation 必须重新通过受影响 wave gates 和 HITL2；旧 HITL2 proceed 不继承。
- generation lineage 在 final citations/diagnostics 可追踪。

## 验收

- full rerun、单 topic rerun、单 finding repair、无效 scope、budget exhausted 全覆盖。
- 旧 evidence 可读取但不被错误计为新 generation 的未复核结论。
- rerun crash/restart 不会重复增加 generation 或双创建 work。
- 真实 rerun 与其余 real/fake mixed graph 两代 E2E 通过。

## Non-Goals

- 不做任意历史分支合并或多 active generation。
- 不实现 late-submit 跨 generation 接受。

## 落地关联

17 的 cancellation/recovery 必须覆盖 rerun 中途状态；18 评估增量 rerun 的成本与正确性。
