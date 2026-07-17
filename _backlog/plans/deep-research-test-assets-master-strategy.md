# Plan: Deep Research 测试资产总控 Strategy

> 类型: 设计 / 总控 | 更新: 2026-07-17
> 范围: `agent/` 的代码正确性、Agent workflow、行为评估与 full-real 验收
> 输入: `test-assets-postmortem-real-mode-integration.md`、
> `test-assets-bug-to-test-mapping.md`、`test-assets-demo-design-coverage.md`、
> `test-assets-layered-strategy.md`
> 状态: 总控计划；通过一个 OpenSpec change 内的三个顺序 batch 落地

## 背景 / 问题

`add-deep-research-demo-full-pipeline` 在 fake 测试、lint 和设计审查均通过后，
首次 full-real 运行仍连续暴露 import、context 转发、模型与工具配置、sandbox、
filesystem、worker capability、policy、budget、structured output、gate 和 checkpoint
隔离等问题。13 个问题只能靠约 10 次昂贵的端到端运行逐层剥离。

四份输入材料已经分别记录事故、bug 回归、demo 决策覆盖和初版分层策略，
但仍存在三个缺口：

1. 它们以一次事故为中心，没有形成新节点和新 workflow 可重复使用的资产规则。
2. 它们把 unit、integration、smoke、E2E 当成主要分类，却没有单独定义
   Agent workflow conformance 和非确定性行为评估。
3. 文档中的测试数量、bug 数量和仓库现状已经漂移；当前 `agent/` 可收集
   1134 个测试，但仍没有独立 agent PR CI、实际 `requires_llm` suite 或
   nightly/release 门禁。

本计划的目标不是简单增加测试数量，而是让每一类风险在最早、最小、最可诊断的
测试层被发现。Full-real E2E 保留为系统验收，不再承担日常低层 bug 定位。

## 统一术语

### Code Correctness Test

传统软件测试层，验证确定性代码行为：

- **Module test**：通过 domain、engine 或其他深 module 的稳定 interface 验证纯逻辑，
  不测试私有函数和内部调用次数。
- **Integration test**：跨 runtime、context、checkpoint、sandbox、filesystem、store
  等真实 seam，验证相邻 module 的契约能够协作。
- 负责 import、schema、字段转发、capability 路由、权限、持久化、并发、取消和恢复。

### Agent Workflow Conformance Test

AI Agent 特有的确定性测试层。它验证的不只是两个 module 能否连接，而是一个有时间
顺序和循环的 workflow 是否遵守契约：model/tool 多轮循环、节点路由、checkpoint、
interrupt、repair、retry、cancel、exhausted、submit、gate 和 artifact 副作用。

这类测试使用真实节点、graph、middleware、policy、budget、tool authorization、
parser、validator、store 和本地 filesystem，只把真正的外部依赖替换为 scripted model
和 scripted tools。Mock 掉项目内部节点或 middleware 的测试不得宣称覆盖 workflow。

### Agent Behavioral Evaluation

使用真实模型和真实工具，验证非确定行为是否落在可接受范围。它同时包含两类结果：

- **硬不变量**：生命周期、权限、安全、artifact、引用绑定和 terminal outcome，失败即红。
- **质量指标**：citation precision、must-answer coverage、source diversity、
  contradiction recall、unsupported claims、成本和延迟，以多次运行和趋势判断。

### Full-System Acceptance E2E

从 real public entry 跑到 final delivery，证明部署配置、真实依赖和完整 pipeline 可以
协作。它只用于发布验收和发现未知失败类别。任何 E2E 新问题都必须下沉为更小的
correctness、workflow conformance 或 behavioral scenario，不能只保留 bug 单和日志。

## 真实性阶梯

不同 test double 能证明的范围必须显式区分：

```text
FakeNode
  证明 graph 拓扑和控制流
      ↓
Fake NodeExecutionCapabilities
  证明真实节点的输入、输出、状态更新和路由
      ↓
ScriptedModel + ScriptedTools
  证明真实 agent loop、middleware、policy 和 workflow conformance
      ↓
Real Model + Real Tools
  证明真实输出分布、供应商兼容性和研究质量
      ↓
Full Real Pipeline
  证明系统级可接受性
```

低一级测试通过不能替代高一级证据；高一级失败也必须尽量缩减到低一级的确定性
scenario。特别是，full-fake graph 通过只能证明拓扑，不能证明 real worker path。

## 稳定测试 Seams

测试资产优先放在以下五个 interface，避免随内部重构失效：

1. domain / engine interface：纯契约、reducer、validation、gate 和状态不变量。
2. `NodeSpec` / `NodeExecutionCapabilities`：真实节点行为和 capability 使用。
3. runtime adapter / node-agent bridge / store protocol：可信 context、sandbox、工具、
   middleware、预算和 filesystem。
4. lifecycle handlers / mixed graph：start、resume、status、cancel 和 real-prefix workflow。
5. real public entry：真实模型、工具、运行配置和 full pipeline。

测试应通过这些 interface 观察结果。只有当某个内部 parser 或 policy 本身是稳定、共享的
行为接口时，才直接为它建立 module test。

## Scenario 资产模型

Scenario 是 AI 测试的核心资产，不是某个 pytest 文件的临时输入。同一 scenario 应能被
deterministic workflow、live eval 和 release E2E 复用。每个 scenario 固定描述：

- 稳定 scenario id、风险标签、关联 requirement id 和 regression id；
- 用户目标、入口 action、初始 context/checkpoint 和 workspace 前置条件；
- scripted 模式下的模型响应、tool calls、tool results、usage 和故障注入；
- live 模式需要的模型与工具能力，不记录凭据；
- 预期 route、状态、terminal outcome、artifact、引用和安全不变量；
- 适用的质量指标、诊断字段和允许的降级结果。

首批 corpus 至少包含：

| Scenario family | 主要风险 |
|---|---|
| quick factual | 正常检索、引用和快速收敛 |
| claim verification | 支持、反驳和不确定证据 |
| insufficient evidence | 不伪造结论，诚实降级 |
| prompt injection | 外部内容不能取得控制权 |
| malformed structured output | repair、fallback 和 exhausted |
| tool unavailable / timeout | 工具失败、重试和限制记录 |
| budget exhaustion | token、model call、parallel call 和 wall time |
| partial worker success | submit、gate 和 failure fingerprint |
| resume / cancel / duplicate response | checkpoint、幂等和 terminal monotonicity |
| sandbox / filesystem failure | mount、containment、atomicity 和 restart |

## 风险应在哪一层最早失败

| 风险 | 最早责任层 | 更高层保留的证明 |
|---|---|---|
| import、类型、schema、纯 reducer | Module / contract | 不需要等待 workflow |
| context 转发、capability 路由、store、mount | Integration | mixed graph 只做回归 |
| middleware、tool policy、budget、parser、submit、gate | Workflow conformance | live 验证现实分布 |
| 模型格式波动、工具供应商行为、研究质量 | Behavioral evaluation | release 检查总体可接受性 |
| 真实配置、入口、全链 artifact 交付 | Full-system E2E | 不向下替代任何测试 |

## 三批实施路线

不能用一批测试结束。三批分别建立确定性地基、Agent workflow 资产和真实行为/发布门禁；
每批都必须有独立完成条件，按顺序落地。

### Batch 1: Correctness Foundation And Incident Closure

Owning OpenSpec change: `evaluate-harden-deep-research-graph`，Batch 1

1. 以当前测试收集结果为准，按风险、seam 和真实性阶梯审计现有资产；不照搬旧文档的
   “21 个新测试”，不以新增数量作为完成标准。
2. 将 postmortem 的 13 个问题逐项映射到真实测试 selector，删除重复建议，只补当前
   仍缺失或位于错误 seam 的回归。
3. P0 覆盖 all-real compile、non-interactive/context 转发、model/tool 配置、合法 sandbox、
   POSIX store probe、每节点 capability/policy 路由、budget admission、structured output、
   gate fatigue 和唯一 checkpoint/thread identity。
4. 建立合法 runtime envelope、本地 mounted sandbox、唯一运行身份、scripted model、
   scripted tools 和脱敏 diagnostics 等共享 test adapters。
5. 增加 `make test-fast`、`make test-integration` 和 agent 专属 PR CI。默认 `make test`
   明确排除 `requires_llm`、`postgres` 和 release E2E，且不得访问公网。
6. 增加 requirement-to-test checker：每个 alive requirement 至少有一个测试 `@impl`，
   所有引用必须存在于 registry。

完成条件：13 个已知事故都能在 full-real E2E 前由确定性测试发现；失败输出能直接指出
所属 seam、scenario 和稳定错误码。

### Batch 2: Deterministic Agent Workflow Assets

Owning OpenSpec change: `evaluate-harden-deep-research-graph`，Batch 2

1. 每个 real 节点至少有一个成功 scenario 和一个该节点最高风险的
   failure / repair / exhausted scenario。
2. 模型或工具节点必须有一条真实 `RuntimeNodeAgentBridge` → model → tool → middleware →
   structured output → submit → gate 路径；只替换模型 API 和外部工具响应。
3. 每个 real 前缀建立 mixed-graph 垂直切片：目标及其前置节点为 real，后续节点保持 fake。
4. 建立完整 replay workflow，覆盖 start、HITL、worker fan-out、repair、rerun、readiness、
   final delivery、cancel 和 restart。
5. 加入 tool timeout、malformed output、duplicate resume、partial write、stale checkpoint、
   conflicting worker result 等 fault injection。
6. 将 `tests/eval` 从只验证指标函数升级为真正驱动 workflow 的 replay corpus。

完成条件：不使用真实 LLM 和网络即可穿过全部高风险 agent workflow；full-real 失败时，
同一 scenario 能缩减到单节点或短工作流并给出可诊断结果。

### Batch 3: Live Evaluation And Release Acceptance

Owning OpenSpec change: `evaluate-harden-deep-research-graph`，Batch 3

1. 增加 `make test-live`，nightly 至少运行 start→HITL1、HITL1→topic planning 和单 topic
   Wave0 三个最短真实切片。
2. 用相同 scenario corpus 运行真实模型与工具，保存脱敏 trace、tokens、成本、wall time、
   tool calls、重试次数和质量指标。
3. correctness、安全、artifact 和生命周期不变量从第一天硬失败；主观质量指标先报告
   趋势，形成稳定基线后通过独立 change 提升为发布阈值。
4. 增加 `make test-release-e2e` 和手动/release workflow。每次 full-real run 使用唯一
   thread/run/research id，并验证清理与 checkpoint 隔离。
5. 禁止静默重试掩盖波动；每次尝试及其结果都进入报告。
6. 每个 live/E2E 新发现必须在同一修复 change 中新增最小 deterministic regression。

完成条件：nightly 能发现模型、工具供应商和真实行为分布变化；release E2E 只承担系统
验收，不再反复承担低层接口调试。

## 开发与门禁规则

每个后续 feature/change 必须：

1. 在设计或 tasks 中声明风险、scenario、被测 seam 和所需真实性级别。
2. 按一个 scenario 的 red → green 垂直推进，不先批量编写所有测试再批量实现。
3. 每个 requirement 至少有一个确定性测试；涉及 Agent 行为的 requirement 还必须有
   workflow conformance scenario。
4. 只有涉及真实模型、工具分布或供应商兼容性的需求才进入 live suite。
5. E2E 发现的问题先完成 bug→风险→seam→deterministic regression 映射，再关闭 bug。

门禁节奏固定为：

```text
PR        deterministic correctness + workflow conformance
Nightly   short live slices + behavioral evaluation
Release   full-real acceptance E2E + stable quality thresholds
```

## 与四份来源材料的关系

- `test-assets-postmortem-real-mode-integration.md`：保留原始时间线和根因证据，不再定义路线图。
- `test-assets-bug-to-test-mapping.md`：作为 Batch 1 审计输入；selector 和数量必须以当前代码
  为准重新验证。
- `test-assets-demo-design-coverage.md`：demo/public-entry 风险分别进入 Batch 1 correctness
  和 Batch 3 acceptance，不另建平行测试体系。
- `test-assets-layered-strategy.md`：其“前移风险、减少 E2E”结论保留，具体四层/四 change
  roadmap 由本计划的四类资产、真实性阶梯和三批路线取代。

四份材料不在本计划创建时立即关闭。Batch 1 将其有效发现转成可执行 inventory 后，
把已被吸收的三份设计/映射材料移入 closed plans；postmortem 可作为历史证据一并关闭。
本总控计划在 Batch 3 完成后关闭。

## Non-Goals

- 不引入 pytest 之外的第二套测试框架。
- 不以行覆盖率或测试数量衡量完成度。
- 不为测试便利扩大 production interface 或暴露内部 implementation seams。
- 不修改 `backend/` 或 `frontend/` 来扩大 Deep Research 的当前集成边界。
- 不把单次 demo 成功、单一模型表现或 full-fake graph 通过当作发布证据。

## 总体验收

- 已知事故在最低责任层有确定性回归，不需 full-real 才能复现。
- 每个 real 节点和关键 workflow 都有可复用 scenario，而不是孤立 mock 测试。
- PR、nightly、release 三种门禁各自有明确职责、命令和失败语义。
- Live eval 的硬不变量与质量评分分离，失败可回放、可缩减、可诊断。
- 新 E2E bug 会持续增加低层资产，测试体系不会再次依赖“尾巴上提 bug”。

## 落地关联

本 plan 只定义总控策略和三批顺序，不直接充当 implementation change。实际落地由一个
OpenSpec change `evaluate-harden-deep-research-graph` 统一拥有。OpenSpec 没有原生父子
change 机制；另建空 umbrella 或三个平行 change 都会造成 spec ownership 重复。

该 change 的 tasks 必须保留 Batch 1 → Batch 2 → Batch 3 的顺序和各自完成条件。每个
batch 都是可单独验证的里程碑，但 change 只有在三批全部完成、live/release 门禁已形成
明确可执行策略后才可 archive。不得把三个 batch 改写为一组无法分段验收的混合任务。
