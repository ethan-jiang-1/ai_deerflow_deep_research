# Plan: Deep Research 04 - Work Unit Kernel

> 类型: 设计 | 更新: 2026-07-14
> 状态: OpenSpec apply-ready，全部 hard-done 门已通过，待归档
> 对应 OpenSpec change: `build-deep-research-work-unit-kernel`
> 依赖: 02 State Contracts、03 Gate Kernel
> 替换范围: fake fan-out/fan-in 和 fake submit，worker 内容仍为 fixture

## 地基已具备（来自 01）

- **`Send` fan-out/fan-in 已验证**: 01 的 Wave0/Wave1 fake subgraph 已实现三路 `Send` + fan-in，证明并行拓扑和 mixed-node contract 可行。
- **topology 中 wave subgraph 结构已定义**: `wave0/subgraph.py` 和 `wave1/subgraph.py` 已有 plan/worker/submit/gate 的分层结构。
- **fake worker 产出 fixture result/files**: 已能产出并 fan-in 到 submit node。
- **submit node 骨架**: 01 已有 submit node，负责收拢 worker 结果——但用的是 fake 直接 pass。

## 目标

把 DPT queue → work-unit → submit → ledger 的权威链映射为 LangGraph bounded `Send`、typed reducers 和 deterministic submit node。

## 已落地决策

- **三权威链**: checkpointed `ResearchState` 是 control truth；hash-chained `evidence/submissions.jsonl` 是 accepted-evidence truth；sandbox artifacts 是 content truth。accepted refs 只引用 ledger record hash，不复制 record。
- **compact state**: 保持 schema version 2 的单向兼容扩展，旧 checkpoint 缺字段时默认；活动窗口固定为 32 works / 64 attempts / 32 selected failures / 64 accepted refs，work block ≤ 40,960 bytes，whole checkpoint ≤ 65,536 bytes。
- **ledger/lock**: 选择 LF-only canonical JSONL + SHA256 hash chain；每 research 使用稳定 mode-0600 POSIX `flock`，同目录 mode-0600 staging、atomic replace、file/directory fsync。ledger 先发布，checkpoint 通过 replay catch-up。
- **replay unit**: 手动调用的 child graph 明确 `checkpointer=False`；整个 Wave node 是恢复单元。重启从最后 parent checkpoint 确定性重建 ids，先 reconcile ledger，再决定跳过、补 ref 或重跑未接受 attempt。
- **部署边界**: 第一版仅支持 parent sandbox 与 trusted host path 被运行时证明为同一 mounted POSIX workspace 的 provider。remote/provisioner/custom/unverified 模式 fail closed。
- **lifecycle 边界**: `start`/`resume` 在进入声明 controller capability 的 Wave 前异步构造 store；`status`/`cancel` 不初始化 parent sandbox，保持 checkpoint-only，因此 storage outage 不阻塞 cancel。
- **fixture 副作用**: Wave0/Wave1 只写 controller `work-spec.json`、worker `result.json`/声明 outputs、submit ledger/lock/staging；不写 cache、synthesis、review、final report，也不调用 model/web/MCP/ACP/task。
- **复用规则**: 后续真实 Wave、targeted evidence、rerun 只能替换 planner/worker/result-contract 内容，必须复用同一 component、validator、store、ledger、retry 和 drain 路径，不能建立第二条 delegated completion authority。

## Scope（缩减后——地基已覆盖 fan-out/fan-in 和 subgraph 结构）

- 定义 immutable WorkSpec、Attempt、CandidateResult、SubmissionRecord schemas。
- controller 分配 logical work id/attempt id；worker 不可自分配或改 spec。
- pending/in-flight/terminal state、batch cursor 和并发上限。
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
