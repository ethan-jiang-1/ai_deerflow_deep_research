# Plan: Deep Research 11 - Wave2 Synthesis Node

> 类型: 设计 | 更新: 2026-07-10
> 对应 OpenSpec change: `implement-deep-research-wave2-synthesis-node`
> 依赖: 10 Wave1 Node
> 替换范围: fake pure-synthesis node；targeted search 仍为 fake

## 目标

实现只基于既有 accepted evidence 的跨 topic 综合，严格区分“纯综合”与“获取新证据”。

## Scope

- synthesis agent 只获得 read tools 和 synthesis assigned writes，实际不绑定 web search/fetch。
- 输入由代码投影 accepted claims/verdicts/limitations，不让 Agent 自扫裸文件决定权威。
- structured outputs：finding index、cross-topic relations、contradictions、resolutions、candidate gaps。
- finding 带 priority、affected topics、backing refs、confidence、search_required、decision。
- deterministic materializer 生成 synthesis.md、finding index 和 cross-topic ledger。
- hard gate 检查引用/结构/accepted backing；semantic gate 检查因果强度、矛盾遗漏和 must-answer coverage。
- 需要新证据的 finding 只进入 gap state，不允许 synthesis node 暗搜。

## 验收

- synthesis 尝试 web tool 确定性失败。
- finding 引用裸文件、unsubmitted claim、dangling source 时 gate 拒绝。
- 相关性误写成因果、忽略反证、遗漏高优先级 must-answer 有 critic fixtures。
- mixed graph 使用真实 synthesis，fake targeted/HITL2/final 完成 E2E。

## Non-Goals

- 不执行 targeted evidence、不判断 HITL2 decision。
- 不把 report prose 当 finding index 替代品。

## 落地关联

12 消费 candidate gaps 并把补证结果反馈回同一 synthesis node 收敛。
