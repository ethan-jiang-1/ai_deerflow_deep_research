# Plan: Deep Research 15 - Readiness Node

> 类型: 设计 | 更新: 2026-07-10
> 对应 OpenSpec change: `implement-deep-research-readiness-node`
> 依赖: 09 Evidence Critics、13 HITL2 Node
> 替换范围: fake readiness gate/repair router

## 目标

在最终写作前建立 answerability、citation closure 和 limitation completeness 的强门禁，保证 writer 只接收可交付 evidence projection。

## Scope

- 每个 root must-answer 生成 ready_substantive / ready_insufficient_judgment / blocked_repair_required。
- major claims 的 independent backing、critic verdict、confidence 与 limitation 检查。
- citation closure：claim → accepted submission → source/cache 双向可解析。
- HITL2 decision 必须属于当前 generation/brief hash。
- report plan 投影包含可写结论、必须保留的不确定性、禁止强化的 claim。
- readiness gate collect-all；repair route 只能回 targeted evidence/synthesis/HITL2 合法节点。
- provenance/schema/dangling refs 永不 degraded pass。

## 验收

- 实质可答、证据不足但可交付判断、必须补证三类路径都有 fixtures。
- dangling citation、unsupported major claim、旧 HITL2 decision、遗漏 limitation 全部拒绝。
- semantic critic 与 hard check 冲突时 fail closed/形成 gap。
- mixed graph 通过真实 readiness 后进入 fake final；repair edges 正确。

## Non-Goals

- 不写最终报告，不展示 artifacts。
- 不允许用户 proceed 直接覆盖 readiness failure。

## 落地关联

16 只能读取 readiness 生成的 immutable report plan，不重新扫描裸 evidence 决定可写内容。
