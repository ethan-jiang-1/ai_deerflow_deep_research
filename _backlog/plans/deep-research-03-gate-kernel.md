# Plan: Deep Research 03 - Gate Kernel

> 类型: 设计 | 更新: 2026-07-10
> 对应 OpenSpec change: `build-deep-research-gate-kernel`
> 依赖: 02 State And Persistence Contracts
> 替换范围: fake gate outcome router，业务 rule 仍使用 fixtures

## 目标

实现所有 phase 共用的 deterministic gate/repair 内核，保留 DPT collect-all、inspect/advice、attempt/fatigue 和不可假通过的合同。

## Scope

- 定义 GateDefinition、GateRule、GateResult、stable failure code。
- rule evaluation 收集所有失败，区分 hard、semantic、repairable、degradable。
- GateResult 固定输出 verdict、codes、inspect、advice、failed_refs、attempt、remaining budget。
- gate node 是 phase transition outcome 的唯一 writer；agent node 无权写 pass。
- generic repair loop 把完整 feedback 投影给 repair agent，再回同一 gate。
- attempt/failure fingerprint/fatigue escalation 写入 typed state。
- provenance/schema/identity 类 rule 永不 degraded pass。
- 用 fixture rule 替换 skeleton 中的直接 outcome switch，保留全图路径。

## 验收

- collect-all 顺序稳定，同一输入产生相同 failure fingerprint。
- pass、repair、blocked、needs_human 四类 edge 均由 typed verdict 路由。
- 超过 repair budget 后按定义 blocked/degraded，不无限循环。
- fake repair node 能读完整 inspect/advice 并使下一次 gate 通过。
- graph topology 不因 gate kernel 引入隐藏 transition。

## Non-Goals

- 不实现 Wave0/Wave1/Wave2/readiness 的具体 rules。
- 不让 LLM critic 直接成为 hard gate authority。

## 落地关联

所有真实 phase change 只新增 phase-specific definitions/rules，不各自重写 retry loop。
