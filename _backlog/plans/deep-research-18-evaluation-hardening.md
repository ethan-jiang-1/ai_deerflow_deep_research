# Plan: Deep Research 18 - Evaluation And Production Hardening

> 类型: 设计 | 更新: 2026-07-12
> 对应 OpenSpec change: `evaluate-harden-deep-research-graph`
> 依赖: 17 Runtime Operations
> 替换范围: 全链路 release gate，不新增主要 workflow phase

## 地基已具备（来自 00 + 01 + 所有前置 change）

- **完整 graph 可评估**: 01 的 full-fake graph 已提供所有 node/edge，可直接用于故障注入和 recovery 测试。
- **contract test 基础设施**: 00/01 的 contract 和 integration test 模式可直接复用到 eval corpus。
- **checkpoint recovery 已验证**: memory + file-SQLite 跨进程恢复可用于 crash/recovery scenario。
- **topology snapshot**: `topology_snapshot.py` CI 检查可保证 node/edge 闭集，防止意外变更。

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
