# DPT_FRAMEWORK 架构参考

> 来源: `/Users/bowhead/ai_tool_deepresearch/`
> 用途: 理解 DPT 的完整设计后，在 DeerFlow 上重实现 Deep Research 能力

## 索引

| # | 文档 | 内容 |
|---|------|------|
| — | [dpt-to-deerflow-mapping.md](dpt-to-deerflow-mapping.md) | **主控文档**: 架构映射方案、关键发现、已知缺口 |
| 01 | [details/01-execution-model.md](details/01-execution-model.md) | 三层执行模型 + Agentic Loop + 三权威架构 |
| 02 | [details/02-engine.md](details/02-engine.md) | Engine: gate, queue, work-unit, trace, consistency |
| 03 | [details/03-bundle-structure.md](details/03-bundle-structure.md) | Run bundle 目录结构、control files |
| 04 | [details/04-schema.md](details/04-schema.md) | Enums、Contracts、Gate Definitions、Research Styles |
| 05 | [details/05-phases.md](details/05-phases.md) | 11 个 Phase 详解、Silent Execution、HITL |
| 06 | [details/06-subagent-roles.md](details/06-subagent-roles.md) | 5 个 Subagent Role、Work-Unit Envelope |
| 07 | [details/07-guidelines-key-insights.md](details/07-guidelines-key-insights.md) | Guidelines 体系关键设计原则 |
| 08 | [details/08-additional-surfaces.md](details/08-additional-surfaces.md) | Command Playbook、Templates、Brief、Experiments |

## 读法

1. 先看 `dpt-to-deerflow-mapping.md` 了解全局映射 + 关键发现
2. 对照 DPT 源码（`/Users/bowhead/ai_tool_deepresearch/`）按需深入各 detail doc
3. 消化完后在 `_backlog/plans/` 写本项目的具体实施方案
