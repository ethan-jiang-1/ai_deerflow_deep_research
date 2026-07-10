# Plan: Deep Research 02 - State And Persistence Contracts

> 类型: 设计 | 更新: 2026-07-10
> 对应 OpenSpec change: `define-deep-research-state-persistence-contracts`
> 依赖: 01 Fake Graph Skeleton
> 替换范围: fake state/checkpoint payload，不替换业务 node

## 目标

把骨架中的临时字典升级为 versioned typed ResearchState，固定 graph control truth、sandbox content refs 和 evidence authority 的边界。

## Scope

- 定义 ResearchState：identity、request、control、planning、work、quality、delivery。
- 定义 phase/terminal/waiting/work status enums 和 schema version/migration policy。
- 实现 reducers：work terminal monotonicity、duplicate hash idempotency、conflict detection、ref dedupe。
- 规定大内容不进 checkpoint，只存 path/hash/schema version/短摘要。
- 定义最小 research bundle layout 和 path containment contract。
- 明确三种权威：checkpoint control state、validated submission ledger、sandbox artifact content。
- 封装 nested checkpoint namespace、user/thread/research id 派生和 provider lifecycle。
- 为 memory/sqlite/postgres 建 contract tests；本 change 可只在 CI 集成环境验证可用 backend。

## 状态不变量

- 一次只存在一个合法 phase/waiting state。
- terminal state 不回退；generation 只单调递增。
- worker 不能写 gate feedback、phase 或 accepted submissions。
- 同 work/attempt 相同 hash 重放幂等，不同 hash 标 conflict。
- schema 不兼容时停止并要求 migration，不静默重置。

## 验收

- fake graph 全部改用 typed state 后路径不变。
- checkpoint size 有硬测试，大 artifact 写入 state 会失败。
- restart、resume、duplicate update、parallel reducer property tests 通过。
- SQLite 单进程和 Postgres 多 worker 的 namespace/isolation 行为有验证。

## Non-Goals

- 不实现 gate 规则、WorkSpec 或真实 bundle artifact。
- 不做业务 state migration；只建立版本与 fail-closed 合同。

## 落地关联

03、04 和所有真实 node 都依赖这里冻结的 state ownership。后续扩字段必须显式说明 writer、reader 和 reducer。
