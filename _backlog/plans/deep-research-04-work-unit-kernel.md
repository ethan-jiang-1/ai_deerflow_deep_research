# Plan: Deep Research 04 - Work Unit Kernel

> 类型: 设计 | 更新: 2026-07-10
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
- 只有 submit 成功才 append evidence submission ledger并更新 accepted refs。
- retry 创建新 attempt id；expired attempt 第一版 fail closed。
- cancellation、crash replay、same-hash idempotency、different-hash conflict。
- generic phase drain check：pending/in-flight 为零才能进入 phase gate。

## 验收

- 至少三个 fake workers 并行，reducer 不丢结果、不产生双 winner。
- worker 只说“完成”但无 result/file 时 submit 失败。
- 错 id、越界路径、hash mismatch、重复冲突全部 fail closed。
- crash 后已提交 attempt 幂等跳过，未提交 attempt 可重新执行。
- full fake graph 和 mixed graph 继续通过。

## Non-Goals

- 不实现真实 web worker、late-submit、20 项 active window 或动态优先级抢占。
- 不定义具体 wave evidence floor。

## 落地关联

Wave0、Wave1、targeted evidence 和 rerun 统一依赖此内核，不能建立第二条 delegated completion path。
