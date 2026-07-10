# DPT Guidelines 体系 — 关键设计原则

> 从 `ai_tool_deepresearch` 分析，用于在 DeerFlow 上重实现。
> 主控文档: [../dpt-to-deerflow-mapping.md](../dpt-to-deerflow-mapping.md)

## Guidelines 全景

| Guideline | 角色 | 关键洞察 |
|-----------|------|---------|
| `project-charter.md` | 项目宪法 | LLM 是能力源，Markdown 控 Agent Flow，JS/CLI 控确定性 checkpoint |
| `framework-runtime-boundary.md` | 目录权威边界 | DPT_FRAMEWORK/ = 只读，dpt_rb_*/ = 可变 runtime truth |
| `agentic-execution-model.md` | 术语正典 | Chain → Queue → Work Unit 三层执行粒度 |
| `agentic-workflow-mechanism.md` | Tier 1 机制 | Phase Agent 动态加载 MD 的闭环，三权威架构 |
| `agentic-queue-mechanism.md` | Tier 2 机制 | 两层嵌套循环，Queue 驱动 phase 内静默执行 |
| `agentic-subagent-mechanism.md` | 委托机制 | Work-unit-mediated sub-agent，噪声隔离 |
| `command-experiments.md` | 实验规范 | 如何写和运行 experiment playbook |
| `logging-conventions.md` | 日志约定 | 结构化日志格式和位置 |

## 核心设计决策（从 Guidelines 中提取）

### 1. Layer 1 可以出错，Layer 2 不能造假

```
Layer 1: Agent/MD → 可以理解偏差、搜索噪声、格式错误 → JS 反馈 → Agent 修复
Layer 2: Engine/CLI/Trace → schema/状态机/receipt 绝不能假通过
```

绝对禁止：
- 手写假 result.json / trace event / receipt
- 跳过 runtime validation 后继续
- 直接改 deterministic state 绕过状态机
- 用 console.log 当裁决证据

### 2. 两阶段 Token 策略

Phase Agent 上下文有限 → 高 I/O 工作委托给 subagent → subagent 返回简洁结构化结果

```
Phase Agent context (scarce) ← 只接收 structured result
Sub-agent context (disposable) ← 承担搜索/抓取的噪声
```

### 3. Gate 失败不是错误，是正常反馈

```
gate fail → read inspect/advice → fix → retry → pass
                                     → switch strategy
                                     → degraded pass (gate says passed:true, degraded:true)
```

### 4. 推进驱动 = Agent 读 Markdown，不是 JS loop

```
不存在 while(true) { advance(); }
不存在 lifecycle walker
不存在 cursor 指针

Agent 手持当前 node → 执行 → gate → chain 查 next → 加载下一 node → 循环
```

### 5. transition table 是被动路由表，不是分支逻辑

```
transitions.chain.json:
  { currentNodeRef, outcome } → nextNodeRef

不编码 fail/repair 分支——那些归 Agent 判断
不持有当前状态
不驱动循环
```

### 6. Stop Authorization

Phase Agent 只能在以下情况停机：
- `final_delivery` — 最终交付完成
- `decision_blocker` — 无法继续
- `empty_queue_after_refill` — queue 已空且 refill 后仍为空

其他情况：`unauthorized_continue_required` — 不能停

### 7. Anti-cheating 的深层机制

不只是"别造假"——而是一整套结构保证只有真实执行才能产出的副产物：

- **Receipt nonce**: 每个 work unit 有随机 nonce，submit 时验证
- **Beacon**: 身份文件，防止混淆 work_id
- **Cache trails**: subagent 的搜索/抓取必须留下 cache 痕迹
- **Ledger rows**: gate 读 `rb_output_declarations.jsonl`，不看文件系统存在性
- **Trace JSONL**: append-only audit trail

## → DeerFlow 映射

### 原则保留

这些原则直接移植到 DeerFlow：
- Layer 1 可错/Layer 2 不造假 → gate tools 必须做真实文件检查
- Token 策略 → DeerFlow subagent 天然隔离
- Gate 失败是反馈 → gate tool 返回 {passed, say, inspect, advice}
- Agent 驱动 → 不发 LangGraph conditional edge

### 原则调整

| DPT | DeerFlow |
|-----|----------|
| JS trace JSONL | sandbox `_bundle/rb_trace.jsonl` (由 gate tool 写入) |
| Receipt nonce | 可选——DeerFlow subagent executor 已有自己的追踪 |
| Beacon | Phase Agent 传 bundle_dir 作为 tool 参数，不需要单独 beacon |
| Cache trails | subagent 产出文件存在 sandbox，天然可审计 |
| Ledger rows | `rb_output_declarations.jsonl` 由 dpt_work_unit_submit tool 写入 |

### Stop Authorization → 简化

DeerFlow 的 Agent 在收到 `stop: yes` 的 phase skill 指令（HITL1/HITL2）时才与用户交互。其他 phase 自然静默。不需要 engine-enforced stop authorization——Agent 遵循 skill 指令即可。
