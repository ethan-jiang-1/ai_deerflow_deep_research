# Plan: Deep Research 00 - Runtime Infrastructure

> 类型: 设计 / 基础设施 | 更新: 2026-07-11
> 对应 OpenSpec change: `establish-deep-research-runtime-infrastructure`
> 依赖: 无
> 在主图中的作用: 提供 01 及以后所有 graph/node 共用的源码落点、加载方式、挂载配置、上下文、权限和资源生命周期底座

## 目标

00 先回答“Deep Research graph 最终怎样架到 DeerFlow 上、代码放哪里、后续 node 怎么补”。本 change 不搭业务 graph，但必须交付一个能被 DeerFlow 标准运行环境稳定加载的最小纵切面：source-mounted Python package、reflected control tool、trusted runtime context、官方 checkpointer 使用方式、node-agent runtime 基座、folder-shape/import/config/mount contract tests。

这不是 01 的前置小工具，而是整个项目的地基。00 没有把文件结构和边界定死，后面 01-18 的 AI Coding 会自然长出第二套目录、第二套 helper、第二条权限路径。

## 必须先定死的架构决策

- **执行形态：in-process custom tool + nested StateGraph。** Deep Research 需要父 thread 的身份、sandbox、stream/cancel/runtime context；MCP/ACP 不作为默认承载。
- **代码归属：顶层自有 source-mounted package。** 源码在 `agent/src/deerflow_deep_research/`，不放入 `backend/`/`frontend/`，也不修改上游 backend workspace；通过 launcher/Docker override 显式加入 `PYTHONPATH`。
- **入口形态：全局 tool + public entry skill + per-user dedicated Agent。** `deep_research` tool 是真实入口；public skill 只是用户交互合同；dedicated Agent/SOUL 只是 UX 引导，不是安全边界。
- **控制权边界：Python graph 控制 phase/state，node 内 DeerFlow agent loop 做开放式判断。** DPT 的 graph/state/gate/work-unit 语义保留，只把 Markdown controller 换成 Python controller。
- **资源生命周期：GraphHost 不假设 Gateway lifespan hook。** reflected `BaseTool` 无可靠 app lifespan 接口；第一版 GraphHost 缓存 topology/builders，不持有长期 DB 连接。SQLite/Postgres 每次 tool action 用 `deerflow.runtime.checkpointer.async_provider.make_checkpointer(app_config)` 开启官方 async context，compile/invoke/resume 后确定关闭。memory backend 可保留进程内 saver，但明确不支持进程重启恢复。
- **权限不靠 prompt。** Agent/SOUL/tool_groups 只能降低误用概率；RuntimeAdapter、node-agent policy、path middleware、submit/gate 才是权限边界。
- **身份来源：trusted runtime。** user/thread/run/sandbox 只能从 DeerFlow runtime/config/context/state 派生，模型参数和用户输入不能覆盖。

## Canonical Folder Structure

00 必须实际创建并用 `agent/AGENTS.md` 固定以下结构。后续 change 不得在 repo root、`backend/` 或 `frontend/` 另起第二套 Deep Research 源码树。

```text
agent/
├── AGENTS.md                         # 本模块目录/依赖/测试规约，后续 AI Coding 必读
├── README.md                         # 安装、配置、启动、诊断
├── Makefile                          # configure/doctor/test/dev wrapper
├── pyproject.toml                    # 独立 Python package；不改 backend/pyproject.toml
├── src/
│   └── deerflow_deep_research/
│       ├── __init__.py               # 仅稳定公共 API，使用 lazy exports
│       ├── config.py                 # 本项目配置 model/解析，不读取业务 state
│       ├── tool.py                   # tools[].use 稳定入口 deep_research_tool
│       │
│       ├── runtime/                  # DeerFlow/Gateway integration boundary
│       │   ├── graph_host.py         # builder/topology/cache；不默认持有长期 DB 连接
│       │   ├── runtime_adapter.py    # DeerFlow Runtime -> trusted GraphContext
│       │   ├── identity.py           # user/thread/research namespace derivation
│       │   ├── checkpoint.py         # make_checkpointer wrapper + namespace policy
│       │   ├── events.py             # outer stream/run-event projection
│       │   └── cancellation.py       # cancellation propagation contract
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
│       │   └── artifacts/            # bundle layout, hashing, path containment, publish
│       │
│       ├── agents/                   # node 内 DeerFlow agent-loop factory
│       │   ├── factory.py            # project wrapper around create_deerflow_agent()
│       │   ├── middleware.py         # path/tool/prompt-injection enforcement
│       │   ├── policies.py           # model/tool/path/budget/turn policies
│       │   ├── prompts.py            # package-resource prompt loader
│       │   └── structured_output.py  # agent result -> domain contract
│       │
│       ├── graph/                    # workflow declaration，禁止放通用业务实现
│       │   ├── builder.py            # compile StateGraph
│       │   ├── topology.py           # 唯一 top-level node/edge 拓扑真相
│       │   ├── registry.py           # 收集 NodeSpec，不含 routing judgment
│       │   ├── implementation_map.py # fake/real/mixed 选择
│       │   ├── routing.py            # 只读 typed verdict 的 routers
│       │   ├── components/           # 可复用内部组件，不直接出现在顶层 topology
│       │   │   ├── source_diagnostic/
│       │   │   └── claim_verifier/
│       │   └── nodes/                # 顶层逻辑 workflow nodes
│       │       ├── bootstrap/
│       │       ├── hitl1/
│       │       ├── topic_planning/
│       │       ├── wave0/
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
│   ├── extensions.fragment.json      # public skill enable state 片段
│   ├── agent-template/
│   │   ├── SOUL.md
│   │   └── config.yaml
│   └── public-skill/
│       └── deep-research-controller/
│           └── SKILL.md
│
├── scripts/
│   ├── configure.py                  # structured/idempotent materialization
│   ├── doctor.py                     # import/config/mount/provider checks
│   └── serve.sh                      # project-owned local dev/prod launcher
├── docker/
│   └── docker-compose.deep-research.yaml  # Gateway source/PYTHONPATH override
│
└── tests/
    ├── unit/
    │   ├── runtime/
    │   ├── domain/
    │   ├── engine/
    │   ├── agents/
    │   └── nodes/                    # 与 graph/nodes/<name>/ 一一镜像
    ├── contract/                     # folder/import/config/mount/NodeSpec contracts
    ├── graph/                        # topology/full-fake/mixed-graph
    ├── integration/                  # DeerFlow runtime/checkpointer/sandbox/mount
    ├── e2e/
    └── fixtures/
```

### 每个 Top-Level Node Package 的固定形状

每个 `graph/nodes/<phase>/` 都是独立 Python package。复杂 phase 可以在包内有 subgraph，不把 13 个 node 平铺成 `nodes.py`，也不把多个 phase 混进一个 `wave_nodes.py`：

```text
graph/nodes/<phase>/
├── __init__.py          # 只 export NODE_SPEC，不执行 IO/构图
├── node.py              # real node/subgraph entry
├── fake.py              # deterministic fake，01 起永久保留
├── contracts.py         # 仅该 node 私有的 typed input/output
├── subgraph.py          # 可选：phase-local planner/worker/submit/gate/repair graph
├── planner.py           # 可选：复杂 phase 的 planner
├── worker.py            # 可选：复杂 phase 的 worker adapter
├── materializer.py      # 可选：artifact projection
├── gates.py             # 可选：该 node 的 rule definitions；通用 kernel 在 engine/gates
├── prompt.md            # 简单 agentic node
└── prompts/             # 可选：复杂 phase 的多角色 prompt
    ├── planner.md
    ├── worker.md
    └── repair.md
```

`NODE_SPEC` 是 builder 唯一认识的 node surface，至少声明稳定 name、real callable/factory、fake callable/factory、input/output contract、所属 phase 和所需 policy。顶层 topology 只看稳定逻辑 node name；`graph/components/` 里的可复用 critic/diagnostic 组件不作为顶层 topology node 出现，避免“可复用子流程”和“主图阶段”混在一起。

禁止创建 `utils.py`、`helpers.py`、`common.py`。共享代码必须按领域命名并有明确 owner。

### Shared Code 放置规则

- 跨 node 的 **数据结构** 放 `domain/`；只被一个 node 使用的结构留在该 node 的 `contracts.py`。
- 跨 node 的 **确定性算法/IO policy** 放 `engine/`；只被一个 node 使用的动作留在 `node.py`/`planner.py`/`worker.py`。
- DeerFlow Runtime、checkpointer、stream、sandbox handle 的适配只放 `runtime/`。
- `create_deerflow_agent()` wrapper、model/tool/prompt/path/budget policy 只放 `agents/`。
- node-specific prompt 跟 node 放；只有被至少两个 nodes 实际引用的片段才能进入 `resources/shared_prompts/`。
- public skill 只描述入口合同；phase prompt 永远不复制到 skill。

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
- 一个 node 不直接 import 另一个 node；跨 phase 只通过 `ResearchState`、artifact refs 和 topology edge。
- 自有 package 永不 import `app.*`，也永不被 `deerflow.*` 反向 import。
- `tool.py` 保持薄，只做 schema/tool entry 和调用 `GraphHost`，不包含 research business logic。

00 必须增加 AST import-boundary test，把这些规则变成 CI gate。

## Mount And Configuration Contract

这里区分四种完全不同的“mount”，后续不得混用。

### 1. Gateway Host Python Source

- 本地源码真相：`<repo>/agent/src/deerflow_deep_research/`。
- local launcher 从 `backend/` 启动 Gateway，但显式设置 `PYTHONPATH=<repo>/agent/src:.`。
- local `DEER_FLOW_PROJECT_ROOT=<repo>`，`DEER_FLOW_HOME=<repo>/backend/.deer-flow`。
- Docker dev/prod 中 project root 是 `/app` 或上游 compose 对应的 repo bind；override 必须把 `agent/src` 加进 Gateway `PYTHONPATH`。
- 生产 Docker image 默认不含 `agent/`；必须通过 downstream override 只读 mount 或在 downstream image bake 入 `agent/`。
- `agent/docker/docker-compose.deep-research.yaml` 只做 Gateway source/PYTHONPATH/config mount 覆盖，不修改上游 `backend/Dockerfile` 或原 compose 文件。
- `deerflow.fragment.yaml` 的稳定反射路径固定为 `deerflow_deep_research.tool:deep_research_tool`。

Host source 只供 Gateway Python 进程 import，绝不挂进 research sandbox。

### 2. DeerFlow Runtime Configuration

`agent/config/` 保存可提交模板；真实 `config.yaml`、`extensions_config.json`、`skills/` 和 `.deer-flow/` 仍是 runtime truth。

`scripts/configure.py` 必须用 YAML/JSON parser 做 idempotent merge：

- `config.yaml -> tool_groups += deep-research-control`；
- `config.yaml -> tools += {name: deep_research, group: deep-research-control, use: deerflow_deep_research.tool:deep_research_tool}`；
- `extensions_config.json` 启用 public skill `deep-research-controller`；
- materialize committed public skill 到 `<repo>/skills/public/deep-research-controller/SKILL.md`；
- materialize dedicated Agent template 到 `{DEER_FLOW_HOME}/users/{user_id}/agents/deep-research/{config.yaml,SOUL.md}`；
- 默认 no-auth `user_id` 是 `default`；authenticated 环境必须显式传入已验证 user id，或通过当前用户 API provision；
- 重复执行无 diff，冲突时停止并输出诊断，不覆盖同名第三方配置；
- 支持 `--check`、`--dry-run`、backup 和 redacted diff。

不得向 legacy shared agent path 写入新文件：

```text
{DEER_FLOW_HOME}/agents/deep-research/                 # read-only fallback only
<repo>/skills/custom/deep-research-controller/         # legacy/global custom，不作为新设计
```

00 必须明确生效边界：tool/config/Agent/skill 更改对下一次 agent build 生效；package/PYTHONPATH/checkpointer provider 更改需要 Gateway restart。

### 3. Public Entry Skill And Per-User Agent

- committed source：`agent/config/public-skill/deep-research-controller/SKILL.md`。
- runtime public skill：`<repo>/skills/public/deep-research-controller/SKILL.md`，enabled state 在 `extensions_config.json`。
- committed Agent template：`agent/config/agent-template/{SOUL.md,config.yaml}`。
- runtime Agent：`{DEER_FLOW_HOME}/users/{user_id}/agents/deep-research/`。
- Agent config references the public skill and the `deep-research-control` tool group.
- SOUL 只负责把用户入口稳定引导到 `deep_research` control tool，不包含 phase prompt。
- public skill 只解释用户入口/交互合同，不承载 graph topology。
- future authenticated users 不能靠一次性 configure 预创建；需要 current-user `POST /api/agents` path 或 operator CLI with explicit validated user id。
- dedicated Agent 缺失不能使全局 `deep_research` tool 不可用；它只影响推荐入口和 UX。

重要限制：`tool_groups` 过滤的是配置工具面，DeerFlow 仍会追加 built-in/MCP/ACP 等工具。计划不得声称 dedicated Agent “只暴露 control tool”。安全必须由 `RuntimeAdapter`、nested graph、node tool/path policy 和 submit/gate 执行。

### 4. Skills And Sandbox Mount

- skills host root 是 `<repo>/skills`，sandbox 中是 `/mnt/skills`。
- public skill 可以被 agent 读取；phase prompt 从 package resources 加载，不要求 sandbox skill mount。
- source code 不挂进 sandbox；node agent 不能通过 `/mnt/skills` 或 workspace 读取 `agent/src`。
- Deep Research 只使用 DeerFlow 已有 per-thread user-data mount：

```text
Host:
  {DEER_FLOW_HOME}/users/<uid>/threads/<tid>/user-data/workspace/
Sandbox:
  /mnt/user-data/workspace/
Research root:
  /mnt/user-data/workspace/deep-research/<research_id>/
```

Graph state/checkpointer 不放进 sandbox；sandbox 只保存 evidence/cache/work outputs/final artifacts。所有 node 通过 `RuntimeAdapter` 提供的 canonical virtual research root 操作，禁止自己拼 host path。

## RuntimeAdapter And GraphHost Contract

### RuntimeAdapter

00 必须建立 `RuntimeAdapter`，从 DeerFlow tool runtime 中提取并验证：

- effective user id、outer thread id、outer run/request attribution；
- `thread_data` 中的 workspace/outputs/uploads host path 与 virtual path；
- sandbox availability；
- `AppConfig`、model/tool runtime hints；
- stream writer、cancellation signal、runtime context。

RuntimeAdapter 输出 typed `GraphContext`，只含 Deep Research 允许使用的 view。模型参数、tool action payload、用户输入里的 user/thread/research id 只能作为待校验输入，不能覆盖 trusted context。

### GraphHost

00 的 GraphHost 第一版只拥有：

- graph builder/topology cache；
- implementation map selection；
- checkpoint namespace derivation；
- per-action checkpointer context management；
- invoke/resume/status/cancel shell。

GraphHost 第一版不拥有：

- Gateway app lifespan hook；
- `app.state.checkpointer`；
- long-lived SQLite/Postgres connection pool；
- business state schema。

SQLite/Postgres 的调用模型：

```text
tool action
  -> RuntimeAdapter builds GraphContext
  -> GraphHost derives checkpoint namespace
  -> async with make_checkpointer(app_config) as checkpointer:
       compile graph with checkpointer
       invoke/resume/status
  -> close provider context
```

持久 DB 负责跨调用/重启恢复；memory backend 只保证同进程内行为，01 的 restart/resume 验收只对 SQLite/Postgres 成立。

## Node-Agent Runtime Foundation

00 不实现真实 research node，但必须把所有真实 node 都要用的 bounded DeerFlow agent adapter 建起来并测试。

`agents/factory.py` 必须封装：

- 调用 DeerFlow `create_deerflow_agent()`；
- 默认采用 full middleware takeover 或经测试的 feature configuration，避免自动加入不适合 phase agent 的 clarification/tool surface；
- 不给 node agent 单独 checkpointer，避免 node 内产生第二套持久控制状态；
- 透传 parent `sandbox`、`thread_data`、runtime context 和 cancellation；
- 建立 model/tool/turn/token/wall-time policies；
- 禁止 phase agent 使用 `ask_clarification`；HITL 只能由 graph HITL nodes 发起；
- structured output normalization 与 validation；
- stream/progress projection 到 outer run events。

`agents/middleware.py` 或等价 policy 必须代码级 enforce：

- read roots；
- write roots；
- allowed tool names；
- no phase/gate/ledger mutation；
- no cross-attempt writes；
- external source text 只能作为 untrusted data，不进入 system/developer prompt；
- source text 中的“忽略规则/调用工具/修改 ledger”等内容永远不能成为控制指令。

这些在 00 用 fake tools/fake runtime 测掉；08 Wave0 再用真实网页/缓存路径做对抗样例。

## 后续 Change 如何补一个 Node

后续 AI Coding 增加/替换 node 时固定执行：

1. 只进入对应 `graph/nodes/<name>/`，先写 `contracts.py` 和 fake/real contract test。
2. 简单 node 实现 `node.py`；复杂 node 增加 `subgraph.py`、`planner.py`、`worker.py`、`materializer.py` 等固定文件名。
3. agentic node 增加同目录 `prompt.md` 或 `prompts/<role>.md`；门禁规则增加 `gates.py`。
4. 在 `__init__.py` export `NODE_SPEC`，不得让 builder import node 内部符号。
5. 只在 `graph/topology.py` 修改合法 edge；若逻辑 node 名不变则 topology 不应变化。
6. 测试放到镜像路径 `tests/unit/nodes/<name>/`，再跑 full-fake 与 mixed-graph E2E。
7. 需要共享能力时，先判断属于 `domain/engine/agents/runtime/graph/components` 哪一层；禁止顺手丢到 root helper。
8. 更新 `agent/AGENTS.md` 仅记录稳定架构规则，不记录一次性实现过程。

## Scope

- 建立 `agent/` 目录、`agent/AGENTS.md`、package/pyproject、公共 import surface 和版本边界。
- 建立 source-mounted local/prod launcher 与 Docker override/等价装配，并记录与上游同步的维护边界。
- 通过 root config `tools[].use` 加载最小 `deep_research` control tool shell。
- 建立 public entry skill 和 per-user dedicated Agent provisioning；不写 legacy shared agent/global custom skill。
- 建立 RuntimeAdapter：提取 authenticated user、outer thread/run、sandbox state、thread data、AppConfig、stream/cancel handles。
- 建立 GraphHost：builder/topology cache、checkpoint namespace、per-action `make_checkpointer()` context；先托管单节点 `infra_probe` graph。
- 建立 namespace derivation 和 collision/isolation smoke contract，但不定义完整 ResearchState。
- 建立 node-agent runtime foundation：bounded agent factory、middleware/policy、path/tool/prompt-injection enforcement、structured output normalization。
- 明确 hot-reload/restart 边界、配置文件、secret redaction 和日志字段。
- 建立 folder-shape、NodeSpec、import-direction、config-fragment、mount-path、path-policy、prompt-injection contract tests。

## 基础设施 Smoke Flow

```text
DeerFlow lead_agent or dedicated deep-research Agent
  -> deep_research(action="infra_probe")
  -> RuntimeAdapter validates identity/sandbox/thread_data
  -> GraphHost derives namespace
  -> async with official make_checkpointer(app_config)
  -> one-node smoke graph checkpoint write/read
  -> fake node-agent policy denies out-of-scope read/write/tool
  -> structured ToolMessage returns derived refs (no secrets)
```

## 验收

- fresh checkout 通过文档化命令在 local dev、prod、Docker 启动，无手工环境修补。
- `tools[].use` 在三种环境解析到同一 package/version；restart 后仍成立。
- `configure.py --check` 能从 fresh config 与已配置环境验证相同预期，不产生重复 tool/Agent/skill。
- no-auth 写入 `{DEER_FLOW_HOME}/users/default/agents/deep-research/`；authenticated provisioning 写入指定已验证 user id；不写 legacy shared paths。
- public skill materialized to `<repo>/skills/public/deep-research-controller/`，not `skills/custom/`。
- smoke graph 能读取独立 checkpoint namespace，且不污染 lead-agent checkpoint。
- SQLite/Postgres 后端支持 tool action 后关闭 provider context，restart 后 probe checkpoint 可恢复；memory 后端明确只测同进程。
- RuntimeAdapter 在伪造 thread/user 参数、缺 sandbox、跨用户访问时 fail closed。
- node-agent adapter 能继承 parent sandbox/thread_data/cancel context，不创建独立 checkpointer。
- path/tool policy 对越界读写、非白名单工具、ledger/gate mutation、cross-attempt 写入全部 fail closed。
- prompt-injected source fixture 不能改变 system/developer instruction、不能获得 tool/ledger/control 权限。
- `backend/`、`frontend/` 零修改；新增 downstream launcher 有独立测试/doctor check。
- 任一 node 放错目录、node 间直接 import、domain 反向 import、配置反射路径漂移都会被 contract test 拦截。

## Non-Goals

- 不建立完整 phase topology、HITL、rerun 或 fake research nodes。
- 不定义 ResearchState、gate、WorkSpec、submission ledger 业务 schema。
- 不调用真实 LLM、web search 或写 research artifacts。
- 不解决最终 artifact publication；16 负责 workspace-to-outputs publish。

## 风险 / 取舍

- [风险] source-mounted launcher 与上游 `scripts/serve.sh` 漂移。→ launcher 只负责环境/命令装配，加入 upstream-command contract test，不复制上游业务逻辑。
- [风险] reflected tool 无 lifespan hook，长期 provider 复用不可控。→ 第一版用官方 per-action async context；只有 00 实证找到稳定 hook 后才升级为进程级池。
- [风险] dedicated Agent 被误当安全边界。→ 文档、SOUL 和测试都明确：权限在 RuntimeAdapter/node policy/submit/gate；Agent 只是 UX。
- [风险] `create_deerflow_agent()` 默认 feature chain 带入不合适 middleware。→ 00 必须用 full takeover 或 verified configuration，并用 contract test 锁住。
- [风险] prompt-injection 发现太晚。→ 00 建 untrusted-source invariant；08/09/18 逐层加强。
- [风险] authenticated future users 无法由一次 configure 预创建 Agent。→ 支持 current-user API 或 operator CLI；tool 本身不依赖 dedicated Agent 存在。

## 落地关联

00 通过后，01 只能消费已冻结的 package、launcher、RuntimeAdapter、GraphHost 和 node-agent runtime，不再夹带基础设施选型。真实 business nodes 必须沿着 00 定义的目录、import、mount、path policy 和 prompt-loading 规则逐个替换。
