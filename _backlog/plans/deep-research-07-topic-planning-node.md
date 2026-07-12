# Plan: Deep Research 07 - Topic Planning Node

> 类型: 设计 | 更新: 2026-07-12
> 对应 OpenSpec change: `implement-deep-research-topic-planning-node`
> 依赖: 03 Gate Kernel、06 HITL1 Node
> 替换范围: fake topic planning/seed node（`agent/src/deerflow_deep_research/graph/nodes/topic_planning/fake.py`）

## 地基已具备（来自 01）

- **node 位置和路由**: 01 的 topic planning node 已在拓扑中，HITL1 → topic planning → Wave0 路径通。
- **gate transition**: 输入/输出 edge 和 repair 回边已定义。
- **fake fixture**: topic registry 和 seed artifacts 的 fixture 骨架已存在。

## 目标

用 bounded planner agent 把确认后的 brief/profile 转换成稳定 topic registry、must-answer coverage map 和 wave planning inputs。

## Scope（原有，保持不变——核心是 LLM planner + materializer，地基没做这些）

- node 内 DeerFlow agent loop，只允许读取 request/profile，不允许 web 或 phase mutation tools。
- structured output：topic id/slug/title/scope、must-answer bindings、search dimensions、exclusions。
- deterministic materializer 写 topic registry/seed artifacts，不让 LLM 拼 YAML/JSON。
- topic id/slug 稳定性、重复/重叠 topic、空 coverage 的 hard checks。
- semantic check：topic 集合是否覆盖 root must-answer 且不过度扩张。
- gate fail 将 overlap/missing coverage 反馈给同一 planner repair loop。
- rerun generation 的输入合同先保留，真实 invalidation 在 14 实现。

## 目标

用 bounded planner agent 把确认后的 brief/profile 转换成稳定 topic registry、must-answer coverage map 和 wave planning inputs。

## Scope

- node 内 DeerFlow agent loop，只允许读取 request/profile，不允许 web 或 phase mutation tools。
- structured output：topic id/slug/title/scope、must-answer bindings、search dimensions、exclusions。
- deterministic materializer 写 topic registry/seed artifacts，不让 LLM 拼 YAML/JSON。
- topic id/slug 稳定性、重复/重叠 topic、空 coverage 的 hard checks。
- semantic check：topic 集合是否覆盖 root must-answer 且不过度扩张。
- gate fail 将 overlap/missing coverage 反馈给同一 planner repair loop。
- rerun generation 的输入合同先保留，真实 invalidation 在 14 实现。

## 验收

- Replay model 覆盖正常、重复 topic、漏 must-answer、越界扩题、格式错误。
- planner 不能直接写 accepted evidence、work status 或 graph phase。
- materialized registry 与 state refs/hash 一致。
- mixed graph 到真实 topic planning 后进入 fake Wave0 并完成全链。

## Non-Goals

- 不创建 Wave0 WorkSpec，不搜索来源。
- 不实现 rerun 差异规划。

## 落地关联

08 只从 accepted topic registry 生成 Wave0 work，不重新解释用户范围。
