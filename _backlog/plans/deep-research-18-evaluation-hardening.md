# Plan: Deep Research 18 - Evaluation And Production Hardening

> 类型: 设计 | 更新: 2026-07-16
> 对应 OpenSpec change: `evaluate-harden-deep-research-graph`（待 proposal）
> 依赖: 17 Runtime Operations（待 proposal）
> 替换范围: 全链路 release gate，不新增主要 workflow phase

## 地基已具备（来自 00–13 全链路 + 所有前置 change）

- **完整 graph 可评估**: 01 的 full-fake graph 提供所有 node/edge 用于故障注入；08–13 的 real nodes 提供真实搜索/证据/批评/综合/HITL 行为用于质量评估。两个 implementation 模式下都已有可重复的 E2E 路径。
- **contract test 基础设施**: 00/01 的 contract 和 integration test 模式已在 08–13 中大量使用。09（critics）和 11（synthesis）的零 API agent test（FakeToolCallingModel/ReplayChatModel）可直接复用到 eval corpus 的 claim verification 和 adversarial source scenarios。
- **checkpoint recovery 已验证**: memory + file-SQLite 跨进程恢复已在 01、03、06、13 的 interrupt/resume 测试中反复验证。
- **topology snapshot**: `topology_snapshot.py` CI 检查可保证 node/edge 闭集，防止意外变更。
- **新增可评估面**: 08–13 的 real nodes 暴露了具体质量维度——citation precision（wave0/wave1 submit validation）、must-answer coverage（topic planning → wave2 synthesis gap planner）、source diversity（wave0 URL canonicalization）、contradiction recall（wave1 counterevidence + evidence critics）。这些都已有 structured output schema，可直接量化。

## 目标

用可重复 eval corpus 和故障注入证明 graph 的质量、恢复、成本与安全边界，形成可发布而非“能跑”的 Deep Research 基线。

## Scope

- 建立 quick factual、exploratory map、claim verification、current events、insufficient evidence corpus。
- adversarial sources：SEO spam、营销材料、prompt injection、重复转载、页面消失/付费墙。
- metrics：citation precision/completeness、unsupported major claim、must-answer coverage、contradiction recall、source diversity。
- runtime metrics：resume correctness、repair convergence、tokens、cost、wall time、fetch count、worker retries。
- graph edge/node fault matrix：crash、timeout、cancel、duplicate resume、conflicting result、DB transient failure。
- quality regression thresholds 和 release gate；固定 Replay fixtures 与少量 `@requires_llm` canary 分层。
- multi-worker Postgres/concurrency/security review、operator runbook、migration rehearsal。
- 对照 DPT invariants 做 parity audit，不按文件数量做 parity。

## 验收

- 零 API deterministic suite 是 hard CI gate；real-LLM canary 有明确成本和非阻塞/阻塞策略。
- insufficient evidence case 能输出“不足以判断”，不强行结论。
- prompt-injected source 不能获得控制权或伪造 submission。
- 所有 critical fault points 有恢复或明确 terminal outcome，不产生 silent partial success。
- 发布报告列出已达到与未达到的 DPT invariant parity。

## Non-Goals

- 不用单次 demo 或主观阅读代替评估。
- 不在本 change 扩展新 phase/role，发现结构缺口时回到对应 plan/change 修复。

## 落地关联

此 plan 是首个完整版本的 release gate。完成后主架构 plan 才可被 change/spec 吸收并归档。
