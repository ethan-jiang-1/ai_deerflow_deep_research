# Plan: Deep Research 12 - Targeted Evidence Loop

> 类型: 设计 | 更新: 2026-07-12
> 对应 OpenSpec change: `implement-deep-research-targeted-evidence-loop`
> 依赖: 04 Work Unit Kernel、09 Evidence Critics、11 Wave2 Synthesis
> 替换范围: fake gap planner、targeted workers、Wave2 convergence gate（`agent/src/deerflow_deep_research/graph/nodes/targeted_evidence/fake.py`）

## 地基已具备（来自 01）

- **循环边**: 01 已定义 synthesis → targeted evidence → back-to-synthesis 的收敛回边。
- **fan-out 复用**: targeted workers 复用 04 的 `Send` 机制（01 已验证）。

## 目标

为 Wave2 中明确需要新证据的 finding 建立有界补证循环，并在每轮 submit/critic 后重新综合直到 pass、defer 或 blocked。

## Scope

- deterministic gap router 只接受 finding index 中 `search_required` gaps。
- gap planner agent 把每个 gap 转为 bounded targeted WorkSpec，不扩成全 topic 搜索。
- targeted worker 只获得 assigned gap 的 web/search/fetch 和 scoped writes。
- submit 后运行 source/claim critics，更新 finding backing/gap status。
- 回到 synthesis node重新投影 findings；不是在 targeted worker 内直接改 synthesis。
- Wave2 gate：P0/P1 independent backing、gap closed states、search submission coverage、drain。
- round/attempt/token/fetch budgets 由 state 强制；耗尽时 explicit defer/blocked。

## 验收

- 无 gap 直接过 gate；有 gap 补证后收敛；不可解决 gap 显式 defer；重复相同失败触发 fatigue。
- targeted worker 搜索未分配 topic、直接改 finding/ledger 或返回裸 URL 均被拒。
- `pure_synthesis_eligible` 由代码导出，Agent 不能自填 true。
- mixed graph 到真实 Wave2 gate 后进入 fake HITL2，restart/cancel/retry E2E 通过。

## Non-Goals

- 不实现用户 HITL2 选择或 rerun generation。
- 不做全局报告写作。

## 落地关联

13 只展示当前 generation 已通过 Wave2 gate 的 decision brief。
