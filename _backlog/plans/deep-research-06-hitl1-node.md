# Plan: Deep Research 06 - HITL1 Node

> 类型: 设计 | 更新: 2026-07-12
> 对应 OpenSpec change: `implement-deep-research-hitl1-node`
> 依赖: 05 Bootstrap Node
> 替换范围: fake HITL1 interrupt/resume node（`agent/src/deerflow_deep_research/graph/nodes/hitl1/fake.py`）

## 地基已具备（来自 01）

以下已由 01 的 fake HITL1 node 实现，**本 plan 只做升级，不重做**：

- **真实 LangGraph interrupt**: `interrupt()` 调用、checkpoint 写入、graph 暂停——已实现。
- **resume 恢复**: 从真实 `HumanMessage` 读取原文，拒绝 tool payload 中的伪造回答——已实现。
- **control tool 映射**: interrupt → `ToolMessage.artifact.human_input` version-1 → outer `END`——已实现。
- **request id/research id/generation/schema version** 在 interrupt payload 中——已实现。
- **非交互路径**: 缺 policy 则 blocked 的占位合同——已定义。
- **outer thread 不追加伪 final answer**: resume 后 graph 从 HITL1 后继继续——已验证。

## 目标

把 fake HITL1 的 fixture question/answers 替换为 LLM 生成的 structured brief 和真实用户回答解析。

## Scope（缩减后）

- 从 original question 生成只供用户确认的 **structured brief draft**（LLM agent）。
- 提问 profile、范围、must-answer、时间/成本倾向；选项有稳定 machine values。
- 解析/校验用户回答；不完整时生成同一 checkpoint 的 follow-up interrupt。
- 把 recorded profile 写入 state 和 bundle ref，通过 **HITL1 gate** 后进入 topic planning。
- profile 值必须来自 closed enum 或显式 custom payload，不能由模型悄悄替换。

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
