# Done Todos Index — 已完成 todo 归档

> 最后更新: 2026-07-10 | `_backlog/_done/_done_todos/` — 已完成 todo 的归档目录。
> 接收来自 [`../../todos/`](../../todos/) 的 todo。`_` 前缀 = coding agent 默认忽略。
>
> **todo 完成后文件名不变（`todo-<name>.md`），位置即状态。** 移入时分配 `DONE-NNN` 序号，按完成时间递增。

## 接收一个完成的 todo

todo 完成后从 `_backlog/todos/` 通过 `git mv` 移入本目录：
1. 在本文件表格加一行（DONE-NNN + 日期 + 文件名 + 简述），编号 = 当前最大 + 1
2. 更新最后的 "Next available DONE ID" 行
3. 更新 `../../todos/README.md`（移除该 todo 的行）
4. 更新 `../README.md`（计数 +1）

---

## 已完成列表

| ID | Date | File | Summary |
|----|------|------|---------|
| — | — | — | — |

**Next available DONE ID: DONE-001**
