# Plan: Deep Research 06 - HITL1 Node

> 类型: 实施完成 | 更新: 2026-07-15
> 对应 OpenSpec change: `implement-deep-research-hitl1-node`
> 依赖: 05 Bootstrap Node
> 替换范围: mixed graph 的 real HITL1；full-fake `fake.py` 保持不变

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
- 把 recorded profile 写入 checkpoint 短字段和 request-bundle `profile.json`，通过显式
  `accepted` 路由进入 topic planning。
- profile 值必须来自 closed enum 或显式 custom payload，不能由模型悄悄替换。

## 已落地

- `domain/profile.py` 定义 frozen extra-forbid `StructuredBrief`、`PartialResearchProfile`、
  `ResearchProfile`、closed enum、canonical JSON/hash、merge/finalize 和 deterministic parser。
- `graph/nodes/hitl1/prompts.py` 构造 bounded node-agent brief prompt、follow-up context 和
  strict brief parser。
- `graph/nodes/hitl1/node.py` 实现 real HITL1：node-agent brief generation、一次 repair、
  `interrupt(PendingResearchInterrupt(...))`、accepted/cancel/mismatch、checkpointed
  follow-up、第三轮 degraded profile、`exhausted` blocked path。
- `runtime/request_bundle.py` 是唯一 `request/profile.json` writer，执行 same-directory
  staging、atomic replace、fsync、symlink/path containment 和 redacted errors。
- `ResearchState` schema version 仍为 2，新增 `profile_ref`、短 enum 字段、
  `must_answer_questions`、`degraded_profile`、`pending_profile`、`profile_followup_round`。
- normalized topology 新增 `hitl1 --needs_followup--> hitl1` 和
  `hitl1 --exhausted--> blocked`；`accepted`/`cancel` 不变。
- `ResearchGraphRecipe` 只允许 `bootstrap=real` + `hitl1=real` 的 mixed real-HITL1，
  并仅在 start/resume context 构造 real `RuntimeNodeAgentBridge` 和 request-bundle writer。

## 验收

- 正常回答、自由文本、缺字段、重复 resume、错 request id、restart resume 全覆盖。
- profile 值必须来自 closed enum 或显式 custom payload，不能由模型悄悄替换。
- outer thread 中不追加伪 final answer，resume 后 graph 从 HITL1 后继继续。
- mixed graph 走真实 bootstrap/HITL1，其余 fake，E2E 通过；生命周期结果仍为
  `implementation_mode=full_fake`。

## Non-Goals

- 不生成最终 topics，不执行搜索。
- 不实现 HITL2 或 scheduled auto-proceed。
- 不修改 `backend/`、`frontend/`、root config、extensions、skills、Agent/SOUL、MCP/ACP。

## 落地关联

07 以 recorded profile 和 must-answer questions 为唯一规划输入。
