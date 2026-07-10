# Plan: Deep Research 04 - Work Unit Kernel

> 类型: 设计 | 更新: 2026-07-11
> 对应 OpenSpec change: `build-deep-research-work-unit-kernel`
> 依赖: 02 State Contracts、03 Gate Kernel
> 替换范围: fake fan-out/fan-in 和 fake submit，worker 内容仍为 fixture

## 目标

把 DPT queue → work-unit → submit → ledger 的权威链映射为 LangGraph bounded `Send`、typed reducers 和 deterministic submit node。

## Scope

- 定义 immutable WorkSpec、Attempt、CandidateResult、SubmissionRecord schemas。
- controller 分配 logical work id/attempt id；worker 不可自分配或改 spec。
- pending/in-flight/terminal state、batch cursor 和并发上限。
- `Send` fan-out/fan-in，使用 fake worker 产出 fixture result/files。
- submit validator 检查 identity、spec hash、schema、path、file hash、source refs。
- 只有 deterministic controller submit node 能 append evidence submission ledger 并更新 accepted refs；planner/worker/repair agent 只返回 candidate，不直接写 ledger。
- 明确 ledger storage 选择与事务边界：append record、update accepted refs、checkpoint state 的 crash window 必须有 idempotent replay protocol。
- per-research serialization 或等价 optimistic concurrency 必须在本 change 落地；不能把同一 research 的多进程 submit race 留到 17。
- retry 创建新 attempt id；expired attempt 第一版 fail closed。
- cancellation、crash replay、same-hash idempotency、different-hash conflict。
- generic phase drain check：pending/in-flight 为零才能进入 phase gate。

## 验收

- 至少三个 fake workers 并行，reducer 不丢结果、不产生双 winner。
- worker 只说“完成”但无 result/file 时 submit 失败。
- 错 id、越界路径、hash mismatch、重复冲突全部 fail closed。
- crash 后已提交 attempt 幂等跳过，未提交 attempt 可重新执行。
- fault-injection 覆盖 crash between ledger append and checkpoint、checkpoint before publish-ref、replay same record、replay divergent record。
- 多进程/多实例 race contract test 证明同一 work/attempt 最多一个 accepted winner；失败路径不能产生半条 ledger。
- full fake graph 和 mixed graph 继续通过。

## Non-Goals

- 不实现真实 web worker、late-submit、20 项 active window 或动态优先级抢占。
- 不定义具体 wave evidence floor。

## 落地关联

Wave0、Wave1、targeted evidence 和 rerun 统一依赖此内核，不能建立第二条 delegated completion path。
