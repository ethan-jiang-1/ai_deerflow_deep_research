# DPT Run Bundle 结构 — 详细分析

> 从 `ai_tool_deepresearch` 分析，用于在 DeerFlow 上重实现。
> 主控文档: [../dpt-to-deerflow-mapping.md](../dpt-to-deerflow-mapping.md)

## 概述

DPT 的 run bundle 是每次 deep research 执行的**唯一 mutable runtime truth 根**。它与只读的 `DPT_FRAMEWORK/` 严格分离。

## 三种坐标

```
repo_command_root   = 执行 node DPT_FRAMEWORK/... 的仓库根（只是命令位置）
framework_root       = DPT_FRAMEWORK/（只读 reusable assets）
active_bundle_root   = dpt_rb_* 或 dpt_disp_*（唯一 mutable runtime truth）
```

裸 runtime path（如 `rb_queue.json`）默认以 active bundle root 为根。

## Production Bundle: `dpt_rb_<name>/`

```
dpt_rb_<name>/
├── BUNDLE_MAP.md              # Passive map of bundle contents
├── rb_plan.md                 # Research question + topic_registry frontmatter
├── rb_profile.yaml            # HITL decisions: research style, thresholds
├── rb_status.json             # Phase/gate status: current_node, current_gate, run_state
├── rb_queue.json              # Queue state: active window + refill pool + in-flight + history
├── rb_trace.jsonl             # Append-only audit trail
│
├── _logs/                     # Runtime logs
│   └── run.log
│
├── seed_topics/               # Initial topic discovery output
├── reference/                 # Shared reference files (00-shared-*.md)
├── artifacts/
│   ├── wave0/                 # Per-topic source.yaml
│   ├── wave1/                 # Per-topic deep evidence
│   └── wave2/                 # Synthesis + cross-validation
├── final/                     # Final report output
├── _cache/                    # Cached gate results, projections
│   ├── gate-results/
│   └── projections/
├── _checkpoints/              # Phase transition witnesses
├── _diagnostics/              # Audit diagnostic output
└── _work_units/               # Delegated sub-agent work
    ├── _index.json            # Attempt-state registry
    └── waveN/{work_id}/       # Per work-unit directory
        ├── manifest.json
        ├── task.md
        ├── result.schema.json
        ├── _beacon.json
        ├── runtime-receipt.jsonl
        └── (result files)
```

## Disposable Experiment Bundle: `dpt_disp_<name>_<hex>/`

结构同 production bundle，但用于实验。Automatically suffixed with hex to avoid collision.

## 5 个 Control Files

### rb_plan.md
- 研究问题写在正文
- Frontmatter 含 `topic_registry`（topic 列表，含 slug/title/status）
- Phase Agent 从这里读 topic 列表来生成 queue demand

### rb_profile.yaml
- `research_profile`: quick_factual | exploratory_map | claim_verification | debug
- `research_style_params`: 每个 wave 的 source floor、shared ref total 等阈值
- `search_preference`: 搜索偏好
- HITL1 时由用户确认，之后 Phase Agent 据此配置各 wave 的 demand

### rb_status.json
```json
{
  "current_node": "phases/phase-wave0.md",
  "current_gate": "wave0_complete",
  "run_state": "in_progress",
  "stop_authorization_state": "unauthorized_continue_required"
}
```
- `current_node`: 当前活跃的 phase node fileRef。为 null 时表示需要 reentry 诊断。
- `current_gate`: 当前 phase 对应的 gate enum 值
- `run_state`: not_started | in_progress | blocked | completed
- `stop_authorization_state`: 是否可以停（只 final_delivery / decision_blocker / empty_queue_after_refill 可以停）

### rb_queue.json
- Queue v2 state: active window (当前活跃的 demand items), refill pool, delegated in-flight, terminal history
- 每个 item: `queue_item_id`, `kind`, `priority_class`, `action`, `writes_to`, `required_receipts`

### rb_trace.jsonl
- Append-only JSONL
- 每行一个 trace event: gate attempt, queue operation, work-unit lifecycle, phase transition, repair attempt
- Agent 通过读 trace 恢复上下文（而不是靠 chat memory）

## Framework 与 Bundle 的读写边界

| 操作 | 写到哪里 |
|------|---------|
| HITL answer / profile decision | bundle `rb_profile.yaml` |
| Gate pass/fail result | bundle `_cache/gate-results/` |
| Trace entry | bundle `rb_trace.jsonl` |
| Repair attempt | bundle `rb_status.json` + trace |
| Research artifact | bundle `artifacts/` |
| Final output | bundle `final/` |
| Work-unit attempt | bundle `_work_units/` |
| Runtime log | bundle `_logs/` |

**绝对不能写回 `DPT_FRAMEWORK/`。**

## 实例化

```bash
node DPT_FRAMEWORK/cli/instantiate-run-bundle.mjs <name>
```

创建 `dpt_rb_<name>/`，materialize 初始模板：
- 5 个 `rb_*` control files（空/默认值）
- Canonical scaffold 目录（seed_topics, reference, artifacts, final, _cache）
- `BUNDLE_MAP.md`
- 如果目标目录已存在 → 报错停止（不可覆盖）

## → DeerFlow 映射

```
dpt_rb_<name>/  →  DeerFlow thread sandbox /home/user/_bundle/

- Thread isolation 天然隔离不同 research run
- Sandbox 文件系统承载所有 bundle 文件
- rb_status.json + rb_trace.jsonl 使 Agent 可断点续跑
- checkpointer (SQLite) 持久化 thread 状态
- 不需要额外的 bundle 管理 CLI——用 sandbox 的 ls/read_file/write_file 工具
```

唯一的差异：DPT 的 `instantiate-run-bundle.mjs` 是一个 CLI 一次性创建 bundle。
在 DeerFlow 上，可以由 Phase Agent 在 phase-instantiation 时直接用 sandbox 工具创建目录和文件，
或者提供一个 `dpt_bundle_init` Python tool 来做。
