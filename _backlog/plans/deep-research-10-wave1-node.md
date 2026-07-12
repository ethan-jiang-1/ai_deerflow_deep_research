# Plan: Deep Research 10 - Wave1 Node

> 类型: 设计 | 更新: 2026-07-12
> 对应 OpenSpec change: `implement-deep-research-wave1-node`
> 依赖: 08 Wave0 Node、09 Evidence Critic Nodes
> 替换范围: fake Wave1 plan/worker/critic/gate/repair subgraph（`agent/src/deerflow_deep_research/graph/nodes/wave1/fake.py`）

## 地基已具备（来自 01）

- **subgraph 结构**: 01 已定义 Wave1 plan → workers → submit → gate → repair（`wave1/subgraph.py`），与 Wave0 共用 `Send` 并行机制。
- **worker → submit → critic pipeline**: 01 的 Wave1 fake subgraph 已走通 fan-out → fan-in → submit → gate 全路径。

## 目标

实现 topic-specific 深度证据提取，覆盖 mechanism、trend/difficulty、limitation/dispute/failure mode、反例和开放问题。

## Scope

- Wave1 planner 根据 profile floor、Wave0 背景和 must-answer 生成 evidence WorkSpecs。
- evidence worker 搜索/抓取新来源并输出 claims、counterevidence、open questions、cache refs。
- 明确 `is_new_vs_wave0`，Wave0 重复 URL 不计 new-source floor。
- submit 后运行 source diagnostic/claim verifier，生成独立 verdict artifacts。
- Wave1 gate 同时检查 hard provenance 和 semantic coverage/critic verdict。
- open question 进入 resolved/targeted-search/deferred/requires-internal-data closed states。
- repair agent 可补证、降级 claim 或显式 limitation，不可直接改 critic verdict。

## 验收

- 重复 Wave0 来源、snippet-only、unsupported claim、缺反例、缺维度、critic contradiction 全覆盖。
- 每个重大 claim 可追溯到 accepted submission 和 critic verdict。
- 同 topic 多 work 的 claim id/reducer 不冲突。
- mixed graph 到真实 Wave1 后进入 fake synthesis，正常/repair/restart E2E 通过。

## Non-Goals

- 不做跨 topic 综合或 targeted Wave2 search。
- 不写最终报告。

## 落地关联

11 只读取 Wave1 accepted evidence + verdict，不把 evidence-summary prose 本身当权威。
