# Plan: Deep Research Spec Gates And Requirement-Test Coverage

> 类型: 治理/流程 | 更新: 2026-07-16
> 对应 OpenSpec change: 待立(建议 `add-deep-research-spec-gate-catalog`,独立于 03/04)
> 依赖: 无(可先于 03/04 落地,且能让 03/04 的 apply 更稳)
> 动因: change 02 apply/archive 期间暴露——MD(proposal/spec)只描述意图,真正的裁判是 CLI 门禁 + 测试,二者没对齐,导致"瞎猜才能过"
> 状态: 提案(draft for discussion)——08–13 已落地，spec 数量从 ~10 增长到 17，门禁集合缩水的风险更高

## Context / 为什么做

change 02 走完一遍 apply→archive,踩到一连串"MD 没说、但 CLI 会卡"的点:

- `openspec archive` 的 sync 检查拒绝了我"把 REG-005 的 scenario 挪到 REG-011"(MODIFIED 不能丢 scenario)——这条规则只存在于 CLI,MD 里看不到。
- `check_project_architecture.py` 报 `guide.drift`、`required_paths missing`——manifest 与 AGENTS.md 的 generated block 必须逐字节一致,也是 MD 之外的隐含规则。
- `make test` 才暴露 `generation` 缺默认值、`project_lifecycle_status` 把 dataclass 当 dict 用——行为是否保留,只有跑测试才知道,MD 说了不算。
- 末组门禁在 change 00/01/02 之间**从 6 条缩到 3 条**(02 漏了 architecture checker、漏了 make test/lint/durability、漏了 `@impl` 核对),没有任何机制阻止下一个 change 继续缩水。
- `openspec/config.yaml rules.tasks` 的 done-conditions **只硬编码了 2 条门禁**(`check_project_reqs.py`、`check_project_specs.py`)。

审计确认的 10 个缺口(证据见探索报告),最关键两条:

1. **`@impl REG-xxx` 没有任何机器校验**——三个 checker 的源码里 `@impl` 这个 token 出现 0 次;一个需求可以零 `@impl`、或引用不存在的 ID,所有门禁照样过。
2. **没有需求→测试可追溯**——没有任何文件把 REG-xxx 映射到测试;没有 checker 断言"每个需求至少有一个测试管它"。目前 ~45 个 src 文件带 `@impl`,只有 **2 个**测试文件带。

结论:**门禁(CLI)和测试才是 spec 的真正执行层;MD 只是意图 + 指针。** 现在执行层是碎片化、隐含、会漂移的,所以实现者只能瞎猜。

## 目标(对应你的两个疑问)

1. **CLI/MD 配合、消灭瞎猜** → 一个权威「门禁目录 GATE CATALOG」+ 一键跑全部门禁的 runner。MD 描述意图;门禁目录告诉实现者"改什么、看什么、跑哪条命令才能过"。
2. **测试资产做强制、别忘了测** → requirement→test 可追溯 + 一个 coverage checker,机械地保证每个 alive 需求都有测试背书。

## Scope(建议落地物,下一个 change 实现)

### 1. 门禁目录 `openspec/governance/GATES.md`
逐条枚举门禁,字段统一:`name / 检查什么(精确规则) / 命令 / 改什么能过(速查) / 防止的失败类`。覆盖:

- **治理脚本**:`check_project_reqs.py`(ID 一致性: duplicate/unregistered/orphan/reusedRetired)、`check_project_specs.py`(main spec 结构: deltaHeaderInMain/missingPurpose/missingRequirements/missingReqHeader)、`check_project_architecture.py`(manifest + guide drift + import 边界 + required_paths + 单一 source root)。
- **Spec 工具**:`openspec validate --strict`(每个 ADDED/MODIFIED 需求 ≥1 scenario、`> req:` header)、`openspec archive`(MODIFIED 不能丢 scenario、ADDED 不能重名、REMOVED 要 Reason/Migration + 迁移)。
- **Agent**:`make lock-check`、`make format`/`make lint`(ruff)、`make test`、`make test-durability`(file-SQLite restart)、`make test-blocking-io`、`make test-contract`(含 architecture 契约测试)。
- **边界**:`backend/`/`frontend/` diff 为空。

每条配"失败→怎么修"速查(例:`guide.drift` → 重新生成 AGENTS.md 的 generated block;`scenario drop` → 保留场景或用 REMOVED+Reason;`orphan` → 补 main spec `> req:` 行或 registry;`import 边界` → 看违规 import 链)。

### 2. 一键门禁 runner `make gates`(agent/Makefile) + `openspec/governance/run_gates.sh`
按 GATES.md 顺序跑全部门禁,任一失败即非零退出。把"跑门禁"从记 10 条命令变成 1 条,且**集合稳定**——不能再被单个 change 的 tasks.md 偷偷缩水。新增的 coverage checker(#3)自动纳入。

### 3. 需求→测试 coverage checker `openspec/governance/check_project_req_coverage.py`
- 复用现有 `@impl REG-xxx` 约定,但**推到测试侧**:要求每个 alive 需求(registry + main spec `> req:`)在 `agent/tests/` 里至少有 1 个 `@impl` 标注(标在 unit 或 integration 测试文件 docstring 均可)。
- checker 扫描 `agent/tests/**/*.py` 的 `@impl`,断言每个 alive 需求有测试背书,报告 uncovered 列表。
- 同时校验 src/tests 里所有 `@impl` 引用的 ID 都已在 registry 注册(防幻影 ID / 拼错)。
- 备选(更重、留作后续):`req-coverage.yaml` 显式登记 REG→test 文件。先做 @impl-in-test 扫描——零额外登记、复用既有约定。

### 4. 收口 config.yaml + tasks.md 模板
- `openspec/config.yaml rules.tasks` 的 done-conditions:从硬编码 2 条 → 引用 `make gates`(或显式列全部门禁,含 architecture checker + 新 coverage checker)。
- tasks.md 末组:不再各 change 自己列(bespoke 3→6 条),改成一行"运行 `make gates`,全绿"。门禁集合的 single source of truth 是 GATES.md,堵住 gap 9(门禁缩水)。

## 状态不变量

- 门禁集合**唯一且稳定**:GATES.md 是真相,`make gates` 是它的可执行镜像;tasks.md 末组只引用,不重写。
- 每个 alive 需求都有**机械可验**的测试背书(@impl-in-test),否则 coverage checker 红。
- MD 角色收敛为:意图 + scenario + `@impl`/测试指针;执行裁判权在门禁 + 测试。

## 验收

- `make gates` 一条命令跑完全部门禁并全绿(含新 coverage checker)。
- 故意删某测试文件的 `@impl` → coverage checker 报该需求 uncovered(红)。
- 故意改 `backend/` → 边界门禁红。
- **change 02 回填首例**:给 REG-006..011 的测试(`test_state_*.py`、`test_bundle.py`)补上 `@impl`,coverage checker 由红转绿——作为该 checker 的首个端到端验证。
- 新 change(03)的 tasks.md 末组只需"运行 `make gates`",且无法再悄悄缩水门禁集合。

## Non-Goals

- 不改 openspec CLI 本身(`@fission-ai/openspec` 的 scenario-drop 等规则是它的;我们只在 GATES.md 里文档化 + 给"怎么过"速查)。
- 不引入新测试框架;复用 pytest + 现有 fixtures。
- 不做覆盖率%(行/分支覆盖);只做"需求→测试"的**存在性**背书(每个需求至少有一个测试管它)。
- **本轮不实现机制**——本轮只产出本 plan MD 供讨论。GATES.md / runner / checker / config 收口是下一个 change 的事。

## 落地关联

- 独立于 03/04,可先做(它让 03/04 的 apply 更稳、更可重复)。
- 落地后,03(gate kernel)/04(work unit)新增的 REG-012+ 会被 coverage checker 强制要求有测试,从源头杜绝"MD 写了契约但没人测"。
- change 02 的 REG-006..011 顺带补 `@impl`-in-test,作为 coverage checker 的首例验证。

## 风险 / 权衡

- **@impl-in-test 可能漏掉"靠集成测试覆盖"的需求** → 缓解:允许标在 `tests/integration/*` 与 `tests/graph/*`,不限于 unit。
- **coverage checker 太严会拖慢 change** → 缓解:只要求 ≥1 测试存在(非覆盖率%);uncovered 在平时 warning、仅在 archive 门禁报红。
- **门禁目录与 CLI 版本漂移** → 缓解:GATES.md 每条标注来源(CLI 版本 / 脚本路径);openspec 升级后跑一次 `make gates` 校准。
- **@impl-in-test 是约定不是强类型** → 缓解:checker 同时校验 ID 已注册,拼错/幻影 ID 会红。

## 待你拍板的开放点(写进 plan 供讨论,不阻塞)

1. coverage 机制:**@impl-in-test 扫描**(轻、复用约定) vs **`req-coverage.yaml` 登记表**(重、显式)——本 plan 推荐前者,后者留备选。
2. 门禁 runner 放哪:`agent/Makefile` 的 `make gates`(agent 侧) vs `openspec/governance/run_gates.sh`(治理侧)——推荐脚本 + Makefile 薄封装,两边都能调。
3. 边界 diff 检查是单独脚本还是塞进 architecture checker——推荐单独 `check_diff_boundary.py`(职责单一)。
