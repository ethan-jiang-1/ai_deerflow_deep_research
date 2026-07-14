# Plan: Deep Research 05 - Bootstrap Node

> 类型: 设计 | 更新: 2026-07-12
> 状态: 已实现 (OpenSpec change `implement-deep-research-bootstrap-node`, 2026-07-15)
> 对应 OpenSpec change: `implement-deep-research-bootstrap-node`
> 依赖: 02 State Contracts、03 Gate Kernel
> 替换范围: fake bootstrap node（`agent/src/deerflow_deep_research/graph/nodes/bootstrap/fake.py`）

## 地基已具备（来自 00 + 01）

以下已由 01 的 fake bootstrap node 实现，**本 plan 只做升级，不重做**：

- **identity 派生**: user/thread → domain-separated opaque `research_id`，模型不能覆盖——已实现。
- **original question 绑定**: 从 runtime 最新真实 `HumanMessage` 读取原文和 stable message id——已实现。
- **start 幂等与冲突检测**: 同消息重试恢复同一 lifecycle，同 thread 已有 active run 拒绝新 start——已实现。
- **generation 0 初始化**: 01 fake bootstrap 已写入初始 control state。
- **directory/bundle 创建**: 01 fake bootstrap 已创建最小 bundle 目录。
- **HumanMessage 文本为唯一权威**: 不接受 tool payload 中伪造的 question。

## 目标

将 fake bootstrap 升级为 real bootstrap：原子目录创建、schema/version marker、real gate。**不再重新设计 identity 派生或 start 语义。**

## Scope（缩减后）

- **原子创建**最小 bundle 目录与 schema/version marker（01 fake 是非原子的简单 mkdir）。
- **bootstrap gate** 验证目录、state、checkpoint/bundle binding——替换 fake 的 fixture pass。
- 失败只做确定性清理/重试，不调用研究 LLM。
- 检测同 thread 已有 active/completed research 的 edge cases（partial directory recovery）。

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
