# Plan: Deep Research 16 - Final Delivery Node

> 类型: 设计 | 更新: 2026-07-10
> 对应 OpenSpec change: `implement-deep-research-final-delivery-node`
> 依赖: 15 Readiness Node
> 替换范围: fake final writer、integrity gate、artifact publish

## 目标

用受限 writer agent 将 readiness-approved report plan 投影为最终报告，并在发布前证明没有引入 ledger 外事实或悬空引用。

## Scope

- writer agent 只读 report plan/accepted refs，允许写 assigned final paths，不允许 web。
- 输出 report.md 和 machine-readable claim-citation-map。
- final integrity gate 双向检查 report claims/citations/map/submission ledger。
- 结论强度不得高于 critic verdict；insufficient/uncertain 必须保留限定语。
- writer gate fail 回同一 writer repair，不回搜索；需要新证据时 blocked 回 readiness 路由。
- final hash/metadata 固定，publish 通过现有 artifacts/present_files 通道。
- completed 后 start/status/resume/cancel 行为幂等且不重写报告。

## 验收

- writer 引入新事实、丢 limitation、悬空 citation、map 不一致、试图 web search 均被拒。
- final repair 后通过且 report hash 稳定。
- 从真实 bootstrap 到真实 final 的全 real interactive happy path 零 API Replay E2E 通过。
- artifact 列表和用户最终消息只在 final gate pass 后出现。

## Non-Goals

- 不做 PDF/多格式渲染或前端定制。
- 不在 writer 中补搜证据。

## 落地关联

17 在完整 graph 上补运行时策略；18 才对报告质量做基准评估和发布门槛。
