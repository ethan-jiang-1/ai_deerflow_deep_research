# Plan: Deep Research 17 - Runtime Operations

> 类型: 设计 | 更新: 2026-07-10
> 对应 OpenSpec change: `harden-deep-research-runtime-operations`
> 依赖: 14 Rerun Node、16 Final Delivery Node
> 替换范围: 横切运行时能力，不替换单一 phase node

## 目标

补齐完整 graph 在真实 DeerFlow runtime 中的 cancellation、non-interactive、progress、recovery 和 operator diagnostics。

## Scope

- outer run cancel 向 nested graph/worker 传播，禁止 cancel 后 submit ledger。
- orphan attempt detection/cleanup，明确 crash 后 replay policy。
- non-interactive policy：预置 profile/HITL2 policy 或 blocked；不伪造 human decision。
- phase/batch/gate/usage coarse progress events 进入现有 stream/run events；网页噪声不进入 lead context。
- status/cancel/operator inspect 输出稳定、脱敏、user/thread scoped。
- memory/sqlite/postgres lifecycle、multi-worker ownership 和 connection cleanup。
- support-bundle/diagnostics 包含 graph phase、checkpoint refs、gate codes，不包含网页正文/secret。
- schema migration/unsupported-version runbook。

## 验收

- 在每个主要 phase、HITL、fan-out、rerun、final publish 注入 cancel/crash。
- cancel 后无新 accepted submission；restart 后从最后 committed superstep 恢复。
- scheduled run 无 policy 时不会悬挂，有 policy 时可全链完成并标记来源。
- SQLite 单 worker与 Postgres multi-worker stress/integration tests 通过。
- progress 事件顺序稳定且不会把低层 tool output 泄漏到用户消息。

## Non-Goals

- 不改变 research quality rules 或 UI 布局。
- 不支持同 thread 多 active research run。

## 落地关联

18 以本 change 的故障注入点、events 和 metrics 作为 production evaluation 基础。
