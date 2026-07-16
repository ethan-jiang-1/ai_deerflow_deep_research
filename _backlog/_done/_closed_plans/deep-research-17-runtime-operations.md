# Plan: Deep Research 17 - Runtime Operations

> 类型: 设计 | 更新: 2026-07-16
> 对应 OpenSpec change: `harden-deep-research-runtime-operations`（待 proposal）
> 依赖: 14 Rerun Node（proposal 完成）、16 Final Delivery Node（待 proposal）
> 替换范围: 横切运行时能力，不替换单一 phase node

## 地基已具备（来自 00 + 01 + 全链路 08–13）

以下已由 00 和 01 交付，**本 plan 不用重建**：

- **cancel 传播**: 01 的 `runtime/control.py` 已实现 cancel action → lifecycle state transition → graph 清理；`status` 可返回当前 phase/waiting state。08–13 的全链路运行已验证 cancel 在 wave worker batch、critic agent、synthesis loop 中正确传播。
- **checkpoint recovery**: 01 已验证 memory 同进程恢复和 file-SQLite 跨进程恢复。03 checkpointer 集成已在 08–13 中经过大量 checkpoint 写入/恢复（每个 wave gate、每次 HITL interrupt 都写 checkpoint）。
- **provider lifecycle**: 00 已定义 `async_provider.make_checkpointer(app_config)` 和 per-action open/close；memory/sqlite/postgres 三 backend 可用。
- **lifecycle tool**: 01 的 `start | resume | status | cancel` 已通过 reflected control tool 暴露；identity 由 RuntimeAdapter 提供。HITL1（06）和 HITL2（13）已验证完整的 interrupt/resume 链路。
- **新增横切经验**: 08–13 暴露了 recovery edge cases（worker crash 中 ledger 一致性、batch 中单 worker timeout 的 orphan detection、HITL interrupt 前后的 crash replay），为 17 的 scope 提供了真实测试场景。

## 目标

补齐完整 graph 在真实 DeerFlow runtime 中的 non-interactive policy、progress visibility、recovery edge cases 和 operator diagnostics。

## Scope（缩减后——cancel/checkpoint/lifecycle 已通）

- **crash 后 replay edge cases**: orphan attempt detection/cleanup，明确 crash 后 replay policy。
- **non-interactive policy**: 预置 profile/HITL2 policy 或 blocked；不伪造 human decision——升级 01 的占位合同为完整实现。
- **progress events**: phase/batch/gate/usage coarse progress events 进入现有 stream/run events；网页噪声不进入 lead context。
- **status/cancel/operator inspect** 输出稳定、脱敏、user/thread scoped——在 01 已有基础上加固。
- **multi-worker ownership**: memory/sqlite/postgres 的 connection cleanup 和 per-worker isolation contract。
- **support-bundle/diagnostics** 包含 graph phase、checkpoint refs、gate codes，不包含网页正文/secret。
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
