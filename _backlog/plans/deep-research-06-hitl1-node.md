# Plan: Deep Research 06 - HITL1 Node

> 类型: 设计 | 更新: 2026-07-10
> 对应 OpenSpec change: `implement-deep-research-hitl1-node`
> 依赖: 05 Bootstrap Node
> 替换范围: fake HITL1 interrupt/resume node

## 目标

将 DPT HITL1 的 research profile、root must-answer 和范围确认映射为可 checkpoint、可重启恢复的 typed interrupt。

## Scope

- 从 original question 生成只供用户确认的 structured brief draft。
- 提问 profile、范围、must-answer、时间/成本倾向；选项有稳定 machine values。
- interrupt payload 带 request id/research id/generation/schema version。
- control tool 将 interrupt 映射为现有 `human_input` artifact + outer `END`。
- resume 从 runtime 最新真实 HumanMessage 读取原文，不以 lead LLM 改写为权威。
- 解析/校验用户回答；不完整时生成同一 checkpoint 的 follow-up interrupt。
- 把 recorded profile 写入 state 和 bundle ref，通过 HITL1 gate 后进入 topic planning。
- 为 non-interactive 只定义“缺 policy 则 blocked”的占位合同，自动 policy 留到 17。

## 验收

- 正常回答、自由文本、缺字段、重复 resume、错 request id、restart resume 全覆盖。
- profile 值必须来自 closed enum 或显式 custom payload，不能由模型悄悄替换。
- outer thread 中不追加伪 final answer，resume 后 graph 从 HITL1 后继继续。
- mixed graph 走真实 bootstrap/HITL1，其余 fake，E2E 通过。

## Non-Goals

- 不生成最终 topics，不执行搜索。
- 不实现 HITL2 或 scheduled auto-proceed。

## 落地关联

07 以 recorded profile 和 must-answer questions 为唯一规划输入。
