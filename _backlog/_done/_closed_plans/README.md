# Closed Plans Index — 已完成 plan 归档

> 最后更新: 2026-07-15 | `_backlog/_done/_closed_plans/` — 已完成 plan 的归档目录。
> 接收来自 [`../../plans/`](../../plans/) 的 plan。`_` 前缀 = coding agent 默认忽略。
>
> **plan 完成后文件名不变，位置即状态。** 移入时分配 `CLS-NNN` 序号（Closed），按完成时间递增。

## 接收一个完成的 plan

plan 完成后从 `_backlog/plans/` 通过 `git mv` 移入本目录：
1. 在本文件表格加一行（CLS-NNN + 日期 + 文件名 + 简述），编号 = 当前最大 + 1
2. 更新最后的 "Next available plan ID" 行
3. 更新 `../../plans/README.md`（移除该 plan 的行）
4. 更新 `../README.md`（计数 +1）

---

## 已完成列表

| ID | Date | File | Summary |
|----|------|------|---------|
| CLS-001 | 2026-07-13 | [deep-research-tui-hitl-terminal-workbench.md](deep-research-tui-hitl-terminal-workbench.md) | HITL in Terminal Workbench — demo TUI split to `add-deep-research-lifecycle-demo-tui`; formal integration deferred to backlog |
| CLS-002 | 2026-07-15 | [deep-research-05-bootstrap-node.md](deep-research-05-bootstrap-node.md) | Real bootstrap node — atomic bundle establishment + schema/version marker, non-gated binding-validation replacing the fake fixture pass (OpenSpec `implement-deep-research-bootstrap-node`, archived 2026-07-15) |

**Next available plan ID: CLS-003**
