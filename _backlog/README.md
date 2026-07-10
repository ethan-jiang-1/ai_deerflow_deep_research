# _backlog — 项目待办与决策记录

> 最后更新: 2026-07-10 | 本目录追踪本仓库的工作项、设计决策、上游分析。
> 活跃工作走 OpenSpec（`openspec/changes/`）；本目录是 **上游分析与决策记录 + 待办池**，不是运行时真相。
>
> **本文件是 `_backlog` 的规矩手册。** 搬迁流程在下面定死，今后大家都遵循这里头定的规矩。
>
> **命名约定：`_` 前缀目录（`_done/`、`_fixed_bugs/` 等）是已归档/已完成的子目录——coding agent 默认忽略，除非显式点名要读。** 活跃工作件在无前缀目录（`bugs/`、`todos/`、`plans/`）。

## 这个仓库是什么

`ai_deerflow_deep_research` 是对上游 [bytedance/deer-flow](https://github.com/bytedance/deer-flow)（基于 LangGraph 的 AI super-agent 框架）之上，以 OpenSpec spec-driven 规范开发的 **Deep Research 智能体应用**。硬约束：**绝不修改上游源码**（`backend/`、`frontend/` 是上游 1:1 镜像）。研究笔记在 `_digest/`（继承自 wiki 项目），问答在 `_faq_on_digested/`，Deep Research 智能体开发走 `openspec/`。

## 目录结构

```
_backlog/
├── README.md                          # 本文件（规矩手册 + 索引）
│
├── _done/                             # ✅ 已完成/已归档
│   ├── README.md                      #   状态总览、快速查阅指南
│   ├── _fixed_bugs/                   #   已修复 Bug（编号权威源）
│   ├── _done_todos/                   #   已完成 TODO（DONE-NNN）
│   ├── _closed_plans/                 #   已完成 Plan（CLS-NNN）
│   └── _suspened_bugs/                #   悬挂 Bug（暂未确认修复）
│
├── bugs/                              # 🐛 活跃 bug → 修完移入 _done/_fixed_bugs/
├── todos/                            # 📋 活跃 todo → 做完移入 _done/_done_todos/
├── plans/                            # 📐 活跃 plan → 完成移入 _done/_closed_plans/
└── learning/                         # 📖 apply/研究复盘 retro（长期留存）
```

---

## 知识地图：从活跃到归档，三对生命周期 🗺️

`_backlog` 里追踪三种工作件，每一种都是 **活跃在无前缀目录，完成移入 `_done/` 下对应的 `_` 前缀子目录**：

| 类型 | 活跃（当前工作） | 归档（已完成） | 编号方式 |
|------|-----------------|---------------|---------|
| 🐛 **Bug** | [`bugs/`](bugs/) — 活跃 bug 列表 | [`_done/_fixed_bugs/`](_done/_fixed_bugs/) — 已修复 | BUG-NNN 递增，权威在 `_fixed_bugs/` |
| 📋 **Todo** | [`todos/`](todos/) — 活跃 todo + 依赖链 + 执行顺序 | [`_done/_done_todos/`](_done/_done_todos/) — 已完成 | DONE-NNN 递增，移入时分配 |
| 📐 **Plan** | [`plans/`](plans/) — 活跃 plan 列表 | [`_done/_closed_plans/`](_done/_closed_plans/) — 已完成 | CLS-NNN 递增，移入时分配 |

> 📖 **想看全局状态、历史决策、查阅指南** → [`_done/README.md`](_done/README.md)
>
> 📖 **想看当前该做什么、依赖关系、执行顺序** → [`todos/README.md`](todos/README.md)

---

## 搬迁规矩

三种工作件的搬迁步骤完全一样：**`git mv` 过去，文件名不变，位置即状态，连带更新三处 README。** 各子目录 README（`bugs/`、`todos/`、`plans/` 及对应的 `_done/` 下级）里也写了具体步骤。

### 铁律

- **`_backlog` 独立于 OpenSpec** —— 两层各自簿记，不交叉判定。不要为了在 `_backlog` 标 done 而去动 OpenSpec。
- **文件内容原样保留**，不重写。用 `git mv`（不是普通 `mv`）。
- **反向可以**：`git mv` 回活跃目录即可。极少用，但允许。

### 三条命令

```bash
# Bug 修完
git mv bugs/BUG-<NNN>-<slug>.md _done/_fixed_bugs/BUG-<NNN>-<slug>.md

# Todo 做完
git mv todos/todo-<name>.md _done/_done_todos/todo-<name>.md

# Plan 完成
git mv plans/<name>.md _done/_closed_plans/<name>.md
```

### 搬完更新

> ⚠️ **README 文件本身永不删除。** "移除"指的是从活跃列表中移除该条目的行，不是删文件。每个 README 永远留在目录里做索引。**文件内容原样保留，`git mv` 搬迁。**

**🐛 Bug 修完：**
| 操作 | 怎么改 |
|------|--------|
| `bugs/README.md` | 从活跃列表移除该 bug 的行 |
| `_done/_fixed_bugs/README.md` | 表格加一行 + 更新 Next available bug ID |
| `_done/README.md` | 已修复 bug 计数 +1 |

**📋 Todo 做完：**
| 操作 | 怎么改 |
|------|--------|
| `todos/README.md` | 从活跃列表移除该 todo 的行 |
| `_done/_done_todos/README.md` | 表格加一行 + 更新 Next available DONE ID |
| `_done/README.md` | DONE 计数 +1 |

**📐 Plan 完成：**
| 操作 | 怎么改 |
|------|--------|
| `plans/README.md` | 从活跃列表移除该 plan 的行 |
| `_done/_closed_plans/README.md` | 表格加一行 + 更新 Next available plan ID |
| `_done/README.md` | 已关闭 plan 计数 +1 |

---

## 相关外部文件

> 以下路径相对于 **repo 根目录**（`/Users/bowhead/ai_deerflow_deep_research/`），不是 `_backlog/` 目录。

| 路径 | 角色 |
|------|------|
| `AGENTS.md` / `CLAUDE.md` | repo 最高指引（monorepo 定位 + 跨切约定；`CLAUDE.md` 经 `@AGENTS.md` 导入） |
| `openspec/config.yaml` | OpenSpec 项目上下文 + 4 artifact（proposal/specs/design/tasks）规则 |
| `openspec/specs/` | 已接受 spec（运行时真相层，与 `_backlog` 各自簿记） |
| `openspec/changes/` | 活跃 change |
| `_digest/` | DeerFlow 源码研究笔记 |
| `_faq_on_digested/` | 基于 digest 的 FAQ |
| `backend/` `frontend/` | 上游镜像（**禁改**，`main` 分支 1:1 跟踪 bytedance/deer-flow） |
