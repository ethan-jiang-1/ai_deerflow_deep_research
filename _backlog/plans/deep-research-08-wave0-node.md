# Plan: Deep Research 08 - Wave0 Node

> 类型: 设计 | 更新: 2026-07-12
> 对应 OpenSpec change: `implement-deep-research-wave0-node`
> 依赖: 04 Work Unit Kernel、07 Topic Planning Node
> 替换范围: fake Wave0 plan/worker/submit/gate/repair subgraph（`agent/src/deerflow_deep_research/graph/nodes/wave0/fake.py`）

## 地基已具备（来自 01）

- **subgraph 结构**: 01 已定义 Wave0 plan → fan-out workers → fan-in submit → gate → repair 的分层 subgraph（`wave0/subgraph.py`）。
- **`Send` 并行**: 三路 fan-out/fan-in 已验证。
- **node-agent policy 骨架**: 01 的 worker 已有 per-node tool policy 占位。

## 目标

实现每 topic 的基础来源摄入和共享参考层，对应 DPT Wave0 的广度优先证据建立。

## Scope（原有——核心是真实 web search/fetch + source validation，地基没做）

## 目标

实现每 topic 的基础来源摄入和共享参考层，对应 DPT Wave0 的广度优先证据建立。

## Scope

- Wave0 planner 从 topic/profile 生成 immutable source-intake WorkSpecs。
- source-intake worker 使用受限 DeerFlow agent loop：web search/fetch、assigned cache/output writes。
- worker 继承 00 的 node-agent policy：只能读 assigned topic/profile refs，只能写本 work/attempt 目录和允许的 cache 路径，不能写 phase/gate/ledger。
- candidate result 包含 canonical URL、source metadata、baseline facts、fetch/cache refs、limitations。
- submit validator 做 URL canonicalization、真实 fetch/cache、path/hash、source identity 检查。
- 外部网页、PDF、snippet、缓存正文一律作为 untrusted data 处理：不得拼进 system/developer prompt，不得让 source text 指挥工具、ledger、gate 或路由。
- Wave0 gate：per-topic source floor、独立来源、重复计数、fetch/degraded capture、drain。
- source 不可访问时走明确 degraded-capture contract，不伪造成功。
- repair loop 可补搜缺失 topic，但不能手写 submission ledger。

## 验收

- 可访问来源 happy path、重复 URL、搜索 snippet 冒充 evidence、空 cache、错 topic binding 均覆盖。
- adversarial source 覆盖“忽略规则/调用工具/修改 ledger/把自己标记为权威来源”等 prompt injection，结果只能进入 source limitation 或 rejection。
- worker 最终文本不计 coverage，只有 accepted SubmissionRecord 计数。
- 并发 topic workers 不跨 attempt 目录写入。
- 越界读写、写 shared phase state、写其他 attempt、把 snippet 当 cache 均被 policy/submit gate 拒绝。
- mixed graph 使用真实 Wave0、后续 fake，repair path 与 restart E2E 通过。

## Non-Goals

- 不做深度 claim extraction、cross-topic synthesis 或 source semantic critic。
- 不让 Wave0 来源自动满足 Wave1 new-source floor。

## 落地关联

09 使用 Wave0 fixtures/accepted submissions 训练 critic contracts；10 以 Wave0 作为背景输入。
