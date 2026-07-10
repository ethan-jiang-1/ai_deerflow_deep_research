# Plan: Deep Research 08 - Wave0 Node

> 类型: 设计 | 更新: 2026-07-10
> 对应 OpenSpec change: `implement-deep-research-wave0-node`
> 依赖: 04 Work Unit Kernel、07 Topic Planning Node
> 替换范围: fake Wave0 plan/worker/submit/gate/repair subgraph

## 目标

实现每 topic 的基础来源摄入和共享参考层，对应 DPT Wave0 的广度优先证据建立。

## Scope

- Wave0 planner 从 topic/profile 生成 immutable source-intake WorkSpecs。
- source-intake worker 使用受限 DeerFlow agent loop：web search/fetch、assigned cache/output writes。
- candidate result 包含 canonical URL、source metadata、baseline facts、fetch/cache refs、limitations。
- submit validator 做 URL canonicalization、真实 fetch/cache、path/hash、source identity 检查。
- Wave0 gate：per-topic source floor、独立来源、重复计数、fetch/degraded capture、drain。
- source 不可访问时走明确 degraded-capture contract，不伪造成功。
- repair loop 可补搜缺失 topic，但不能手写 submission ledger。

## 验收

- 可访问来源 happy path、重复 URL、搜索 snippet 冒充 evidence、空 cache、错 topic binding 均覆盖。
- worker 最终文本不计 coverage，只有 accepted SubmissionRecord 计数。
- 并发 topic workers 不跨 attempt 目录写入。
- mixed graph 使用真实 Wave0、后续 fake，repair path 与 restart E2E 通过。

## Non-Goals

- 不做深度 claim extraction、cross-topic synthesis 或 source semantic critic。
- 不让 Wave0 来源自动满足 Wave1 new-source floor。

## 落地关联

09 使用 Wave0 fixtures/accepted submissions 训练 critic contracts；10 以 Wave0 作为背景输入。
