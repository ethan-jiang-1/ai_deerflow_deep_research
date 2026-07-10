# Plan: Deep Research 05 - Bootstrap Node

> 类型: 设计 | 更新: 2026-07-10
> 对应 OpenSpec change: `implement-deep-research-bootstrap-node`
> 依赖: 02 State Contracts、03 Gate Kernel
> 替换范围: fake bootstrap node

## 目标

确定性建立一次 research run 的身份、目录、原始请求和初始控制状态，对应 DPT instantiation + setup，但不让 Agent 手工创建控制文件。

## Scope

- 从 outer runtime 派生 user/thread/research id，拒绝模型提供越权 identity。
- 保存 original question 的原文和 hash，建立 generation 0。
- 原子创建最小 bundle 目录与 schema/version marker。
- 初始化 phase、repair budgets、空 work/quality/delivery state。
- 检测同 thread 已有 active/completed research，定义 start 幂等和冲突行为。
- bootstrap gate 验证目录、state、checkpoint/bundle binding。
- 失败只做确定性清理/重试，不调用研究 LLM。

## 验收

- 新建、重复 start、并发 start、已有 completed run 四类行为明确。
- partial directory creation 可恢复，不留下被误认成 active 的 bundle。
- path/user/thread isolation 和 schema mismatch tests 通过。
- mixed graph 中只替换 bootstrap，其余节点保持 fake 并完成 E2E。

## Non-Goals

- 不做 topic rewrite、profile 推导或用户提问。
- 不创建 DPT 的冗余 `rb_status.json` phase cursor。

## 落地关联

06 HITL1 只接收 bootstrap 已绑定的原始请求和 research identity。
