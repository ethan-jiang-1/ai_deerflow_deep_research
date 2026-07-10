# DPT 辅助 Surface — 补充分析

> 从 `ai_tool_deepresearch` 分析，用于在 DeerFlow 上重实现。
> 主控文档: [../dpt-to-deerflow-mapping.md](../dpt-to-deerflow-mapping.md)
> 相关: [05-phases.md](05-phases.md) · [03-bundle-structure.md](03-bundle-structure.md)
>
> **DPT 源文件**: `DPT_FRAMEWORK/command_playbook/`, `DPT_FRAMEWORK/rb_templates/`, `DPT_FRAMEWORK/workflows/nodes/brief/`, `experiments_playbook/`, `experiments_env/`

---

## 1. Command Playbook (`DPT_FRAMEWORK/command_playbook/`)

Agent-facing 命令指令和诊断/维护 playbook。不是给人看的操作手册——是给 coding agent（Claude Code/Codex）读的。

关键文件：
- `start-research.md` — 触发一次 deep research 的入口流程。Agent 读它来了解如何开始。
- 其他 playbook 文件 — 特定场景的维护/诊断指令

### → DeerFlow 映射

`start-research.md` 的内容融入 `SOUL.md` 的第一段：告诉 lead agent 当用户表达研究意图时，如何开始 deep research 流程。

---

## 2. RB Templates (`DPT_FRAMEWORK/rb_templates/`)

`instantiate-run-bundle.mjs` 创建 bundle 时的初始模板文件。Materialize 到新 bundle 目录。

包含：
- `BUNDLE_MAP.md` 模板
- `rb_plan.md` 模板（含 frontmatter skeleton）
- `rb_profile.yaml` 模板
- `rb_status.json` 初始值
- `rb_queue.json` 空 queue
- 空 `rb_trace.jsonl`

### → DeerFlow 映射

Phase Agent 在 instantiation phase 用 sandbox 工具创建 `_bundle/` 目录和初始 control files。可以直接复用 DPT 的模板结构，但写成 DeerFlow skill 里的指令：

```
## 4. Expected Artifacts
创建以下文件在 sandbox _bundle/ 目录下：
- _bundle/BUNDLE_MAP.md (空模板)
- _bundle/rb_plan.md (含研究问题)
- _bundle/rb_profile.yaml (初始值)
- _bundle/rb_status.json (current_gate: instantiation_complete)
- _bundle/rb_queue.json (空 queue, queue_health: blocked)
- _bundle/rb_trace.jsonl (空文件)
- 目录: seed_topics/, reference/, artifacts/wave0/, artifacts/wave1/, artifacts/wave2/, final/, _cache/, _logs/, _work_units/
```

---

## 3. Brief Nodes (`DPT_FRAMEWORK/workflows/nodes/brief/`)

HITL phase 使用的入口 prompt 模板。在 `suggested_context` 中被引用：

- `brief/hitl1.md` — HITL1 的入口 prompt（structure questions、research profile 选择）
- `brief/hitl2.md` — HITL2 的入口 prompt（decision brief、A/B/C/D/E 选项）

### → DeerFlow 映射

HITL phase skill 的 `suggested_context` 保持为 skill reference。在 DeerFlow 上，这些 brief 可以：
1. 合并到 HITL phase skill 的 body 里（作为 section）
2. 或者保留为独立的 shared skill，Agent 在 HITL phase 时加载

---

## 4. Experiments Playbook (`experiments_playbook/`)

22 个 `exp_*` 目录，每个是一个受控端到端实验的 playbook：

```
exp_agentic-queue/          — Queue 机制实验
exp_autonomous-research-hardening/ — 自主研究硬化实验
exp_engine-boundary/        — Engine 边界实验
exp_evidence-extraction/    — 证据提取实验
exp_gate-fork/              — Gate fork 实验
exp_gate-loop/              — Gate loop 实验
exp_reentry-debuggability/  — Reentry 可调试性实验
exp_subagent/               — Subagent 机制实验
exp_wff_*/                  — Workflow Foundation 实验系列
exp_wfn_*/                  — Workflow Node 实验系列
...
```

每个 playbook 是 Agent-driven 的：Agent 读 playbook → 执行 → 产出 disposable bundle → trace 裁决。

### → DeerFlow 映射

这些实验不是生产代码——是**验证机制可行性的证据**。对应到 DeerFlow 开发流程：
- 第一轮 OpenSpec change 落地时，用类似的受控端到端验证每个机制
- 可以简化为：跑最小 phase chain → 检查 sandbox 文件 → 验证 gate tool 返回正确

---

## 5. Experiments Environment (`experiments_env/`)

共享实验工具：
- `shared/new-disposable-bundle.mjs` — 快速创建 disposable experiment bundle
- `prototype-*/` — 已冻结原型（仅 fixture + 笔记，不含 engine/trace/CLI 代码）

### → DeerFlow 映射

不需要直接映射。DeerFlow 开发中的 "实验" = 跑真实 `make dev` + 验证 behavior。

---

## 6. Mode Injection（workflow-chain.mjs 的隐藏特性）

`workflow-chain.mjs` 的 `assessNode` 在加载 phase node 后，会根据 `stop` 和 `gate` 注入行为 banner：

- `stop: no` + `gate: non-null` → 注入 `AUTONOMOUS MODE` banner：Agent 不能浮出水面、必须自我修复、gate 失败不是紧急情况
- `phase: final` + `stop: no` + `gate: null` → 注入 `TERMINAL DELIVERY MODE` banner

这在 DPT 中是通过 JS 代码注入的，在 DeerFlow 上需要通过 phase skill 文件本身包含这些指令（而不是运行时注入）。

### → DeerFlow 映射

每个 non-HITL phase skill 的第一段直接包含静默执行纪律（来自 `shared-silent-execution.md` 的核心规则）。Phase Agent 读 skill 时自然遵守。不需要额外的 code-level injection。

---

## 7. Key Finding: Gate CLIs Don't Use checkGate/forkGate

通过 agent 分析发现（见 [02-engine.md](02-engine.md) §5-6）：**实际的 CLI gate 模块并不调用 `checkGate()`/`forkGate()`**。它们实现了自己的 rule loop，使用 `gate-helpers-core.mjs` 中的原语。

这意味着在 DeerFlow 上重实现 gate 工具时：
- 不需要精确复刻 `checkGate`/`forkGate` 的函数签名
- 需要复刻的是 **rule evaluation pattern**：逐个评估规则 → 收集所有失败 → 返回 `{passed, inspect[], advice[], routing}`
- 以及 **fatigue/degradation escalation**：重复失败时自动调整 advice 文本

参考：`check-gate-wave0-complete.mjs`（577 行）和 `check-gate-instantiation-complete.mjs` 的完整实现模式。
