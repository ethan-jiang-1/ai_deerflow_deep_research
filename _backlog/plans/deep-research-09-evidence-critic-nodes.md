# Plan: Deep Research 09 - Evidence Critic Nodes

> 类型: 设计 | 更新: 2026-07-12
> 对应 OpenSpec change: `implement-deep-research-evidence-critic-nodes`
> 依赖: 03 Gate Kernel、04 Work Unit Kernel
> 替换范围: 新增 source diagnostic 与 claim verifier agent nodes，先用 fixtures 验证

## 地基已具备（来自 01）

- **node 位置**: 01 的 `targeted_evidence` package 已为 critic 预留位置；Wave0/Wave1 submit 后可直接插入 critic nodes。
- **tool policy 机制**: 01 的 per-node agent policy 可限制 critic 只读 assigned evidence。
- **gate 消费 critic verdict**: 03 的 GateResult schema 将包含 critic verdict 字段。

## 目标

建立独立于证据作者的 semantic quality layer，映射 DPT `source-diagnostic` 和 `claim-verifier` roles，供 Wave1、Wave2 和 readiness 复用。

## Scope

- SourceDiagnostic input/output：trust tier、materiality、marketing risk、cross-verification need。
- ClaimVerifier input/output：supported/weakened/contradicted/uncertain、support refs、counter refs、reason。
- 两类 node 都是 bounded DeerFlow agent loop，只读 assigned accepted evidence；默认不能写 ledger/phase。
- critic output 使用 versioned structured schema，确定性 materializer 写 review artifacts。
- critic 不是 hard authority：gate 根据 policy/threshold 消费 verdict。
- 作者与 critic 的 model/prompt/session 隔离；测试不能复用作者 self-assessment。
- conflicting critic results 形成 gap，不以多数票自动变成真相。

## 验收

- 用固定 evidence fixtures 覆盖支持、削弱、反驳、不足、营销材料和 prompt-injected source。
- 每个 verdict 必须引用 accepted source/claim ref；悬空引用 hard fail。
- critic 尝试 web/ledger mutation 被工具策略阻止。
- 输出可被 fake Wave1/Wave2/readiness gate 消费。

## Non-Goals

- 不实现 Wave1 extraction 或 targeted web search。
- 不决定最终 phase transition。

## 落地关联

10、12、15 依赖统一 critic contract，不能各自定义不兼容 verdict。
