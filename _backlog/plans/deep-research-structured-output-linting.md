# Plan: Deep Research Structured-Output Linting (Agent YAML/JSON)

> 类型: 治理/流程 | 更新: 2026-07-16
> 对应 OpenSpec change: 待立(Phase 1:`add-deep-research-structured-file-lint-gate`;Phase 2 随 change 04 已解锁)
> 依赖: Phase 1 无;Phase 2 依赖 change 04(work-unit kernel 落地 WorkSpec/SubmissionRecord/ledger schema ✅ 已归档)
> 动因: 想给"agent 输出的 YAML/JSON"加 linter——main-agent 侧成熟可做,sub-agent 侧还没东西可 lint
> 状态: 提案(draft for discussion)——Phase 2 触发条件已满足（04 已落地），sub-agent 侧现在有 wave0/wave1 result、critic verdict、synthesis findings、gap result 等结构化 JSON 可 lint

## Context / 你问的问题

你的原话大意:**如果 agent 输出 YAML 或 JSON,必须 lint。main-agent 上有 yaml 包应该没问题;但 sub-agent 经常输出点东西、那边没有严格的 node 定义,怎么做?要琢磨;可能不用太早做,做完两三四个阶段再说;先看 plans 里没实施的,心里有数今后会是什么样。**

认真分析完三个 surface 后,结论不是"做不做",而是**分三层、分两期**:

| Surface | 现状 | 能不能 lint | 时机 |
|---|---|---|---|
| **main-agent / 配置层**(config.yaml、extensions_config.json、project-structure.toml、req-registry.yaml、spec.md、AGENTS.md 生成块) | 已有大量验证(pydantic 载入、governance checker、字节级 drift) | **能,且便宜** | **现在做(Phase 1)** |
| **sub-agent / phase-agent 输出** | 今天**零**结构化输出;纯 ReAct,输出是 freeform `summary` 字符串;`structured_output_type`/`Result` 契约/真实 node factory 全是惰性占位 | **不能**——没有 schema 可挂 | **延后到 change 04+(Phase 2)** |
| **未来 feature 输出**(03/04/master) | 全是 JSON/JSONL,**无任何新 YAML/TOML**;schema 基本到 04 才定义(只有 SubmissionRecord 有字段表) | 04 后才有料 | **随 04 落地** |

**边界问题的答案(一句话)**:linter 挂在 **schema(pydantic 模型)**上,不是挂在 freeform 文本上。main-agent 侧 schema 已存在(AppConfig 等)→ 现在就 lint;sub-agent 侧 schema(per-node `Result` 契约 / `structured_output_type` 策略槽)目前是惰性的、没人读 → 在它们被接通(04+ 真实 node 落地)之前无法 lint。所以"sub-agent 那头怎么做"的答案是:**等 schema 出现,再把 linter 挂上去;现在挂会挂在空气上。** 这正好对应你说的"做得太早不一定好,因为还不知道正儿八经长啥样"。

## 诊断:三层各自的现状与缺口(有证据)

### A. main-agent / 配置层(已验证,但有便宜可捡)
**已验证(强)**:
- `config.yaml` → `AppConfig` pydantic(`backend/packages/harness/deerflow/config/app_config.py:182`,~30 子模型)。
- `extensions_config.json` → `ExtensionsConfig` pydantic。
- `project-structure.toml` → `check_project_architecture.py` 手写 schema + AST import 边界。
- `req-registry.yaml` → `check_project_reqs.py`(4 不变式)。
- `spec.md` → `check_project_specs.py`(4 结构不变式)。
- `agent/AGENTS.md` 生成块 → `_validate_guide` 字节级 drift。
- `agent/scripts/configure.py` 是**唯一**完整的写器:ruamel.yaml round-trip + ownership 冲突检测 + sha256 rollback manifest + atomic replace + flock + online-detector。

**缺口(便宜、现在可补)**:
1. **pydantic `extra="allow"` 满天飞**(`app_config.py:182`、`extensions_config.py:33,52,91`)→ 字段拼错(如 `modles:`、`enabled:` 放错层级)**被静默接受**。这是 main-agent 侧最大的"lint 缺失"。修法:给关键模型加严格键校验(strict-keys lint),或针对性切 `extra="forbid"`。
2. **示例/模板被 copy 不被 parse**:`config.example.yaml`(`scripts/configure.py:20` `shutil.copyfile`)、`extensions_config.example.json` 从不被解析 → 模板里的语法错会静默流进每个新 `config.yaml`。
3. **`openspec/config.yaml`(23.7KB)和 `.openspec.yaml` 本地从不 parse**——只有外部 openspec CLI 读。
4. **`req-registry.yaml` 用正则扫,不是 YAML parse**(`check_project_reqs.py:32`,刻意"零依赖")→ ID 行之外的结构错(prefixes 块、`[DEPRECATED]` 错行)看不见。
5. **CI 不跑 governance checker**:`.github/workflows/lint-check.yml` 只跑 ruff + frontend;三个 `check_project_*.py` 只在 archive 时人手跑 → drift 在 PR 上抓不到。
6. **`scripts/config-upgrade.sh` 用 `yaml.dump` 破坏性重写**(丢注释、无 rollback),与 `agent/scripts/configure.py` 的完整机器差一大截。
7. `mcpInterceptors` 在 example 里但不在 schema 里(靠 `model_extra` 读,坏条目只 warn+skip)。

### B. sub-agent / phase-agent 输出(今天无可 lint 之物)
- phase agent 是纯 ReAct(`agents/factory.py:25-43` 全托管 `create_deerflow_agent`,**无** `response_format`/`with_structured_output`)。
- agent 输出 = 最后一条 AIMessage 的文本,在 `runtime/node_agent_bridge.py:152-158 _project_result` 里**直接当 `summary` 字符串**,从不序列化成 YAML/JSON 文件(grep `yaml.dump|json.dump|.write(` 在 agents/ + bridge = 0 命中)。
- 严格 pydantic **只**存在于 wire/checkpoint 信封(`DeepResearchControlResult`、`HumanInputRequest`、`NodeExecutionResult`、`ResearchCheckpoint`)和 domain context;**上游**(agent 文本、per-node `Result` 契约、`structured_output_type`)全是 freeform / 未接通。
- 惰性占位(设计**预留**了但没接):`NodeFinishReason.INVALID_OUTPUT`、`FailureCode.INVALID_OUTPUT_SCHEMA`(标 "repairable")、`ExecutionPolicy.structured_output_type: type | None`(grep 确认**从未被读**)。每个 `graph/nodes/*/contracts.py` 的 `Result` 模型被打包进 `NodeSpec.contracts` 但**graph builder 从不拿它校验 node 输出**。所有真实 node factory 是 `UNAVAILABLE_REAL_FACTORY`。

→ **结论**:sub-agent 侧现在没有任何 schema-bearing 产物可挂 linter。

### C. 未来 feature 输出(03/04/master)
- **零新 YAML/TOML**(只有已有的 `openspec/config.yaml`)。
- 真料是 JSON/JSONL,但 schema 基本到 **change 04** 才定义:
  - **唯一有字段表**的:`SubmissionRecord` / `evidence/submissions.jsonl`(master 391-401,10 字段组;存储格式 JSONL-vs-SQL 仍是 04 要定的 open decision,master 902)。
  - 有枚举/字段名但无 pydantic 草图:`GateResult/gate_feedback`、HITL2 decision、HITL 中断载荷、ResearchState 字段组、reducer 不变式。
  - 只有名字、无字段:`WorkSpec`、`Attempt`、`CandidateResult`、`GateDefinition/GateRule`、"stable failure code"。
  - 纯 prose/无结构:`brief.json`、`profile.json`、`claims.jsonl`、`findings.json`、`gaps.json`、`synthesis.md`、`report.md`、`claim-citation-map.json`、`gate-attempts.jsonl`。

## 建议:分两期

### Phase 1 —— 现在做:main-agent / 配置层 structured-file lint gate(便宜、高价值)
目标:把上面 A 的缺口补上,**复用既有原语**,不引入重机器。

1. **严格键 lint**:给 `AppConfig`/`ExtensionsConfig`/`McpServerConfig`/`McpOAuthConfig` 加一个 lint pass(或针对性切 `extra="forbid"` + 白名单已知 `mcpInterceptors`),让字段拼错在配置加载/lint 时报红。复用 pydantic。
2. **示例/模板 parse 校验**:`config.example.yaml`、`extensions_config.example.json`、`openspec/config.yaml`、`.openspec.yaml` 用真实 YAML/JSON parse 做语法 lint(ruamel.yaml 已在 `agent/scripts/configure.py` 用;JSON 用 stdlib)。一个 governance 脚本 `check_project_structured_files.py` 扫这些文件,parse 失败即红。
3. **`req-registry.yaml` 升级为真 YAML parse**(可选,保留零依赖则维持正则——权衡:正则快但漏结构错;ruamel 已是 operations extra)。建议:在 governance 脚本里用 ruamel 做一次结构校验,保留现有正则 ID 扫描不变。
4. **governance checker 进 CI**:把 `check_project_reqs/specs/architecture.py`(+ 新 structured-file checker)加进 `.github/workflows`,PR 上就跑,而不是只在 archive 手跑。(与 spec-gates-and-coverage plan 的 `make gates` runner 自然合流。)
5. **`config-upgrade.sh` 改用 ruamel round-trip**(对齐 `agent/scripts/configure.py`),不再破坏性 `yaml.dump`。

**验收**:Phase 1 落地后,(a) 故意在 `config.yaml` 写拼错字段 → lint 红;(b) 故意把 `config.example.yaml` 写成非法 YAML → 红;(c) CI 在 PR 上跑 governance checker;(d) `req-registry.yaml` 结构错被 catch。

### Phase 2 —— 延后到 change 04+:sub-agent / feature-output JSON/JSONL linting
触发条件:**change 04 落地** `WorkSpec`/`Attempt`/`CandidateResult`/`SubmissionRecord` 的 pydantic schema + ledger 存储格式定型。在那之前,sub-agent 侧无 schema 可挂。

落地形态(届时):
- linter 挂在 **schema** 上,不是 freeform 文本:
  - **submit node 权威边界**:只有 submit node 写 `submissions.jsonl`/`claims.jsonl`;只有 gate node 写 `gate-attempts.jsonl` + `gate_feedback`。lint = `SubmissionRecord.model_validate(row)` + 权威写入检查(配合 topology/gate 检查)。
  - **`_project_result` chokepoint**(`runtime/node_agent_bridge.py:152`):届时扩展它真正 parse agent 输出(现在只赋 raw string),用 `ExecutionPolicy.structured_output_type`(目前惰性)做 `with_structured_output`;parse/校验失败 → `NodeFinishReason.INVALID_OUTPUT` / `FailureCode.INVALID_OUTPUT_SCHEMA`(均已预留、标 repairable)。
  - **per-node `Result` 契约**:graph builder 调 `spec.contracts.result_type.model_validate(node_return)`(现在不调)。
- 校验内容:JSONL append-only / hash-chain;`work-spec.json` 内容 hash 与提交时一致;`result.json` 带 result schema version;`claim-citation-map.json` 与 `report.md` + accepted ledger 双向闭合;claim ID 全 run 唯一。
- **不做**:Markdown-with-structure(`report.md`、`synthesis.md`、`decision-brief.md`)——归 integrity gate(master 547-551)管,不归 JSON linter。

**为什么是 04 不是现在**:schema 在 04 才定义(plan-04 line 21 命名了 WorkSpec/Attempt/CandidateResult;master 902 说 ledger 存储格式是 04 才定的 open decision)。现在挂 = 挂在惰性占位上,且会跟 04 的 schema 设计互相打架(你担心的"做得太早不知道正儿八经长啥样")。

### Out of scope
- **YAML/TOML feature linting**:03/04/master 引入**零**新 YAML/TOML,无需覆盖。
- **Markdown-with-structure**:归 quality gate,不归本 linter。
- **覆盖率%/行覆盖**:不做,只做"schema 存在性 + 结构合法"。
- **改 openspec CLI**:`openspec archive` 的 scenario-drop 等规则是它的(见 spec-gates-and-coverage plan 的 GATES.md 文档化)。

## 复用既有原语(不造新轮子)
- **ruamel.yaml**(`agent/pyproject.toml` operations extra;`agent/scripts/configure.py:34` 用 `YAML(typ="rt")` round-trip)——唯一能保注释的 YAML 库;Phase 1 的 YAML parse + Phase 2 的 ledger(若选 YAML,但更可能 JSON)。
- **pydantic v2**(~60 处;`AppConfig`/`ExtensionsConfig`/`NodeExecutionResult`/`ResearchCheckpoint`/将来的 `SubmissionRecord` 等)——lint 的 schema 载体。
- **`agent/scripts/configure.py` 的完整写器机器**(ownership 检测、sha256 rollback manifest、atomic replace、flock、online-detector)——Phase 1 升级 `config-upgrade.sh` / Phase 2 任何配置写动作的对齐标杆。
- **governance checker 框架**(`openspec/governance/check_project_*.py`)——Phase 1 新 `check_project_structured_files.py` 沿用同款风格(零外部依赖、清晰退出码)。

## 与其他 plan 的关系
- 与 `deep-research-spec-gates-and-coverage.md`(前一个 plan)互补:Phase 1 的 structured-file lint + governance-checker 进 CI,自然成为那个 plan 的 `GATES.md` 目录 + `make gates` runner 里的一条门禁。两个 plan 可合并成一个 change 落地,也可分。
- Phase 2 随 change 04 走。

## 风险 / 权衡
- **`extra="allow"` → 严格化可能炸出既有拼错配置**:缓解——先以 lint-only(报告不阻断)跑一遍基线,修掉存量,再切 `forbid`。
- **Phase 1 过度扩张**:缓解——只覆盖"agent/系统写的结构化文件",不碰 `.github/`、`docker-compose*` 那种外部工具消费的(它们各有自己的 validator)。
- **Phase 2 挂在 `structured_output_type` 上可能与 04 的真实 schema 设计冲突**:缓解——明确 Phase 2 是 04 之后的事,让 04 先定 schema,本 plan 只描述挂点不预定字段。
- **sub-agent 真的可能靠"集成测试"覆盖而非 linter**:缓解——Phase 2 的 `Result` 契约 + `INVALID_OUTPUT_SCHEMA` 失败码本身就是"结构化 lint"的运行时形态,不一定是独立 lint 工具。

## 待你拍板
1. **Phase 1 严格键策略**:针对性切 `extra="forbid"` + 白名单(强)vs 新增 strict-keys lint pass(不改模型,弱)。推荐前者分批做。
2. **`req-registry.yaml`**:维持正则(零依赖)vs 升级 ruamel 结构校验。推荐升级(operations extra 已有 ruamel)。
3. **Phase 1 是否独立成 change**,还是并入 `spec-gates-and-coverage` 那个 change 一起做。推荐并入(都是 governance 加固,一次 apply)。
4. **Phase 2 的触发点**:严格等 change 04 merge,还是 04 propose 阶段(schema 初稿出来)就介入。推荐等 04 merge,避免和 04 schema 设计互相干扰。
