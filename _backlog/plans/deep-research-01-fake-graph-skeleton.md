# Plan: Deep Research 01 - Fake Graph Skeleton

> 类型: 设计 | 更新: 2026-07-10
> 对应 OpenSpec change: `build-deep-research-fake-graph-skeleton`
> 依赖: 00 Runtime Infrastructure
> 在主图中的作用: 先建立完整拓扑，所有业务 node 使用 deterministic fake

## 目标

在实现任何真实 research node 前，跑通一张可以 start、interrupt、resume、rerun、finish 的完整 Deep Research StateGraph。它是后续所有 change 的集成底座和 topology contract。

## Scope

- 在 00 的 GraphHost 上建立 Deep Research graph factory，不重新实现 package/launcher/provider lifecycle。
- 建立全量 fake nodes：bootstrap、HITL1、topic planning、Wave0、Wave1、Wave2 synthesis、targeted evidence、HITL2、rerun、readiness、final。
- 建立全部 pass/repair/rerun/stop edges；fake gate 由 fixture 控制 outcome。
- fake Wave0/Wave1 至少包含一次三路 `Send`/fan-in fixture，用于证明并行拓扑和 mixed-node contract；正式 WorkSpec/submit 留到 04。
- HITL1/HITL2 使用真实 LangGraph interrupt/checkpoint，但问题和答案使用 fixture。
- 为 00 的 control tool shell 接入 `start | resume | status | cancel` fake-graph 协议；identity 继续只由 RuntimeAdapter 提供。
- 产出 graph topology snapshot/diagram，CI 检查不可意外新增 unreachable node 或 edge。
- 建立 node implementation map，使同一拓扑可选择 fake 或 real node。

## 骨架 E2E 路径

至少覆盖：

- happy path：START → 两次 HITL → final → END；
- gate repair：Wave0 fake fail → repair → pass；
- rerun：HITL2 rerun → topic planning/Wave0 回边 → 第二代完成；
- stop：HITL2 stop → typed terminal；
- process restart：HITL interrupt 后重启再 resume。

## 验收

- graph factory/control actions 只使用 00 提供的挂载与上下文合同，不引入第二条启动路径。
- 全图只用 fixture，不调用真实 LLM、web 或 sandbox research tools。
- graph checkpoint 与 lead-agent checkpoint namespace 隔离。
- 错 thread/request id、重复 resume、completed 后 resume 均 fail closed 或幂等。
- topology snapshot 和四条 E2E 路径全部通过。

## Non-Goals

- 不定义完整 ResearchState、证据 schema、submission ledger。
- 不实现真实 gate rule、worker、报告内容或质量阈值。
- 不优化前端进度展示。

## 落地关联

此 plan 完成并被 change 吸收后才能开始 02。后续 change 必须保留 full-fake 与 mixed fake/real E2E。
