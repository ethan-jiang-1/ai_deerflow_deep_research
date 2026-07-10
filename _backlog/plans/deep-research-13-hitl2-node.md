# Plan: Deep Research 13 - HITL2 Node

> 类型: 设计 | 更新: 2026-07-10
> 对应 OpenSpec change: `implement-deep-research-hitl2-node`
> 依赖: 03 Gate Kernel、12 Targeted Evidence Loop
> 替换范围: fake HITL2 decision node

## 目标

把通过 Wave2 gate 的 findings、限制和补证方向形成 decision brief，并以 typed interrupt 记录用户的 proceed/revise/repair/rerun/stop 决策。

## Scope

- deterministic brief builder 从 accepted finding/quality state 生成展示数据。
- decision brief 明确：已确认结论、关键不确定性、未解决 gaps、成本/补证选项。
- interrupt 前先 checkpoint `pending_user` 和 brief hash，保证断线可恢复。
- closed decisions：proceed、revise_view、repair、rerun、stop_blocked。
- resume 绑定 research id/generation/brief hash/request id，拒绝旧 generation 回答。
- revise_view 只回 synthesis projection；repair 回 targeted loop；rerun 交给 14；proceed 到 readiness。
- 用户 proceed 不能绕过后续 hard gate。

## 验收

- 五种 decision edge、自由文本解析、重复/过期回答、restart resume 全覆盖。
- brief 内容只能引用 accepted findings，不能临时生成新事实。
- state 先记录 pending 再展示 interrupt，有 fault-injection test。
- mixed graph 使用真实 HITL2 后可分别进入 fake rerun/readiness/stop。

## Non-Goals

- 不实现 rerun invalidation、readiness 或 final。
- 不在本 change 实现 scheduled auto decision。

## 落地关联

14 和 15 可在本 change 后并行；两者消费同一 typed HITL2 decision contract。
