# Plan: Deep Research 13 - HITL2 Node

> 类型: 设计 | 更新: 2026-07-12
> 对应 OpenSpec change: `implement-deep-research-hitl2-node`
> 依赖: 03 Gate Kernel、12 Targeted Evidence Loop
> 替换范围: fake HITL2 decision node（`agent/src/deerflow_deep_research/graph/nodes/hitl2/fake.py`）

## 地基已具备（来自 01）

以下已由 01 的 fake HITL2 node 实现，**本 plan 只做升级，不重做**：

- **真实 LangGraph interrupt**: HITL2 的 `interrupt()`、checkpoint、graph 暂停——已实现。
- **resume + decision 路由**: proceed/repair/rerun/stop edges 已通——`routing.py` 已验证。
- **control tool 映射**: interrupt → `ToolMessage.artifact.human_input` → outer `END`——与 HITL1 共用同一机制。
- **research id/generation 绑定**: resume 已校验，拒绝过期 generation。
- **非交互占位**: 缺 policy 则 blocked——已定义。

## 目标

把 fake HITL2 的 fixture decision 替换为从 accepted findings 生成的 decision brief 和真实用户决策解析。

## Scope（缩减后）

- **deterministic brief builder** 从 accepted finding/quality state 生成展示数据。
- decision brief 明确：已确认结论、关键不确定性、未解决 gaps、成本/补证选项。
- interrupt 前先 checkpoint `pending_user` 和 brief hash，保证断线可恢复。
- **closed decisions 解析**：proceed、revise_view、repair、rerun、stop_blocked。
- resume 绑定 research id/generation/brief hash/request id，拒绝旧 generation 回答。
- state 先记录 pending 再展示 interrupt（fault-injection test 保留）。

## 验收

- 五种 decision edge、自由文本解析、重复/过期回答、restart resume 全覆盖。
- brief 内容只能引用 accepted findings，不能临时生成新事实。
- state 先记录 pending 再展示 interrupt，有 fault-injection test。
- mixed graph 使用真实 HITL2 后可分别进入 fake rerun/readiness/stop。

## Non-Goals

- 不实现 rerun invalidation、readiness 或 final。
- 不在本 change 实现 scheduled auto decision。

## 落地关联

14 和 15 可在本 change 后并行；两者消费同一 typed HITL2 decision contract。
