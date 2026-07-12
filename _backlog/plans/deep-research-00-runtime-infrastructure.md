# Plan: Deep Research 00 - Runtime Infrastructure

> 类型: 设计 / 基础设施 | 更新: 2026-07-12
> 状态: runtime substrate 已完成并归档；launcher/Docker live smoke/Postgres profile 已转入 deployment follow-up
> 对应 OpenSpec change: `establish-deep-research-runtime-infrastructure`
> 依赖: 无
> 在主图中的作用: 提供 01 及以后所有 graph/node 共用的源码落点、加载方式、挂载配置、上下文、权限和资源生命周期底座

## 目标

> 完成说明：本计划的 runtime substrate 已由归档 change 交付并通过 zero-API、
> file-SQLite provider reopen 与 subprocess restart 验证。未交付的本地 launcher、
> Docker live smoke 和 Postgres profile 不再属于 00/01 的完成门槛，分别记录在
> `_backlog/todos/deferred_deep-research-00-launcher-and-docker.md` 与
> `_backlog/todos/deferred_deep-research-00-postgres-profile.md`。

00 先回答“Deep Research graph 最终怎样架到 DeerFlow 上、代码放哪里、后续 node 怎么补”。本 change 不搭业务 graph，但必须交付一个能被 DeerFlow 标准运行环境稳定加载的最小纵切面：local editable/Docker source-mounted Python package、reflected control tool、trusted runtime context、官方 checkpointer 使用方式、node-agent runtime 基座、folder-shape/import/config/mount contract tests。

这不是 01 的前置小工具，而是整个项目的地基。00 没有把文件结构和边界定死，后面 01-18 的 AI Coding 会自然长出第二套目录、第二套 helper、第二条权限路径。

## 必须先定死的架构决策

- **执行形态：in-process custom tool + nested StateGraph。** Deep Research 需要父 thread 的身份、sandbox、stream/cancel/runtime context；MCP/ACP 不作为默认承载。
- **代码归属：顶层自有 source-backed package。** 源码在 `agent/src/deerflow_deep_research/`，不放入 `backend/`/`frontend/`，也不修改上游 backend workspace；local 用 sync 后 editable install，Docker override 用只读 source mount + `PYTHONPATH`。
- **入口形态：全局 tool + public entry skill + per-user dedicated Agent。** `deep_research` tool 是真实入口；public skill 只是用户交互合同；dedicated Agent/SOUL 只是 UX 引导，不是安全边界。
- **控制权边界：Python graph 控制 phase/state，node 内 DeerFlow agent loop 做开放式判断。** DPT 的 graph/state/gate/work-unit 语义保留，只把 Markdown controller 换成 Python controller。
- **资源生命周期：GraphHost 不假设 Gateway lifespan hook。** reflected `BaseTool` 无可靠 app lifespan 接口；第一版 GraphHost 缓存 topology/builders，不持有长期 DB 连接。SQLite/Postgres 每次 tool action 用 `deerflow.runtime.checkpointer.async_provider.make_checkpointer(app_config)` 开启官方 async context，compile/invoke/inspect 后确定关闭。effective provider 必须遵循官方 legacy `checkpointer` 优先于 `database` 的规则；memory backend 可保留进程内 saver，但明确不支持进程重启恢复。
- **权限不靠 prompt。** Agent/SOUL/tool_groups 只能降低误用概率；RuntimeAdapter、node-agent policy、path middleware、submit/gate 才是权限边界。
- **身份来源：trusted runtime。** 必须显式存在 server-injected `runtime.context.user_id`；通用 helper 静默回退的 `default` 不算认证。thread/run/sandbox 只能从 DeerFlow runtime context/state 派生，模型参数和用户输入不能覆盖。

## Canonical Folder Structure

00 必须实际创建 `agent/` package/test/config/tooling 的所有权根和自己真正实现的 infra modules，并用 `agent/AGENTS.md`、folder contract 和 NodeSpec fixtures 固定以下完整目标结构。图中标为 `(01+)`/`(02+)`/`(03+)` 的 topology、engine kernel 和业务 node 只在对应 change 同时提供有效合同与测试时创建；禁止为了“看起来齐全”预建空 package 或 placeholder API。后续 change 不得在 repo root、`backend/` 或 `frontend/` 另起第二套 Deep Research 源码树。

```text
agent/
├── AGENTS.md                         # 本模块目录/依赖/测试规约，后续 AI Coding 必读
├── README.md                         # 安装、配置、启动、诊断
├── Makefile                          # configure/doctor/test/dev wrapper
├── pyproject.toml                    # 独立 Python package；不改 backend/pyproject.toml
├── uv.lock                           # agent project 的可复现依赖锁
├── src/
│   └── deerflow_deep_research/
│       ├── __init__.py               # 仅稳定公共 API，使用 lazy exports
│       ├── __about__.py              # single-source package version；source mount 也可读
│       ├── tool.py                   # tools[].use 稳定入口 deep_research_tool
│       │
│       ├── runtime/                  # DeerFlow/Gateway integration boundary
│       │   ├── graph_host.py         # builder/topology/cache；不默认持有长期 DB 连接
│       │   ├── runtime_adapter.py    # DeerFlow Runtime -> TrustedRuntimeEnvelope only
│       │   ├── projection.py         # validated research scope -> pure graph/node-agent views
│       │   ├── identity.py           # user/thread/research namespace derivation
│       │   ├── checkpoint.py         # make_checkpointer wrapper + namespace policy
│       │   ├── events.py             # outer stream/run-event projection
│       │   ├── cancellation.py       # cancellation propagation contract
│       │   ├── diagnostics.py        # reusable local/container readiness checks
│       │   ├── startup_snapshot.py   # secret-free startup-only config fingerprint
│       │   └── node_agent_bridge.py  # raw parent binding -> bounded child invocation
│       │
│       ├── domain/                   # 纯共享数据合同，不含 IO/DeerFlow 调用
│       │   ├── enums.py
│       │   ├── context.py            # pure GraphContextView/NodeAgentContext/capability contracts
│       │   ├── node_spec.py          # pure NodeSpec + PolicyRef；避免 nodes -> graph 反向依赖
│       │   ├── state.py              # ResearchState + reducers (02+)
│       │   ├── gates.py              # Gate contracts (03+)
│       │   ├── work_units.py         # WorkSpec/Attempt/Submission (04+)
│       │   ├── evidence.py           # Source/Claim/Finding contracts (09+)
│       │   └── delivery.py           # readiness/final contracts (15+)
│       │
│       ├── engine/                   # owner root；03+ 随真实合同增加具名子包
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
│       │   ├── registry.py           # 收集 NodeSpec，不含 routing judgment
│       │   ├── infra_probe.py        # 00 独立诊断 graph，不是假业务 topology
│       │   ├── topology.py           # 唯一 top-level node/edge 拓扑真相 (01+)
│       │   ├── implementation_map.py # fake/real/mixed 选择 (01+)
│       │   ├── routing.py            # 只读 typed verdict 的 routers (01+)
│       │   ├── components/           # 可复用内部组件 (01+)，不直接出现在顶层 topology
│       │   │   ├── source_diagnostic/
│       │   │   └── claim_verifier/
│       │   └── nodes/                # 顶层逻辑 workflow nodes (01+)
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
│           ├── node_agent/
│           │   └── runtime_policy.md # 00 generic bounded-agent policy prompt
│           └── shared_prompts/       # 两个以上 real nodes 实际复用时才创建
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
│   ├── prepare.py                    # no-orchestration sync/install/fingerprint pipeline
│   ├── doctor.py                     # import/config/mount/provider checks
│   └── serve.sh                      # project-owned local dev/prod launcher
├── docker/
│   ├── docker-compose.deep-research.yaml  # Gateway source/PYTHONPATH override
│   └── docker-compose.postgres-test.yaml  # isolated required provider/restart profile
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

`NODE_SPEC` 是 builder 唯一认识的 node surface，纯合同定义在 `domain/node_spec.py`，至少声明稳定 name、real factory、fake factory、input/output contract、所属 phase 和纯 `PolicyRef`。real/fake factory 只接收 pure `NodeBuildDependencies`，其中只有 reduced context 和 `NodeExecutionCapabilities`。node package 不反向 import `graph/registry.py`；registry 只加载 topology 明确列出的 package root 并读取公开 `NODE_SPEC`，不做隐式 filesystem discovery，也不直接 import 私有 node module。顶层 topology 只看稳定逻辑 node name；`graph/components/` 里的可复用 critic/diagnostic 组件不作为顶层 topology node 出现。

禁止创建 `utils.py`、`helpers.py`、`common.py`。共享代码必须按领域命名并有明确 owner。

### Shared Code 放置规则

- 跨 node 的 **数据结构** 放 `domain/`；只被一个 node 使用的结构留在该 node 的 `contracts.py`。
- 跨 node 的 **确定性算法/IO policy** 放 `engine/`；只被一个 node 使用的动作留在 `node.py`/`planner.py`/`worker.py`。
- DeerFlow Runtime、checkpointer、stream、sandbox handle 的适配只放 `runtime/`。
- `create_deerflow_agent()` wrapper、model/tool/prompt/path/budget policy 只放 `agents/`；raw parent binding 和实际 child invocation 只放 `runtime/node_agent_bridge.py`。
- node-specific prompt 跟 node 放；只有被至少两个 nodes 实际引用的片段才能进入 `resources/shared_prompts/`。
- public skill 只描述入口合同；phase prompt 永远不复制到 skill。

### Import Direction

```text
tool.py -> runtime -> graph -> nodes
                            nodes -> engine -> domain
                            nodes -> domain
runtime -> graph + agents + domain + deerflow.*
agents  -> domain + public deerflow.* + LangChain APIs
graph   -> domain + nodes
domain  -> stdlib + pydantic only
```

硬规则：

- `domain` 不 import `engine/agents/graph/runtime/deerflow/app`。
- `engine` 只 import `domain`。
- `agents` 只 import `domain` 和 public `deerflow.*`/LangChain APIs，不 import `runtime/graph/nodes/app`。
- node 只 import `domain/engine`，不 import `agents/runtime/graph implementation` 或另一个 node；通过 domain capability protocol 请求 agent execution。
- 一个 node 不直接 import 另一个 node；跨 phase 只通过 `ResearchState`、artifact refs 和 topology edge。
- 自有 package 永不 import `app.*`，也永不被 `deerflow.*` 反向 import。
- `tool.py` 保持薄，只做 schema/tool entry 和调用 `GraphHost`，不包含 research business logic。

00 必须增加 AST import-boundary test，把这些规则变成 CI gate。

## Mount And Configuration Contract

这里区分四种完全不同的“mount”，后续不得混用。

### 1. Gateway Host Python Source

- 本地源码真相：`<repo>/agent/src/deerflow_deep_research/`。
- 上游 local launcher 会先执行 exact `uv sync`，且从 `backend/` 以 inline `PYTHONPATH=.` 启动 Gateway；因此只在外层 `export PYTHONPATH` 或先做 editable install 都不成立。
- project-owned local launcher 必须先加载与上游相同的 root `.env`，建立相同 `DEER_FLOW_PROJECT_ROOT`/`DEER_FLOW_HOME` defaults 和 Gateway `backend/` cwd（relative SQLite path 依赖 cwd），并完成 application-state 只读 preflight：root prerequisites、AppConfig path 与当前 upstream config-upgrade target 的 canonical 一致性、effective config 的 `config_version == config.example.yaml.config_version`，以及从独立 locked agent operations environment 运行的 `configure.py --check`。root/backend shadow 或版本缺失、非法、过旧、超前时不得 stop、修改 shared backend environment 或算 fingerprint，只报告冲突并提示 operator 先协调/升级。preflight 通过后必须先委托 upstream stop，确认 quiescence 后才执行上游等价 dependency sync，把 `agent/` editable install 到 backend environment，从相同 backend cwd 计算 effective provider/sandbox/worker 的 secret-free startup candidate，显式通过 prelaunch doctor，最后以 `UV_NO_SYNC=1 --skip-install` 委托 upstream start。restart 等价为这条已验证的 stop + start，不在 downstream 复制 service orchestration。
- local `DEER_FLOW_PROJECT_ROOT=<repo>`，`DEER_FLOW_HOME=<repo>/backend/.deer-flow`。
- editable source 修改不需要重装，但 upstream dev watcher 不监视顶层 `agent/src`，因此 package code 变化仍要求 Gateway restart，不能宣称 hot reload。
- Docker dev/prod 中 project root 是 `/app` 或上游 compose 对应的 repo bind；override 必须把 `agent/src` 加进 Gateway `PYTHONPATH`，在 container-effective environment 中计算/export candidate，并在 unchanged uvicorn tokens 前通过 prelaunch doctor；只允许 runtime-not-ready 阻断，entry warning 继续启动。
- 生产 Docker image 默认不含 `agent/`；必须通过 downstream override 只读 mount 或在 downstream image bake 入 `agent/`。
- `agent/docker/docker-compose.deep-research.yaml` 只做 Gateway source/PYTHONPATH/config mount 覆盖，不修改上游 `backend/Dockerfile` 或原 compose 文件。
- `deerflow.fragment.yaml` 的稳定反射路径固定为 `deerflow_deep_research.tool:deep_research_tool`。

Host source 只供 Gateway Python 进程 import，绝不挂进 research sandbox。

### 2. DeerFlow Runtime Configuration

`agent/config/` 保存可提交模板；launch environment 下 Gateway 实际解析到的 effective `config.yaml`、`extensions_config.json`、canonical `<repo>/skills/` 和 `{DEER_FLOW_HOME}` 才是 runtime truth。configure/doctor 必须解析同一 config/extensions targets，拒绝 root/backend shadow 或写入 inert fallback。change 00 的 local/Docker mount contract 只支持 effective skills root 等于 `<repo>/skills`；`skills.path`/`DEER_FLOW_SKILLS_PATH` 指向别处时判为 runtime not ready，不悄悄复制一份实际不可见的 public skill。

`scripts/configure.py` 必须用保留 YAML comments/order/style 的 round-trip parser 和 structured JSON parser 做 idempotent merge。JSON 必须保留未知数据/key order，并尽量沿用检测到的 indent/newline；任意 whitespace 不作为语义合同，但第一次写入后必须 byte-stable：

- `config.yaml -> tool_groups += deep-research-control`；
- `config.yaml -> tools += {name: deep_research, group: deep-research-control, use: deerflow_deep_research.tool:deep_research_tool}`；
- `extensions_config.json` 启用 public skill `deep-research-controller`；
- materialize committed public skill 到 `<repo>/skills/public/deep-research-controller/SKILL.md`；
- materialize dedicated Agent template 到 `{DEER_FLOW_HOME}/users/{user_id}/agents/deep-research/{config.yaml,SOUL.md}`；
- offline filesystem provisioning 只允许非生产环境中真实启用 `DEER_FLOW_AUTH_DISABLED=1` 的 `default`；authenticated 环境必须由已登录用户通过 current-user `POST /api/agents` provision，00 不接受任意 `--user-id` 作为身份凭证；
- 重复执行无 diff，冲突时停止并输出诊断，不覆盖同名第三方配置；
- 支持 `--check`、`--dry-run`、权限收紧的 backup、redacted diff 和带 before/after hash 的 rollback manifest；rollback 发现配置或模板产物被后续修改时必须停止，不能覆盖新修改。
- `--check`/`--dry-run` 可在线执行；mutate/rollback 的操作前置条件是所有共享这些文件的 Gateway 已停止。脚本必须拒绝显式/已知本地 health endpoint 可达或检测到 project-owned local/Docker Gateway process 的情况，但不得声称本地探测能证明不存在 remote shared-filesystem writer；项目锁不能假装协调外部 writer。

不得向 legacy shared agent path 写入新文件：

```text
{DEER_FLOW_HOME}/agents/deep-research/                 # read-only fallback only
<repo>/skills/custom/deep-research-controller/         # legacy/global custom，不作为新设计
```

00 必须明确生效边界：tool/config/Agent/skill 更改对下一次 agent build 生效；package/PYTHONPATH/database/checkpointer/sandbox 更改需要 Gateway restart。

launcher/Compose command 必须把 effective `database`/legacy `checkpointer`/`sandbox`/normalized worker 的 canonical typed hash 以严格 `v1:<64 lowercase hex>` 形式作为 `DEER_FLOW_DEEP_RESEARCH_STARTUP_FINGERPRINT` 注入新 Gateway；missing/malformed/unknown version fail closed，wrapper 只读取 structured machine field，禁止 `eval` candidate output。local prelaunch doctor 只验证即将注入的 candidate 并明确标记 mode，不冒充 running-process check；进程内 doctor/RuntimeAdapter/GraphHost 则拿进程继承的 fingerprint 与 live AppConfig 比较，不得在缺失时静默重算。二者不符时必须在 sandbox/provider access 前返回 `restart_required`，避免 outer startup singleton 与 nested provider split-brain。hash 输入和 secret 不得输出。

`configure.py --check` 和 doctor 都必须区分 blocking `runtime_ready` 与 `entry_ready = ready | not_ready | unknown`；known skill/Agent defect 为 `not_ready`，只有 authenticated Agent 无法 offline attribution 且没有已知 defect 时才是 `unknown`。durability 独立报告 `same_process | restart_durable | unavailable`。launcher 只按 `runtime_ready` 阻断，entry warning 不得变成隐藏 gate。完成 change 00 仍要求 entry artifacts 最终全部 materialize/verify。

一旦 wrapper 已委托 upstream stop，后续 sync/editable install/candidate/doctor 失败必须保持 stopped 并报告失败阶段；不能把可能已重写的 backend environment 当成可回滚事务，也不能自动重启旧进程。下一次启动重新走 locked exact preparation。

### 3. Public Entry Skill And Per-User Agent

- committed source：`agent/config/public-skill/deep-research-controller/SKILL.md`。
- runtime public skill：`<repo>/skills/public/deep-research-controller/SKILL.md`，enabled state 在 `extensions_config.json`。
- committed Agent template：`agent/config/agent-template/{SOUL.md,config.yaml}`。
- runtime Agent：`{DEER_FLOW_HOME}/users/{user_id}/agents/deep-research/`。
- Agent config references the public skill and the `deep-research-control` tool group.
- SOUL 只负责把用户入口稳定引导到 `deep_research` control tool，不包含 phase prompt。
- public skill 只解释用户入口/交互合同，不承载 graph topology。
- authenticated users 不能靠一次性 configure 或任意 operator `--user-id` 预创建；第一版只支持 authenticated current-user `POST /api/agents` path。
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

- server-injected、非空的 effective user id，以及 outer thread id、outer run/request attribution；通用 helper 的 `default` fallback 不算 trusted identity；
- `thread_data` 中的 workspace/outputs/uploads host path 与 virtual path；
- sandbox availability；fresh thread 缺失时先调用 DeerFlow public async lazy initializer 获取并验证同一个 parent sandbox，不建立第二套 lifecycle；
- `AppConfig`、model/tool runtime hints；
- supported stream writer 和 runtime context；Gateway 没有向 `ToolRuntime.context` 暴露 public cancellation signal，取消只依赖 outer asyncio task cancellation/`CancelledError` 传播并由 integration probe 证明。

RuntimeAdapter 在 `runtime/` 只输出供 integration/GraphHost/bridge 使用的 `TrustedRuntimeEnvelope`，承载 raw identity、host paths、`AppConfig`、sandbox state 和 writer，不凭空制造 research id。`runtime/projection.py` 只有拿到 registered research handler 已验证的 opaque scope id 才派生 research root，并投影为 `domain/context.py` 中纯 `GraphContextView`、`NodeExecutionCapabilities` protocol 和 model-safe `NodeAgentContext`。runtime-owned bridge 是 protocol 的 concrete implementation；node 只能调用 `run_agent(request)`，不接触 AppConfig、host path、sandbox internals 或 child runtime state。tool args schema 禁止 user/thread/host/sandbox/checkpoint 字段，模型输入不能覆盖 trusted context。00 的 `infra_probe` 只验证 envelope/sandbox 并派生 diagnostic namespace，不调用 research projection、不创建 research workspace、不运行 node agent；01 research handlers 才成为公开 projection caller。

### GraphHost

00 的 GraphHost 第一版只拥有：

- graph builder/topology cache；
- generic typed action-handler registry；
- checkpoint namespace derivation；
- per-action checkpointer context management；
- fixed-size process-local same-namespace lock striping；
- 00 只注册独立 `infra_probe` invoke/inspect handler；01 才增加 `start | resume | status | cancel` fake research handlers，00 不预建同名 lifecycle methods。

GraphHost 第一版不拥有：

- Gateway app lifespan hook；
- `app.state.checkpointer`；
- long-lived SQLite/Postgres connection pool；
- business state schema。

SQLite/Postgres 的调用模型：

```text
tool action
  -> RuntimeAdapter builds TrustedRuntimeEnvelope + reduced views/capability
  -> GraphHost derives checkpoint namespace
  -> async with make_checkpointer(app_config) as checkpointer:
       compile graph with checkpointer
       invoke/inspect probe state
  -> close provider context
```

持久 DB 负责 probe checkpoint 跨调用/重启重访；memory backend 和 SQLite memory-mode 只保证同进程内行为。provider classifier 与 doctor 必须共同遵循 legacy `checkpointer` 优先于 `database`。`InfraProbeState` 带 schema version，保留在独立 probe namespace，01 不把它解释或替换成 research state。00 按上游 `${GATEWAY_WORKERS:-1}` 把 missing/empty 归一为 integer 1，并且只支持这个值；malformed、0、负数或更大值都由 doctor 判为 runtime not ready。同 namespace 仅在支持的单进程内串行。真正 interrupt/resume 和 `start | resume | status | cancel` 协议属于 01，且 01 的 restart/resume 验收只对 file-backed SQLite/Postgres 成立。

## Node-Agent Runtime Foundation

00 不实现真实 research node，但必须把所有真实 node 都要用的 bounded DeerFlow agent adapter 建起来并测试。

`runtime/node_agent_bridge.py` 是唯一 raw binding owner：从 envelope/`PolicyRef` resolve model/tool，持有 ephemeral child `ThreadState` 和 child runtime context，并实现 node 只能看到的 `NodeExecutionCapabilities`。raw identity/AppConfig/host path/sandbox internals 不进入 node args、research checkpoint、event 或 model request。

`agents/factory.py` 必须封装：

- 调用 DeerFlow `create_deerflow_agent()`；
- 采用已由当前 DeerFlow 2.1 factory 验证的 `middleware=[...]` full takeover，避免自动加入不适合 phase agent 的 clarification/tool surface；
- child 作为 bridge 内单独 runnable 调用，传 `checkpointer=None`，不作为会继承 parent saver 的 graph subgraph node；
- bridge 在 ephemeral child state/context 中复用 parent `sandbox`、`thread_data`、runtime attribution 和 cancellation，不建立新 lifecycle；
- 建立 model-call/tool-call/per-response/parallelism/token/model-output/tool-result/structured-result/wall-time policies；pre-call token admission 默认使用覆盖 actual messages/tool schemas 的 deterministic no-network UTF-8 byte upper bound，再用 actual usage reconciliation；
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
4. 在 `__init__.py` export `NODE_SPEC`；topology 显式登记 package root，registry 不直接 import node 内部 module。
5. 只在 `graph/topology.py` 修改合法 edge；若逻辑 node 名不变则 topology 不应变化。
6. 测试放到镜像路径 `tests/unit/nodes/<name>/`，再跑 full-fake 与 mixed-graph E2E。
7. agentic node 只调用注入的 `NodeExecutionCapabilities`，不直接 import `agents/runtime`；需要共享能力时，先判断属于 `domain/engine/agents/runtime/graph/components` 哪一层。
8. 更新 `agent/AGENTS.md` 仅记录稳定架构规则，不记录一次性实现过程。

## Scope

- 建立 `agent/` 目录、`agent/AGENTS.md`、package/pyproject/uv.lock、公共 import surface 和版本边界。
- 建立 local sync-then-editable-install launcher 与 Docker read-only source override，并记录与上游同步的维护边界。
- 通过 root config `tools[].use` 加载最小 `deep_research` control tool shell。
- 建立 public entry skill 和 per-user dedicated Agent provisioning；不写 legacy shared agent/global custom skill。
- 建立 RuntimeAdapter：严格要求 server-injected identity，提取 outer thread/run、thread data、AppConfig 和 supported stream writer；fresh thread 用 public async initializer 获取同一个 parent sandbox；取消只依赖 outer asyncio task cancellation，不虚构 runtime cancel handle。
- 建立 runtime-owned node-agent bridge：raw binding 只存在于 ephemeral child state/context，node 只看到 pure capability protocol。
- 建立 GraphHost：builder/topology cache、generic action registry、effective-provider classifier、checkpoint namespace、single-worker same-key serialization、per-action `make_checkpointer()` context；先托管独立 namespace 的单节点 `infra_probe` graph。
- 建立 namespace derivation 和 collision/isolation smoke contract，但不定义完整 ResearchState。
- 建立 node-agent runtime foundation：bounded agent factory、middleware/policy、path/tool/prompt-injection enforcement、structured output normalization。
- 明确 hot-reload/restart 边界、配置文件、secret redaction 和日志字段。
- 建立 folder-shape、NodeSpec、import-direction、config-fragment、mount-path、path-policy、prompt-injection contract tests。

## 基础设施 Smoke Flow

```text
DeerFlow lead_agent or dedicated deep-research Agent
  -> deep_research(action="infra_probe")
  -> RuntimeAdapter requires injected identity, initializes/reuses parent sandbox,
     validates thread_data, and builds runtime-only envelope + reduced views
  -> GraphHost derives namespace
  -> same-key process lock + effective provider selection
  -> async with official make_checkpointer(app_config) for SQLite/Postgres
  -> one-node smoke graph checkpoint write/read
  -> structured tool result returns opaque refs (no secrets)
```

node-agent policy 通过独立 fake bridge/fake tool contracts 验证，不把 agent loop 偷塞进 `infra_probe`。

## 验收

- fresh checkout 通过文档化命令在 local dev、prod、Docker 启动，无手工环境修补。
- `tools[].use` 在三种环境解析到同一 package/version；restart 后仍成立。
- `configure.py --check` 能从 fresh config 与已配置环境验证相同预期，不产生重复 tool/Agent/skill。
- no-auth 写入 `{DEER_FLOW_HOME}/users/default/agents/deep-research/`；authenticated provisioning 只走 current-user `POST /api/agents`，offline configure 不接受任意 user id；不写 legacy shared paths。
- public skill materialized to `<repo>/skills/public/deep-research-controller/`，not `skills/custom/`。
- smoke graph 能读取独立 checkpoint namespace，且不污染 lead-agent checkpoint。
- legacy `checkpointer`/`database` 冲突时 GraphHost 与 doctor 选择同一 effective provider；file-backed SQLite/Postgres action 后关闭 provider context，subprocess restart 后 probe checkpoint 可恢复；memory 与 SQLite memory-mode 只测同进程，缺失/非法 persistent connection 不得报 ready。
- live startup-only config drift 在 sandbox/provider access 前稳定返回 `restart_required`，不打开另一套 nested backend。
- RuntimeAdapter 拒绝伪造 authority fields、缺失显式 injected identity、跨用户路径和 sandbox initializer failure；fresh thread 的正常 lazy sandbox 初始化必须成功。
- runtime bridge 能在 ephemeral child binding 中复用 parent sandbox/thread_data/cancellation；node/model/checkpoint 看不到 raw binding，child 不创建独立 checkpointer。
- node-agent model-call/tool-call/parallelism/token/output/tool-result/structured-result/wall-time budgets 均 fail closed；缺 usage metadata 终止为 `usage_unavailable`。
- path/tool policy 对越界读写、非白名单工具、ledger/gate mutation、cross-attempt 写入全部 fail closed。
- prompt-injected source fixture 不能改变 system/developer instruction、不能获得 tool/ledger/control 权限。
- `backend/`、`frontend/` 零修改；新增 downstream launcher 有独立测试/doctor check。
- 任一 node 放错目录、node 间直接 import、domain 反向 import、配置反射路径漂移都会被 contract test 拦截。
- `GATEWAY_WORKERS` 只有 missing/empty/等价整数 1 能通过 00 doctor；malformed、0、负数或更大值均为 runtime not ready，不声称已实现跨进程 action serialization。

## Non-Goals

- 不建立完整 phase topology、HITL、rerun 或 fake research nodes。
- 不定义 ResearchState、gate、WorkSpec、submission ledger 业务 schema。
- 不调用真实 LLM、web search 或写 research artifacts。
- 不解决最终 artifact publication；16 负责 workspace-to-outputs publish。

## 风险 / 取舍

- [风险] local editable/Docker source assembly 与上游 `scripts/serve.sh`/Compose 漂移。→ launcher/override 只负责环境与命令装配，加入 upstream-command contract test，不复制上游业务逻辑。
- [风险] reflected tool 无 lifespan hook，长期 provider 复用不可控。→ 第一版用官方 per-action async context；只有 00 实证找到稳定 hook 后才升级为进程级池。
- [风险] dedicated Agent 被误当安全边界。→ 文档、SOUL 和测试都明确：权限在 RuntimeAdapter/node policy/submit/gate；Agent 只是 UX。
- [风险] `create_deerflow_agent()` 默认 feature chain 带入不合适 middleware。→ 00 固定传入已验证语义为完整接管的 `middleware=[...]`，并用 ordered inventory contract 锁住，不能回退到默认 `RuntimeFeatures`。
- [风险] fresh thread 尚无 sandbox state。→ RuntimeAdapter 走 public async lazy initializer，复用父 sandbox；初始化失败才 fail closed。
- [风险] local health check 漏掉 remote shared-filesystem writer。→ stopped-Gateway 是显式操作前置条件，health/PID 探测只负责拒绝已检测到的在线实例，CAS/atomic replace 负责剩余文件竞态。
- [风险] 同 probe 并发产生 checkpoint fork/lost update。→ 固定 lock stripes 在单 worker 内按 namespace 串行；00 对多 worker fail readiness，后续分布式协调另立 change。
- [风险] prompt-injection 发现太晚。→ 00 建 untrusted-source invariant；08/09/18 逐层加强。
- [风险] authenticated future users 无法由一次 configure 预创建 Agent。→ 第一版只支持 current-user API，不把 operator `--user-id` 当身份凭证；tool 本身不依赖 dedicated Agent 存在。

## 落地关联

00 通过后，01 只能消费已冻结的 package、launcher、RuntimeAdapter、GraphHost 和 node-agent runtime，不再夹带基础设施选型。真实 business nodes 必须沿着 00 定义的目录、import、mount、path policy 和 prompt-loading 规则逐个替换。
