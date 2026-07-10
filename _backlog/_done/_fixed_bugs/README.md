# Fixed Bugs Index — 已修复 bug 归档

> 最后更新: 2026-07-10 | `_backlog/_done/_fixed_bugs/` — 已修复 bug 的归档目录。
> 接收来自 [`../../bugs/`](../../bugs/) 的 bug。`_` 前缀 = coding agent 默认忽略。
>
> **本目录是 bug 编号的唯一权威来源——新 bug 的编号 = 本目录最大编号 + 1。**

## 接收一个修完的 bug

bug 修完后从 `_backlog/bugs/` 通过 `git mv` 移入本目录：
1. 在本文件表格加一行（ID + Date + Title）
2. 更新下面的 "Next available bug ID"
3. 更新 `../../bugs/README.md`（删掉该 bug）
4. 更新 `../README.md`（计数 +1）

---

| ID | Date | Title |
|----|------|-------|
| — | — | — |

**Next available bug ID: BUG-001**

---

## Suspended (未修复，仍在排查)

悬挂 bug 放在 [`../_suspened_bugs/`](../_suspened_bugs/)，尚未确认修复。此处不列。
