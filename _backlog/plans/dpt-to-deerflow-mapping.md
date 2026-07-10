# Plan: DPT_FRAMEWORK → DeerFlow 架构映射

> 类型: 设计 | 更新: 2026-07-10

## 背景 / 现状

`ai_tool_deepresearch`（DPT）是一个 agentic deep research 框架，核心分工：

```
Agent (LLM)     → 搜索、阅读、提取、写作、综合、判断
Markdown        → LLM-facing 控制面（phase node、任务卡、约束）
JS/CLI (Engine) → 确定性 checkpoint（gate、schema、trace、receipt）
JSON/YAML/JSONL → 持久化 runtime state（run bundle）
```

要在 DeerFlow 上复刻同等能力。DeerFlow 的 extension surface 是：
- `config.yaml`（models, tools, subagents, memory, guardrails, skills）
- `extensions_config.json`（MCP servers）
- `skills/custom/<skill>/SKILL.md`
- `SOUL.md`（lead agent personality）
- 我们自己的 Python package（通过 `use:` reflection path 接入）
- 硬约束：不改 `backend/` 和 `frontend/`

## 核心映射：三层执行模型

### Tier 1: Phase Chain → DeerFlow Skills + Custom Tools

| DPT | DeerFlow | 说明 |
|-----|----------|------|
| Phase node (`.md`) | `skills/custom/dpt/phases/*.md` | 每个 phase 是一个 Skill，定义 Agent 在该阶段的目标、允许动作、gate 命令 |
| `transitions.chain.json` | Phase skill 内嵌的 transition 指令 | Markdown 内写死 next phase，由 gate tool 返回的 `next` 驱动 |
| `enter-phase` → `advance-status` | gate tool 返回 `next` + Agent 读入下一 phase skill | LLM 读完当前 phase skill → 过 gate → gate 说 `next: phase-x` → LLM 加载下一个 skill |

**不需要 LangGraph 的 graph state machine 来控制 phase 流转。** 流转仍然由 LLM 读 Markdown 驱动，gate 工具只返回 "过/不过" + "下一步去哪"。这和 DPT"Agent 是 controller"的哲学一致。

### Tier 2: Queue → DeerFlow State Management (our Python package)

| DPT | DeerFlow | 说明 |
|-----|----------|------|
| `rb_queue.json` | Sandbox 文件系统中的 `_bundle/rb_queue.json` | 每个 research thread 的 sandbox 内维护自己的 queue |
| `operate-queue.mjs` | Python `agent/dpt/queue_manager.py` → 注册为 DeerFlow tool | claim/complete/refill 等操作 |
| Queue demand items | Tool 参数（JSON） | Agent 通过 tool call 创建 queue item |

Queue 不是 LangGraph state——它是 research run 的业务状态，存在 sandbox 文件系统里。这与 DeerFlow 的 thread isolation 兼容。

### Tier 3: Work Unit → DeerFlow Subagent Delegation

| DPT | DeerFlow | 说明 |
|-----|----------|------|
| `operate-work-unit claim/submit` | DeerFlow `task` tool + custom subagents | `task` 工具就是 DeerFlow 的 subagent delegation |
| Sub-agent role (`dpt-source-intake`, etc.) | `custom_agents` in `config.yaml` | 每个 DPT sub-agent role → 一个 DeerFlow custom subagent |
| Work unit lifecycle (claimed→running→submitted) | Subagent 执行完成 + 结果写回 sandbox | DeerFlow 的 subagent executor 管理生命周期 |
| `_work_units/` directory | Sandbox `_bundle/_work_units/` | Work unit 的输入输出存在 sandbox 里 |

DeerFlow 的 subagent 系统天然支持这个模式——`task` 工具接受 subagent_type、prompt，返回结果。关键是：
1. 定义专门的 subagent types（source-intake, evidence-extractor, claim-verifier 等）
2. 每个有独立的 system_prompt + tool whitelist
3. Work unit receipt/cache 由我们的 Python 代码管理

## 详细映射

### 1. 11 Phases → 11 Custom Skills

```
skills/custom/dpt/
├── phases/
│   ├── phase-instantiation.md     # 创建 run bundle
│   ├── phase-hitl1.md             # 人机交互：确认方向/profile/topics
│   ├── phase-setup.md             # 配置 research profile
│   ├── phase-seed-topics.md       # 生成初始 topic 列表
│   ├── phase-wave0.md             # 基础证据收集
│   ├── phase-wave1.md             # 深度证据收集
│   ├── phase-wave2.md             # 综合与交叉验证
│   ├── phase-hitl2.md             # 人机交互：审阅 synthesis
│   ├── phase-readiness.md         # 最终交付前检查
│   ├── phase-rerun.md             # 重跑/修复循环
│   └── phase-final.md             # 最终报告生成
├── shared/
│   ├── shared-profile.md          # Research profile 定义
│   ├── shared-gate-rules.md       # Gate 规则说明
│   ├── shared-schemas.md          # 数据结构 schema
│   ├── shared-subagent-protocol.md # Subagent 委托协议
│   └── shared-anti-cheating.md    # 反作弊规则
└── roles/
    ├── subagent-source-intake.md  # Wave0 子 agent role
    ├── subagent-evidence-extractor.md
    ├── subagent-claim-verifier.md
    ├── subagent-topic-scout.md
    └── subagent-source-diagnostic.md
```

每个 phase skill 结构：
```markdown
---
phase: wave0
gate: wave0-complete
stop: no
requires: [shared-profile, shared-schemas, shared-subagent-protocol]
---

# Phase: Wave0 — Foundation Shared Reference

## 0. Execution Brief
...

## 1. Stage Goal
...

## 5. Gate Command
Use tool `dpt_gate_check` with gate=`wave0-complete`, bundle_dir=`<path>`

## 6. On Gate Pass
Load next phase skill: `skills/custom/dpt/phases/phase-wave1.md`
```

### 2. Gates → Custom Python Tools

三个核心工具：

**`dpt_gate_check`** — 对应 DPT 的 `check-gate-*.mjs`：
```python
# agent/dpt/tools/gate_tools.py
def dpt_gate_check(gate: str, bundle_dir: str) -> dict:
    """
    返回 { passed: bool, say: str, next: str|null, errors: [...] }
    Check/Inspect/Advice 风格反馈
    """
```

**`dpt_queue_operate`** — 对应 `operate-queue.mjs`：
```python
def dpt_queue_operate(action: str, bundle_dir: str, ...) -> dict:
    """claim / complete / refill / check"""
```

**`dpt_work_unit_operate`** — 对应 `operate-work-unit.mjs`：
```python
def dpt_work_unit_operate(action: str, bundle_dir: str, ...) -> dict:
    """claim / submit / fail / timeout / inspect"""
```

这些工具通过 config.yaml 注册：
```yaml
tools:
  - name: dpt_gate_check
    use: agent.dpt.tools.gate_tools:dpt_gate_check
  - name: dpt_queue_operate
    use: agent.dpt.tools.queue_tools:dpt_queue_operate
  - name: dpt_work_unit_operate
    use: agent.dpt.tools.work_unit_tools:dpt_work_unit_operate
```

### 3. Subagent Roles → DeerFlow Custom Subagents

```yaml
subagents:
  custom_agents:
    dpt-source-intake:
      description: "Collect foundation source metadata for a research topic"
      system_prompt: |
        You are a source intake specialist...
        [content from DPT subagent-dpt-source-intake.md]
      tools: [web_search, web_fetch, read_file, write_file]
      skills: [dpt/phases/shared-schemas]
      max_turns: 80
      timeout_seconds: 600

    dpt-evidence-extractor:
      description: "Deep-read sources and extract structured evidence"
      system_prompt: ...
      tools: [web_fetch, read_file, write_file, ls, grep]
      max_turns: 120
      timeout_seconds: 900

    dpt-claim-verifier:
      description: "Verify claims against evidence and identify gaps"
      system_prompt: ...
      tools: [read_file, write_file, grep, web_search]
      max_turns: 80
      timeout_seconds: 600

    dpt-topic-scout:
      description: "Scout a research topic area and identify key sources"
      system_prompt: ...
      tools: [web_search, web_fetch, read_file, write_file]
      max_turns: 60
      timeout_seconds: 600

    dpt-source-diagnostic:
      description: "Diagnose and repair source access issues"
      system_prompt: ...
      tools: [web_fetch, read_file, write_file]
      max_turns: 40
      timeout_seconds: 300
```

### 4. Run Bundle → DeerFlow Sandbox + Thread

```
DeerFlow thread: "Deep Research: <question>"
  └── sandbox: /home/user/
      └── _bundle/               ← DPT 的 dpt_rb_* 对应物
          ├── BUNDLE_MAP.md
          ├── rb_plan.md
          ├── rb_profile.yaml
          ├── rb_status.json
          ├── rb_queue.json
          ├── rb_trace.jsonl
          ├── seed_topics/
          ├── reference/
          ├── artifacts/
          │   ├── wave0/
          │   ├── wave1/
          │   └── wave2/
          ├── final/
          ├── _cache/
          ├── _logs/
          └── _work_units/
```

优势：
- DeerFlow 的 thread isolation 天然隔离不同 research run
- Sandbox 提供文件系统，对应 DPT 的 run bundle
- DeerFlow 的 checkpointer 提供持久化（thread 重启后 sandbox 文件还在）
- `run_events` 可以提供 trace 能力

### 5. HITL → DeerFlow Human Input

| DPT | DeerFlow |
|-----|----------|
| `hitl1`（确认方向/profile/topics） | `ask_clarification` tool + structured questions |
| `hitl2`（审阅 synthesis） | `ask_clarification` + `present_files` 展示草稿 |
| User decision (proceed/repair/rerun) | 用户自然语言回复，Agent 解析意图 |

### 6. SOUL.md — Lead Agent Personality

```markdown
# Deep Research Lead Agent

You are a deep research agent built on DeerFlow. Your mission: given a broad
research question, produce an evidence-backed, multi-wave, gated research report.

## Operating Model
- You read phase skills to know what to do at each stage
- You call dpt_gate_check to validate your work
- You delegate evidence collection to specialized subagents via the `task` tool
- You track all state in the sandbox `_bundle/` directory
- You only stop for human input at HITL1 and HITL2 checkpoints

## Phase Flow
instantiation → hitl1 → setup → seed-topics → wave0 → wave1 → wave2 → hitl2
→ readiness → rerun → final

[rest of the DPT lead agent behavioral rules...]
```

### 7. Anti-Cheating / Evidence Integrity

DeerFlow 已有的保护：
- `read_before_write` gate → 防止盲写（对应 DPT 的反作弊规则之一）
- `loop_detection` → 防止死循环
- `tool_progress` → 检测工具停滞
- `safety_finish_reason` → 安全拦截

需要额外添加的：
- `dpt_gate_check` 工具内建 receipt validation（只接受真实执行的证据）
- Work unit submit 验证 output files 确实存在且由 subagent 产出
- Trace 写入为 append-only JSONL

## 不确定的 / 需要进一步思考的问题

1. **Phase skill 的加载时机**：DeerFlow 的 skill 机制是在 system prompt 里注入 SKILL.md 内容，还是 agent 主动 `read_file` 去读？如果是前者，多个 phase skill 同时注入会导致 prompt 膨胀。**倾向于用 `deferred_discovery` + `describe_skill` 工具，Agent 按需加载当前 phase skill。**

2. **Gate 工具的反馈循环**：DPT 的核心是 JS 反馈 → LLM 读取 → 修复 → 重试。DeerFlow 里 gate tool 返回 `{passed: false, say: "..."}` 后，Agent 能否自然地进入"读反馈→修复"循环？还是需要额外的 middleware 来强制？**从 DeerFlow 的工具范式看，tool 返回的内容会自动进入 conversation context，Agent 自然会读并反应——这和 DPT 的反馈循环一致。**

3. **多 wave 的 subagent 并行度**：DPT 的 queue 机制支持在一个 wave 内创建多个 work unit。DeerFlow 的 `task` 工具能否一次调用触发多个 subagent？**DeerFlow 的 task tool 是单次单 subagent。但 Agent 可以在一次 turn 内多次调用 task tool（不同 subagent_type），形成事实上的并行 delegation。**

4. **Trace/Reentry 的可靠性**：DPT 的 trace JSONL 让 Agent 断点续跑。DeerFlow 里 thread 重启后 sandbox 文件还在，Agent 可以读 `rb_status.json` + `rb_trace.jsonl` 恢复状态。**关键在于 gate 工具和 phase skill 必须明确指示"先读 bundle 状态再决定从哪继续"。这与 DPT 的 reentry 逻辑一致。**

5. **是否需要 LangGraph 来做 phase 路由？**：DPT 的哲学是 LLM 读 Markdown 决定下一步——不是代码 push Agent 去下一个 phase。在 DeerFlow 上我们也应该保持这个哲学：**Phase 流转由 Agent 自主决策（读完当前 phase skill + 过 gate → 自己加载下一个 phase skill），而不通过 LangGraph 的 conditional edge 自动跳转。** 这是关键架构决策——如果我们用 LangGraph 的 graph 来控制 phase 流转，就退化成 "scripted workflow" 而不是 "agentic workflow"。

## 落地关联

1. 第一轮：用 DeerFlow 已有的 extension surface 跑通一条最小 Phase Chain（instantiation → setup → wave0 → final），验证 gate 工具 + skill 驱动的模式可行
2. 第二轮：补全 11 个 phase + 5 个 subagent role + queue/work-unit 机制
3. 第三轮：HITL 交互、repair/rerun 循环、trace/reentry
4. 每轮都以 OpenSpec change 推进

本 plan 的结论确认后，以 `openspec/changes/` 下的 change 落地。

## 详细分析索引

每个子系统有独立的详细分析文档，在 `details/` 子目录下：

| # | 文档 | 内容 |
|---|------|------|
| 01 | [details/01-execution-model.md](details/01-execution-model.md) | 三层执行模型 + Agentic Loop + 三权威架构 |
| 02 | [details/02-engine.md](details/02-engine.md) | Engine: gate-loop, gate-fork, queue-manager, work-unit-lifecycle, trace, consistency |
| 03 | [details/03-bundle-structure.md](details/03-bundle-structure.md) | Run bundle 目录结构、control files、Framework/Bundle 边界 |
| 04 | [details/04-schema.md](details/04-schema.md) | Enums、Contracts、Gate Definitions、Research Styles |
| 05 | [details/05-phases.md](details/05-phases.md) | 11 个 Phase 详解、Execution Contract、Silent Execution、HITL |
| 06 | [details/06-subagent-roles.md](details/06-subagent-roles.md) | 5 个 Subagent Role、Work-Unit Envelope、委托协议 |
| 07 | [details/07-guidelines-key-insights.md](details/07-guidelines-key-insights.md) | Guidelines 体系关键设计原则、深层机制 |

> 以上文档从 `ai_tool_deepresearch` 分析提取，目标是完整理解 DPT 的设计后，在 DeerFlow 上重实现。读的时候对照着看 DPT 源码效果最好。
