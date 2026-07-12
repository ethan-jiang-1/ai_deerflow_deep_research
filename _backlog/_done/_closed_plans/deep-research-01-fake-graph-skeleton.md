# Plan: Deep Research 01 - Fake Graph Skeleton

> 类型: 设计 | 更新: 2026-07-12
> 状态: 已归档（`2026-07-12-build-deep-research-fake-graph-skeleton`）
> 对应 OpenSpec change: `build-deep-research-fake-graph-skeleton`
> 依赖: 已归档的 00 Runtime Infrastructure runtime substrate
> 在主图中的作用: 先建立完整拓扑，所有业务 node 使用 deterministic fake

## 目标

在实现任何真实 research node 前，跑通一张可以 start、interrupt、resume、rerun、finish 的完整 Deep Research StateGraph。它是后续所有 change 的集成底座和 topology contract。

当前实现已落地于 `agent/`：11 个 logical node package、统一 topology/implementation map、两次真实 interrupt、全路由 deterministic fixture、memory 同进程恢复与 file-SQLite 跨进程恢复均已覆盖。公开边界是 Web UI/兼容 generic client；known IM 与 non-interactive 的 start/resume fail closed，status/cancel 保留。对应 requirement 为 `RUI-006`、`REG-001`..`REG-005`。

## Scope

- 在 00 的 GraphHost generic action registry 上增加独立 Deep Research graph factory/handlers，不重新实现 package/launcher/effective-provider lifecycle，也不替换 00 的 infra-probe topology/namespace。
- 建立全量 fake nodes：bootstrap、HITL1、topic planning、Wave0、Wave1、Wave2 synthesis、targeted evidence、HITL2、rerun、readiness、final。
- 建立全部 pass/repair/rerun/stop edges；fake gate 由 fixture 控制 outcome。
- fake Wave0/Wave1 至少包含一次三路 `Send`/fan-in fixture，用于证明并行拓扑和 mixed-node contract；正式 WorkSpec/submit 留到 04。
- HITL1/HITL2 使用真实 LangGraph interrupt/checkpoint，但问题和答案使用 fixture；nested interrupt 必须桥接到外层 DeerFlow 的 human-input artifact/ToolMessage。
- `start` 不接受模型传入 question/research id；从 runtime 最新合格真实 `HumanMessage` 绑定原始请求，并用 trusted user/thread 的 domain-separated digest 派生每 outer thread 唯一的 opaque research id。stable message id 只作幂等相关性：同消息重试恢复同一 lifecycle，不同消息在已有 lifecycle 的 thread 返回冲突，新研究使用新 thread，01 不引入多活 research run。
- resume 时从 runtime 最新真实 `HumanMessage` 读取原文，不接受 tool payload 中伪造的用户答案。
- 为 00 的 control tool shell 注册 `start | resume | status | cancel` fake-graph handlers；identity 继续只由 RuntimeAdapter 提供，00 的 `infra_probe` 仍是独立诊断 action。
- lifecycle action 使用统一、bounded、versioned control-result envelope；suspended ToolMessage 的 text fallback 与普通 action 返回同一合同，并额外携带 human-input artifact。
- 所有 01 lifecycle 结果必须显式标记 `implementation_mode=full_fake`；fake final 只返回 terminal fixture marker，public skill/SOUL 不得把它描述为真实研究结论或报告。
- 产出 graph topology snapshot/diagram，CI 检查不可意外新增 unreachable node 或 edge。
- 建立 node implementation map，使同一拓扑可选择 fake 或 real node。

## 骨架 E2E 路径

至少覆盖：

- happy path：START → 两次 HITL → final → END；
- gate repair：Wave0 fake fail → repair → pass；
- rerun：HITL2 rerun → topic planning/Wave0 回边 → 第二代完成；
- stop：HITL2 stop → typed terminal；
- repair/revise：Wave0/Wave1 repair、targeted evidence → Wave2 synthesis 回环、HITL2 revise_view/repair、readiness typed repair targets、final repair 全部走显式 bounded edge；
- process restart：HITL interrupt 后重启再 resume；01 必须以 file-SQLite 通过，memory backend 明确标记为同进程能力；Postgres profile 与 live deployment smoke 继续留在 deployment follow-up，不是 01 gate。

## 验收

- graph factory/control actions 只使用 00 提供的挂载与上下文合同，不引入第二条启动路径。
- 全图只用 fixture，不调用真实 LLM、web 或 sandbox research tools。
- graph checkpoint 与 lead-agent checkpoint namespace 隔离。
- 错 thread/request id、旧而未消费的 answer 与 completed 后的全新 resume 均 fail closed；已消费的同一 request/message 重试只读重投影当前 durable interrupt/terminal 结果，不再次推进 graph。
- nested HITL suspension 先 checkpoint 再向外层返回 human-input artifact；fault-injection 覆盖“返回前崩溃”和“resume 前重启”。
- “返回前崩溃”重试必须重投影同一 research/request id，不得重复执行已完成 node 或留下随机 id orphan checkpoint。
- raw HumanMessage resume、错 thread/stale answer 拒绝、已消费 answer 的 delivery-retry 重投影都有 contract test。
- topology snapshot 和四条 E2E 路径全部通过。
- 运行基线保持 00 已验证的单 Gateway worker；01 不引入跨进程 action coordination，也不重开 launcher、Docker live smoke 或 Postgres profile 的延期范围。

## Non-Goals

- 不定义完整 ResearchState、证据 schema、submission ledger。
- 不实现真实 gate rule、worker、报告内容或质量阈值。
- 不优化前端进度展示。

## 落地关联

此 plan 完成并被 change 吸收后才能开始 02。后续 change 必须保留 full-fake 与 mixed fake/real E2E。
