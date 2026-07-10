# Plan: Deep Research 00 - Runtime Infrastructure

> 类型: 设计 / 基础设施 | 更新: 2026-07-10
> 对应 OpenSpec change: `establish-deep-research-runtime-infrastructure`
> 依赖: 无
> 在主图中的作用: 提供 01 及以后所有 graph/node 共用的加载、挂载、上下文和资源生命周期底座

## 目标

先回答并验证“Deep Research graph 最终怎样架到 DeerFlow 上”。本 change 不搭业务 graph，只交付一个能够被标准运行环境稳定加载、能够获得可信 DeerFlow runtime context、能够托管 nested graph/checkpointer 的最小基础设施纵切面。

## 必须先定死的架构决策

- **执行形态：in-process custom tool + nested StateGraph。** Deep Research node 需要父 thread 的 sandbox、身份、stream/cancel context，因此 MCP/ACP 不作为默认承载；只有 in-process 路径被实证否决时才回退并重新设计。
- **代码归属：顶层自有 installable package。** package 不放入 `backend/`/`frontend/`，只允许依赖 `deerflow.*`，不被 harness 反向导入。
- **启动装配：project-owned additive launcher。** 由于现有 Gateway 从 `backend/` 以 `PYTHONPATH=.` 启动，00 必须提供 downstream launcher/packaging 方案，使 local dev、prod、Docker 都加载同一包；不能依赖手工 `pip install`、临时 `.pth` 或一次性 `sys.path` 修改。
- **资源归属：GraphHost。** tool 不在每次调用时随意新建无清理 DB 连接；统一 host 管 graph factory、checkpointer/provider lifecycle、namespace 和 shutdown。
- **身份来源：Runtime context。** user/thread/run/sandbox 只能从可信 runtime 派生，模型参数不能指定或覆盖。

## Canonical Folder Structure

00 必须实际创建并用 `agent/AGENTS.md` 固定以下结构。后续 change 不得在 repo root、`backend/` 或 `frontend/` 另起第二套 Deep Research 源码树。

```text
agent/
├── AGENTS.md                         # 本模块目录/依赖/测试规约，后续 AI Coding 必读
├── README.md                         # 安装、配置、启动、诊断
├── Makefile                          # downstream 的 install/configure/dev/start/test/doctor
├── pyproject.toml                    # 独立 installable Python package
├── src/
│   └── deerflow_deep_research/
│       ├── __init__.py               # 仅稳定公共 API，使用 lazy exports
│       ├── config.py                 # 本项目配置 model/解析，不读取业务 state
│       ├── tool.py                   # tools[].use 的稳定入口 deep_research_tool
│       │
│       ├── runtime/                  # DeerFlow/Gateway integration boundary
│       │   ├── graph_host.py         # graph/checkpointer/provider lifecycle
│       │   ├── runtime_adapter.py    # DeerFlow Runtime -> trusted GraphContext
│       │   ├── identity.py           # user/thread/research namespace derivation
│       │   ├── checkpoint.py         # provider adapter/namespace policy
│       │   ├── events.py             # outer stream/run-event projection
│       │   └── lifecycle.py          # startup/shutdown/cancellation ownership
│       │
│       ├── domain/                   # 纯共享数据合同，不含 IO/DeerFlow 调用
│       │   ├── enums.py
│       │   ├── context.py            # GraphContext protocol/data
│       │   ├── state.py              # ResearchState + reducers (02)
│       │   ├── gates.py              # Gate contracts (03)
│       │   ├── work_units.py         # WorkSpec/Attempt/Submission (04)
│       │   ├── evidence.py           # Source/Claim/Finding contracts
│       │   └── delivery.py           # readiness/final contracts
│       │
│       ├── engine/                   # deterministic shared mechanisms
│       │   ├── gates/                # kernel, rule registry, fatigue/repair budget
│       │   ├── work_units/           # batching, submit, ledger, validators
│       │   ├── evidence/             # URL/claim/citation deterministic checks
│       │   └── artifacts/            # bundle layout, hashing, path containment
│       │
│       ├── agents/                   # node 内 DeerFlow agent-loop factory
│       │   ├── factory.py            # create_deerflow_agent adapter
│       │   ├── policies.py           # model/tool/path/budget policies
│       │   ├── prompts.py            # package-resource prompt loader
│       │   └── structured_output.py  # agent result -> domain contract
│       │
│       ├── graph/                    # workflow declaration，禁止放通用业务实现
│       │   ├── builder.py            # compile StateGraph
│       │   ├── topology.py           # 唯一 node/edge 拓扑真相
│       │   ├── registry.py           # 收集 NodeSpec，不含 routing judgment
│       │   ├── implementation_map.py # fake/real/mixed 选择
│       │   ├── routing.py            # 只读 typed verdict 的 routers
│       │   └── nodes/
│       │       ├── bootstrap/
│       │       ├── hitl1/
│       │       ├── topic_planning/
│       │       ├── wave0/
│       │       ├── source_diagnostic/
│       │       ├── claim_verifier/
│       │       ├── wave1/
│       │       ├── wave2_synthesis/
│       │       ├── targeted_evidence/
│       │       ├── hitl2/
│       │       ├── rerun/
│       │       ├── readiness/
│       │       └── final_delivery/
│       │
│       └── resources/
│           └── shared_prompts/       # 多节点真正共用的短合同，禁止复制整份 phase prompt
│
├── config/                           # committed source templates，不是 runtime truth
│   ├── deerflow.fragment.yaml        # tool_group + tools[].use 配置片段
│   ├── extensions.fragment.json      # skill enable state 片段
│   ├── agent-template/
│   │   ├── SOUL.md
│   │   └── config.yaml
│   └── skills/
│       └── deep-research-controller/
│           └── SKILL.md
│
├── scripts/
│   ├── configure.py                  # structured/idempotent materialization
│   ├── doctor.py                     # import/config/mount/provider checks
│   └── serve.sh                      # project-owned local dev/prod launcher
├── docker/
│   └── docker-compose.deep-research.yaml  # dev/prod gateway source/PYTHONPATH override
│
└── tests/
    ├── unit/
    │   ├── runtime/
    │   ├── domain/
    │   ├── engine/
    │   ├── agents/
    │   └── nodes/                    # 与 graph/nodes/<name>/ 一一镜像
    ├── contract/                     # NodeSpec/import boundary/config contracts
    ├── graph/                        # topology/full-fake/mixed-graph
    ├── integration/                  # DeerFlow runtime/checkpointer/sandbox/mount
    ├── e2e/
    └── fixtures/
```

### 每个 Node Package 的固定形状

每个 `graph/nodes/<node_name>/` 都是一个独立 Python package，不能把 13 个 node 平铺成 `nodes.py`，也不能把多个 phase 混进一个 `wave_nodes.py`：

```text
graph/nodes/<node_name>/
├── __init__.py    # 只 export NODE_SPEC，不执行 IO/构图
├── node.py        # real node/subgraph entry
├── fake.py        # deterministic fake，01 起永久保留
├── contracts.py   # 仅该 node 私有的 typed input/output
├── prompt.md      # 仅 agentic node 需要；由 package resources 加载
└── gates.py       # 仅该 node 的 rule definitions；通用 kernel 在 engine/gates
```

简单 deterministic node 可以没有 `prompt.md`；没有局部门禁的 node 可以没有 `gates.py`。其余文件名和职责固定，不另造 `utils.py`、`helpers.py` 垃圾桶。

`NODE_SPEC` 是 builder 唯一认识的 node surface，至少声明稳定 name、real callable/factory、fake callable/factory、input/output contract 和所属 phase。真实实现可以在 `node.py` 内组装一个 subgraph，但顶层 topology 仍只看到稳定的逻辑 node name。

### Shared Code 放置规则

- 跨 node 的 **数据结构** 放 `domain/`；只被一个 node 使用的结构留在该 node 的 `contracts.py`。
- 跨 node 的 **确定性算法/IO policy** 放 `engine/`；只被一个 node 使用的动作留在 `node.py`。
- DeerFlow Runtime、checkpointer、stream、sandbox handle 的适配只放 `runtime/`。
- `create_deerflow_agent()`、model/tool/prompt policy 只放 `agents/`。
- node-specific prompt 跟 node 放；只有被至少两个 nodes 实际引用的片段才能进入 `resources/shared_prompts/`。
- 禁止创建全局 `common.py`、`utils.py`、`helpers.py`；共享代码必须按领域命名并有明确 owner。

### Import Direction

```text
tool.py -> runtime -> graph -> nodes
                            nodes -> agents -> deerflow.*
                            nodes -> engine -> domain
                            nodes -> domain
runtime -> domain + deerflow.*
graph   -> domain
domain  -> stdlib + pydantic only
```

硬规则：

- `domain` 不 import `engine/agents/graph/runtime/deerflow/app`。
- `engine` 不 import `graph/nodes/runtime/app`。
- 一个 node 不直接 import 另一个 node；跨 phase 只通过 ResearchState/artifact refs 和 topology edge。
- 自有 package 永不 import `app.*`，也永不被 `deerflow.*` 反向 import。
- `tool.py` 保持薄，只做 schema/tool entry 和调用 GraphHost，不包含 research business logic。

00 必须增加 AST import-boundary test，把这些规则变成 CI gate，而不只写在文档里。

## Mount And Configuration Contract

这里区分四种完全不同的“mount”，后续不得混用。

### 1. Gateway Host Python Source

- 本地源码真相：`<repo>/agent/src/deerflow_deep_research/`。
- local launcher 从 `backend/` 启动 Gateway，但显式设置 `PYTHONPATH=<repo>/agent/src:.`。
- Docker dev 使用现有 repo bind `/app/project`，source path 为 `/app/project/agent/src`。
- Docker prod override 将 `agent/` 只读挂到 `/app/agent`，source path 为 `/app/agent/src`。
- `agent/docker/docker-compose.deep-research.yaml` 必须替换 Gateway command/PYTHONPATH；不修改上游 `backend/Dockerfile` 或原 compose 文件。
- `deerflow.fragment.yaml` 的稳定反射路径固定为 `deerflow_deep_research.tool:deep_research_tool`。

Host source 只供 Gateway Python 进程 import，不挂进执行 sandbox。

### 2. DeerFlow Runtime Configuration

`agent/config/` 保存可提交模板；真实 `config.yaml`、`extensions_config.json` 和 `.deer-flow/` 仍是 gitignored runtime truth。

`scripts/configure.py` 必须用 YAML/JSON parser 做 idempotent merge：

- `config.yaml -> tool_groups += deep-research-control`；
- `config.yaml -> tools += {name: deep_research, group: deep-research-control, use: deerflow_deep_research.tool:deep_research_tool}`；
- `extensions_config.json` 启用 `deep-research-controller` skill；
- materialize committed SOUL/agent config template 到 DeerFlow agent storage；
- materialize skill template 到 `skills/custom/deep-research-controller/`；
- 重复执行无 diff，冲突时停止并输出诊断，不覆盖同名第三方配置；
- 支持 `--check`、`--dry-run`、backup 和 redacted diff。

00 必须明确 tool/config 更改是下一次 agent build 生效，package/PYTHONPATH/checkpointer provider 更改需要 Gateway restart。

### 3. Custom Agent And Skill Templates

- committed source：`agent/config/agent-template/` 与 `agent/config/skills/`。
- runtime materialization：`DEER_FLOW_HOME/.../agents/deep-research/` 与 root `skills/custom/deep-research-controller/`。
- SOUL 只负责强制入口 Agent 调 control tool，不包含 phase prompt。
- controller skill 只解释用户入口/交互合同，不承载 graph topology。
- phase prompts 永远跟随 `graph/nodes/<name>/prompt.md`，不复制到 skills。

### 4. Research Sandbox Data

不新增代码 mount。Deep Research 只使用 DeerFlow 已有 per-thread user-data mount：

```text
Host:
  <DEER_FLOW_HOME>/users/<uid>/threads/<tid>/user-data/workspace/
Sandbox:
  /mnt/user-data/workspace/
Research root:
  /mnt/user-data/workspace/deep-research/<research_id>/
```

Graph state/checkpointer 不放进 sandbox；sandbox 只保存 evidence/cache/work outputs/final artifacts。所有 node 通过 RuntimeAdapter 提供的 canonical virtual research root 操作，禁止自己拼 host path。

## 后续 Change 如何补一个 Node

后续 AI Coding 增加/替换 node 时固定执行：

1. 只进入对应 `graph/nodes/<name>/`，先写 `contracts.py` 和 fake/real contract test。
2. 实现 `node.py`；agentic node 增加同目录 `prompt.md`，门禁规则增加 `gates.py`。
3. 在 `__init__.py` export `NODE_SPEC`，不得让 builder import node 内部符号。
4. 只在 `graph/topology.py` 修改合法 edge；若逻辑 node 名不变则 topology 不应变化。
5. 测试放到镜像路径 `tests/unit/nodes/<name>/`，再跑 full-fake 与 mixed-graph E2E。
6. 需要共享能力时，先判断属于 domain/engine/agents/runtime 哪一层；禁止顺手丢到 root helper。
7. 更新 `agent/AGENTS.md` 仅记录稳定架构规则，不记录一次性实现过程。

## Scope

- 按 Canonical Folder Structure 建立目录、`agent/AGENTS.md`、package/pyproject、公共 import surface 和版本边界。
- 建立 downstream local/prod launcher 与 Docker override/等价装配，并记录与上游同步的维护边界。
- 通过 root config `tools[].use` 加载一个最小 `deep_research` control tool shell。
- 建立 RuntimeAdapter：提取 authenticated user、outer thread/run、sandbox state、thread data、AppConfig、stream/cancel handles。
- 建立 GraphHost 接口：启动、取得 provider、编译/缓存 graph、关闭资源；先托管单节点 `infra_probe` graph。
- 建立 namespace derivation 和 collision/isolation smoke contract，但不定义完整 ResearchState。
- 建立 dedicated custom Agent/SOUL/entry skill 的最小入口，只允许调用 control tool/probe，不执行研究。
- 明确 hot-reload/restart 边界、配置文件、secret redaction 和日志字段。
- 建立 folder-shape、NodeSpec、import-direction、config-fragment、mount-path contract tests。

## 基础设施 Smoke Flow

```text
DeerFlow lead_agent
  -> deep_research(action="infra_probe")
  -> RuntimeAdapter validates identity/sandbox
  -> GraphHost invokes one-node smoke graph
  -> checkpoint write/read
  -> structured ToolMessage returns derived refs (no secrets)
```

## 验收

- fresh checkout 通过文档化命令在 local dev、prod、Docker 启动，无手工环境修补。
- `tools[].use` 在三种环境解析到同一 package/version；`uv sync`/restart 后仍成立。
- smoke graph 能读取独立 checkpoint namespace，且不污染 lead-agent checkpoint。
- RuntimeAdapter 在伪造 thread/user 参数、缺 sandbox、跨用户访问时 fail closed。
- GraphHost 重复调用复用资源，shutdown 后无连接/线程泄漏。
- `backend/`、`frontend/` 零修改；新增的 downstream launcher 有独立测试/doctor check。
- 任一 node 放错目录、node 间直接 import、domain 反向 import、配置反射路径漂移都会被 contract test 拦截。
- `configure.py --check` 能从 fresh config 与已配置环境验证相同预期，不产生重复 tool/agent/skill。

## Non-Goals

- 不建立完整 phase topology、HITL、rerun 或 fake research nodes。
- 不定义 ResearchState、gate、WorkSpec、submission ledger。
- 不调用真实 LLM、web search 或写 research artifacts。

## 风险 / 取舍

- [风险] additive launcher 与上游 `scripts/serve.sh` 漂移。→ launcher 尽量只负责环境/命令装配，加入 upstream-command contract test，不复制整套业务逻辑。
- [风险] checkpointer provider 无可安全复用的进程级 API。→ 00 必须用 smoke test确认生命周期；不能把风险留给 01。
- [风险] custom tool 无法透传所需 stream/cancel context。→ 明确列出缺口；若为硬缺口，00 停止并重新评估挂载 seam。

## 落地关联

00 通过后，01 只能消费已冻结的 package、launcher、RuntimeAdapter 和 GraphHost，不再夹带基础设施选型。
