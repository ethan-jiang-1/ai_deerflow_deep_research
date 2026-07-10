# learning — apply / 研究复盘 retro

> 最后更新: 2026-07-10 | `_backlog/learning/` — 复盘笔记长期留存（不搬迁、不归档）。

这里放**做完一件事之后的复盘**：一次 OpenSpec change apply、一轮研究、一次大修 bug 的经验沉淀。目的是把"这次为什么做得好/差、下次怎么复用"变成可检索的经验，而不是散落在 commit message 里。

命名：`YYYY-MM-DD-<slug>.md`。retro 只增不删，也不参与 `git mv` 生命周期——它不是待办，是记忆。

---

## retro 模板

```markdown
# <标题> Retro

Date: 2026-MM-DD

## What Went Well
这次哪里做得比平常好，为什么。

## Repeatable Practices
可复用的具体做法（清单式，越具体越好）。

## Why This Found More Issues
为什么这套做法比以前发现了更多问题 / 更少返工。

## Next-Time Standard
下次同类工作，达到什么条件才算"做完"（可勾选清单）。
```

> 精髓（取自源实践）：把一个具体缺陷**转成横切排查**；先怀疑"这看起来像测试问题"，契约类 bug 要先看实现面；按 `tasks.md` 顺序执行，若发现顺序错了就**显式说明并调整**，别偷偷跳；复盘的归档说明**不要过度宣称**超出测试实际证明的范围。
