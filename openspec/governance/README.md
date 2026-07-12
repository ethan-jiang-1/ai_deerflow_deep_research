# openspec/governance — 需求可追踪性 + 确定性归档门禁

> 项目级 OpenSpec 治理扩展（非 OpenSpec 原生）。借鉴自一个上游 JS 项目的**思想**，
> 技术栈换成本仓库的 **Python 标准库**（零外部依赖，永远可跑）。
>
> 定位：让"我们在 DeerFlow 之上构建的智能体"的每条需求都有永久身份、全程可追溯，
> 并用小巧的确定性脚本在归档前机器强制纪律——纪律从"自觉"变"门禁"。

## 四根支柱

1. **需求身份系统** —— 每条 capability 需求一个全局唯一、只增不删、永不复用的 ID
   `{PREFIX}-{NNN}`（如 `CUT-001`）。ID 贯穿全链路：
   `req-registry.yaml` 登记 → main spec 头 `> req:` → tasks `@impl` → 代码 `# @impl`。

2. **单一登记处** —— [`req-registry.yaml`](req-registry.yaml)：
   - `prefixes:` 块是缩写→capability 的自文档化映射。
   - ID 按 capability 分组、组按字母序、组内按数字序。
   - 废弃只在行末标 `[DEPRECATED]`，**永不删除、永不复用**。

3. **结构权威链** —— [`architecture-policy.md`](architecture-policy.md) 定义 active spec、
   [`project-structure.toml`](project-structure.toml)、`agent/AGENTS.md` 受控区块和实际仓库的
   权威分工。精确目录、import 和节点包规则只在 TOML registry 中枚举。

4. **三个确定性校验脚本**（只读、零语义判断、归档前必须 PASS）：
   - [`check_project_reqs.py`](check_project_reqs.py) —— registry 一致性 4 查：
     `duplicate` / `unregistered` / `orphan` / `reusedRetired`。
   - [`check_project_specs.py`](check_project_specs.py) —— main spec 结构 4 查：
     `deltaHeaderInMain` / `missingPurpose` / `missingRequirements` / `missingReqHeader`。
   - [`check_project_architecture.py`](check_project_architecture.py) —— 结构治理检查：
     manifest schema/path、spec 生命周期引用、`agent/AGENTS.md` 受控区块和实际目录一致性。

## 怎么用

```bash
# 在 repo 根运行（默认扫当前目录；也可传 projectRoot 参数）
python3 openspec/governance/check_project_reqs.py
python3 openspec/governance/check_project_specs.py
python3 openspec/governance/check_project_architecture.py
```

三者退出码 `0` = PASS，`1` = 有违规（stderr 列出）。`config.yaml` 的 `rules.tasks`
把归档前门禁固化为每个 change 的硬性收尾 task。

## ID / spec 约定速查

| 约定 | 规则 |
|------|------|
| 缩写 | 首词前 2 字母 + 次词首字母（`custom-tool`→`CUT`）；单词型取前 3（`skills`→`SKI`） |
| 声明归属 | main spec 首个 `##` 之前一行 `> req: XXX-001, XXX-002` |
| 结构引用 | owning spec 首个 `##` 之前一行 `> structure: openspec/governance/project-structure.toml` |
| 引用 | tasks `@impl XXX-001`、代码注释 `# @impl XXX-001`、模块 docstring |
| 需求标题 | 稳定语义锚点，**不得**写进 ID（`### Requirement: Foo` ✅ / `... (CUT-001)` ❌） |
| delta 头 | `## ADDED/MODIFIED/REMOVED/RENAMED Requirements` 只在 `openspec/changes/` 合法 |
| 三态 | alive（main spec）/ pending（活跃 change delta）/ retired（`[DEPRECATED]`） |

## 与上游 JS 版的差异（有意为之）

- **技术栈**：Python 标准库，不用 Node/`.mjs`、不用 Zod、不解析 YAML 库——registry 的
  ID 行用正则直接扫描，依赖为零。
- **空起步**：`check_project_specs.py` 在 `openspec/specs/` 尚无 spec 时返回 `0`（"没有
  spec 就没有可违反的结构"），而非报错；有了 spec 后行为与上游一致。
- **不搬**上游项目专有的 version-bump / Zod / 框架目录等约定——只搬治理**思想内核**。
