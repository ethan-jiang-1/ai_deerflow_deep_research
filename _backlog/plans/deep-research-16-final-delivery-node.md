# Plan: Deep Research 16 - Final Delivery Node

> 类型: 设计 | 更新: 2026-07-16
> 对应 OpenSpec change: `implement-deep-research-final-delivery-node`（待 proposal）
> 依赖: 15 Readiness Node（待 proposal）
> 替换范围: fake final writer、integrity gate、artifact publish（`agent/src/deerflow_deep_research/graph/nodes/final_delivery/fake.py`）

## 地基已具备（来自 01 + 08–13 实际实现）

- **node 位置**: 01 的 final delivery node 已是 graph 的 terminal sink，readiness → final → END 路径通。
- **terminal marker**: 01 的 fake final 返回 `implementation_mode=full_fake` terminal fixture，已走通 completed 后的幂等行为。
- **lifecycle 合同**: 01 的 control-result envelope 已标准化 action 返回格式。
- **writer agent 模式已验证**: 09（critics）、11（synthesis）的 read-only agent loop（禁止 web，只读 accepted evidence，写 assigned paths）已在实际中运行。Final writer 是这个模式的直接复用：只读 readiness-approved report plan，写 report.md + claim-citation-map。
- **integrity gate 可复用 03 gate kernel**: 03 的 hard gate rules（schema/identity/path containment/hash match）已在此前 wave gates 中验证。Final integrity gate 只需加 claim→citation 双向闭合检查。

## 目标

用受限 writer agent 将 readiness-approved report plan 投影为最终报告，并在发布前证明没有引入 ledger 外事实或悬空引用。

## Scope

- writer agent 只读 report plan/accepted refs，允许写 assigned final paths，不允许 web。
- 输出 report.md 和 machine-readable claim-citation-map。
- final integrity gate 双向检查 report claims/citations/map/submission ledger。
- 结论强度不得高于 critic verdict；insufficient/uncertain 必须保留限定语。
- writer gate fail 回同一 writer repair，不回搜索；需要新证据时 blocked 回 readiness 路由。
- final hash/metadata 固定；先在 research workspace 验证，再原子发布到 `/mnt/user-data/outputs/deep-research/<research_id>/`。
- publish 必须 copy verified `report.md`、claim-citation-map 和 metadata 到 outputs path，重新校验 hash/path，再调用现有 `present_files`；不得直接 present workspace path。
- completed 后 start/status/resume/cancel 行为幂等且不重写报告。

## 验收

- writer 引入新事实、丢 limitation、悬空 citation、map 不一致、试图 web search 均被拒。
- final repair 后通过且 report hash 稳定。
- workspace-to-outputs copy 是 atomic/幂等；hash mismatch、partial copy、outputs 外路径、直接 workspace `present_files` 全部 fail closed。
- 从真实 bootstrap 到真实 final 的全 real interactive happy path 零 API Replay E2E 通过。
- artifact 列表和用户最终消息只在 final gate pass 后出现。

## Non-Goals

- 不做 PDF/多格式渲染或前端定制。
- 不在 writer 中补搜证据。

## 落地关联

17 在完整 graph 上补运行时策略；18 才对报告质量做基准评估和发布门槛。
