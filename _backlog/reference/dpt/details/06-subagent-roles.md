# DPT Subagent Roles — 详细分析

> 从 `ai_tool_deepresearch` 分析，用于在 DeerFlow 上重实现。
> 主控文档: [../dpt-to-deerflow-mapping.md](../dpt-to-deerflow-mapping.md)
> 相关: [02-engine.md](02-engine.md) · [05-phases.md](05-phases.md)
>
> **DPT 源文件**: `DPT_FRAMEWORK/workflows/nodes/phases/subagent-dpt-*.md` (5 个 role spec), `DPT_FRAMEWORK/workflows/nodes/shared/shared-subagent-protocol.md`, `DPT_FRAMEWORK/engine/work-unit-*.mjs`, `DPT_FRAMEWORK/cli/operate-work-unit.mjs`, `guidelines/agentic-subagent-mechanism.md`

## 概述

DPT 有 5 个 specialized subagent roles。Subagent 的核心目的是**噪声隔离**——把高 I/O 密度的搜索/抓取/提取工作委托给 bounded sub-agent，保护 Phase Agent 的上下文不被低密度信息淹没。

## 统一委托路径

```
queue demand → operate-work-unit claim → _work_units/waveN/{work_id}/
  → native sub-agent execution → result + receipt + outputs + cache
  → operate-work-unit submit → rb_output_declarations.jsonl → gate
```

## 5 个 Roles

### 1. dpt-source-intake（Wave0 基础参考摄入）

| 维度 | 内容 |
|------|------|
| **使用阶段** | Wave0 |
| **任务类型** | Foundation reference collection |
| **输入** | `task.md` (含 topic + search guardrails), `_beacon.json`, `result.schema.json` |
| **产出** | `artifacts/wave0/{topic.slug}/source.yaml`, optional `reference/00-shared-*.md`, cache trails, `result.json` |
| **搜索范围** | Topic 的 canonical definition、权威基线事实、官方文档、学术论文、高信任度来源 |
| **最小产出** | 每个 topic 至少 1 个真实 source（在可访问的前提下） |
| **文件系统** | 需要 read/write/append/mkdir |

### 2. dpt-evidence-extractor（Wave1/Wave2 证据提取）

| 维度 | 内容 |
|------|------|
| **使用阶段** | Wave1（主力）、Wave2（补充） |
| **任务类型** | Topic-specific deepening |
| **输入** | `task.md` (含 topic + evidence_route), `_beacon.json`, `result.schema.json` |
| **产出** | `evidence-summary.md`, `question-list.md`, structured source claims, cache trails, `result.json` |
| **搜索范围** | Mechanisms（因果、结构）、Trends（变化、模式）、Contradictions（矛盾、局限）、Open questions |
| **关键约束** | Wave0 URLs 可作背景引用，但 accepted Wave1 source claims 必须标注 URL 是 new 还是 from Wave0 |

### 3. dpt-topic-scout（Wave2 缺口填补搜索）

| 维度 | 内容 |
|------|------|
| **使用阶段** | Wave2 |
| **任务类型** | Gap-fill and emergent search |
| **输入** | `task.md` (含 finding/gap 描述), `_beacon.json`, `result.schema.json` |
| **产出** | Targeted evidence payload, source URLs, `fills_gap` 标注, confidence, cache trails, `result.json` |
| **搜索范围** | 针对特定 finding 或 topic gap 的定向搜索 |
| **关键约束** | 不做跨 topic 综合判断、不改 ledger state、不跑 gate |

### 4. dpt-claim-verifier（声明验证）

| 维度 | 内容 |
|------|------|
| **使用阶段** | Wave2（按需） |
| **任务类型** | Critical claim verification |
| **输入** | `task.md` (含 claim list + provided evidence refs), `_beacon.json`, `result.schema.json` |
| **产出** | Per-claim status: supported / weakened / contradicted / uncertain, evidence citations |
| **搜索范围** | 只搜索验证 claim 所需的 bounded search——不是 topic 全量搜索 |
| **验证标准** | 每个 status 必须引用具体 source |

### 5. dpt-source-diagnostic（来源诊断）

| 维度 | 内容 |
|------|------|
| **使用阶段** | 按需（任何阶段） |
| **任务类型** | Source quality assessment |
| **输入** | `task.md` (含 source URL list), `_beacon.json`, `result.schema.json` |
| **产出** | Per-source: trust tier, materiality, marketing risk, cross-verification need |
| **搜索范围** | 只读已有 source 做质量评估——不搜索新内容 |

## Work-Unit Envelope

每个 work unit 的目录结构：

```
_work_units/waveN/{work_id}/
├── manifest.json          # Engine 写入: work_id, queue_item_id, kind, batch/attempt indexes, hash, output/cache contract
├── task.md                # Phase Agent 生成的 bounded task（subagent 的主要阅读材料）
├── result.schema.json     # subagent 结果必须满足的 Zod schema
├── _beacon.json           # 身份 + 日志引用: bundle_dir, work_id, receipt_nonce
├── runtime-receipt.jsonl  # subagent 生命周期事件（由 subagent 写入）
├── _status.json           # 尝试状态投影
├── _agent.json            # 可选诊断运行时引用（永远不是权威）
└── result.json            # Engine submit 后写入（subagent 准备结果文件，但 submit 拥有最终接受权）
```

## Lifecycle Logging Mandate

每个 subagent role 都必须遵守：

1. **先读 beacon** — `_beacon.json` 是 bundle_dir/log_cli/work_id/receipt_nonce 的唯一真相源
2. **发送 lifecycle events** — search_batch_started/done, fetch_batch_started/done, cache_write_started/written, result_draft_started/written, error, work_done
3. **绝不伪造 nonce** — beacon 丢失时 emit error + 继续工作，不发明 receipt_nonce
4. **绝不 log 原始页面内容** — logging CLI always exits 0
5. **进度只是诊断** — 永远不替代 submit/source claims/cache validation/ledger coverage

## 什么不该委托给 Subagent

| 工作类型 | 原因 |
|---------|------|
| Pure cross-topic synthesis | 需要 Phase Agent 的全局视角 |
| Phase routing decisions | 只有 Phase Agent 读 phase node |
| Gate interpretation | 只有 Phase Agent 理解 gate 上下文 |
| Final report judgment | 需要综合所有 wave 产出 |
| HITL decisions | 必须由人类做 |

## → DeerFlow 映射

### 5 Subagent Roles → 5 DeerFlow Custom Subagents

```yaml
subagents:
  custom_agents:
    dpt-source-intake:
      description: "Collect foundation source metadata for a research topic"
      system_prompt: |
        [从 subagent-dpt-source-intake.md 提取]
        You are a source intake specialist for Wave0.
        Search for: canonical definitions, authoritative baseline facts,
        official docs, academic papers, high-trust sources.
        Minimum: 1 real source per topic.
      tools: [web_search, web_fetch, read_file, write_file, ls, mkdir]
      max_turns: 80
      timeout_seconds: 600

    dpt-evidence-extractor:
      description: "Deep-read sources and extract structured evidence"
      system_prompt: |
        [从 subagent-dpt-evidence-extractor.md 提取]
        Search for: mechanisms, trends, contradictions, open questions.
        Produce: evidence-summary.md, question-list.md, source claims.
      tools: [web_search, web_fetch, read_file, write_file, ls, grep, mkdir]
      max_turns: 120
      timeout_seconds: 900

    dpt-topic-scout:
      description: "Targeted gap-fill search for specific findings"
      system_prompt: |
        [从 subagent-dpt-topic-scout.md 提取]
        Search for evidence to fill a specific gap or finding.
        Produce targeted evidence payload with fills_gap and confidence.
      tools: [web_search, web_fetch, read_file, write_file, ls, mkdir]
      max_turns: 60
      timeout_seconds: 600

    dpt-claim-verifier:
      description: "Verify claims against evidence"
      system_prompt: |
        [从 subagent-dpt-claim-verifier.md 提取]
        For each claim: determine supported/weakened/contradicted/uncertain.
        Each status must cite specific sources.
      tools: [web_search, web_fetch, read_file, write_file, ls]
      max_turns: 60
      timeout_seconds: 600

    dpt-source-diagnostic:
      description: "Assess source quality and trust"
      system_prompt: |
        [从 subagent-dpt-source-diagnostic.md 提取]
        Assess per-source: trust tier, materiality, marketing risk,
        cross-verification need.
      tools: [web_fetch, read_file, write_file, ls]
      max_turns: 40
      timeout_seconds: 300
```

### Work-Unit Envelope → Sandbox 目录

DPT 的 work-unit envelope 由 `operate-work-unit claim` CLI 创建。在 DeerFlow 上：

- Phase Agent 直接用 sandbox 工具创建 `_bundle/_work_units/waveN/{work_id}/` 目录
- `task.md` = Phase Agent 写入的 subagent prompt
- `result.schema.json` = 期望的返回结构（如果 DeerFlow subagent 支持 structured output）
- `_beacon.json` = 元数据（work_id, queue_item_id, nonce）
- 或者简化为：Phase Agent 直接 call `task` tool with subagent_type + prompt，result 写回 sandbox

### Lifecycle Logging → Subagent 不需要单独 log

DeerFlow 的 subagent 执行已经有 trace/run_events。不需要额外的 `log-event.mjs` 等价物。但 Phase Agent 需要验证 subagent 产出：
- 检查 output files 存在
- 检查内容不为空
- 记录到 `rb_trace.jsonl`
