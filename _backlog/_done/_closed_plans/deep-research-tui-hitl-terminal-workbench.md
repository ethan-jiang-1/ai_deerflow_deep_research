# Plan: Deep Research HITL In DeerFlow Terminal Workbench

> 类型: 设计 / 延期兼容性工作
> 状态: Backlog；暂不实施
> 建议 OpenSpec change: `support-deep-research-hitl-in-terminal-workbench`
> 依赖: `build-deep-research-fake-graph-skeleton`（Change 01，**已归档**）
> 与 Change 02 的关系: 不依赖、不阻塞；可按产品演示优先级单独排期

> 即时演示拆分: 小型 agent-owned Textual shell 已由
> `add-deep-research-lifecycle-demo-tui` 单独处理；本计划继续只代表未来正式
> DeerFlow Terminal Workbench/generic human-input 集成，不再承载“尽快可视化”的需求。

## 背景

Change 01 **已归档**，提供可运行的 `implementation_mode=full_fake` Deep Research lifecycle：

- `start | resume | status | cancel`；
- 两次真实 LangGraph interrupt；
- `ToolMessage.artifact.human_input` version-1 请求；
- 从真实 `HumanMessage` 读取并校验 HITL response；
- memory 同进程恢复与 file-SQLite 跨进程恢复；
- 独立的 `make -C agent demo` 终端 walkthrough。

当前 demo 是普通交互式 CLI，不是 DeerFlow Textual Terminal Workbench。标准 TUI 尚未完整支持通用 human-input artifact，因此不能把现有 CLI 包装成 `demo-tui` 就宣称真实集成完成。

## 已确认的现状缺口

### TUI stream translation 丢失 human-input artifact

`backend/packages/harness/deerflow/tui/runtime.py` 在翻译 tool message 时只保留：

- `tool_call_id`；
- text content；
- error 状态；
- tool name。

它没有把 `ToolMessage.artifact.human_input` 投影到 TUI action/view state，导致 request id、mode、title、context 和 options 全部丢失。

### TUI view state 没有 pending HITL authority

现有 `ToolResult` 只表示普通工具结果。TUI 没有：

- pending human-input request；
- text/choice 模式；
- request id/source；
- option 列表；
- HITL composer/modal 状态；
- response 已提交/等待恢复状态。

### Embedded client 只能从字符串构造普通 HumanMessage

`backend/packages/harness/deerflow/client.py -> DeerFlowClient.stream()` 当前接受 `message: str`，并固定构造：

```python
HumanMessage(content=message)
```

因此 TUI 无法提交带以下 metadata 的结构化响应：

```text
additional_kwargs.human_input_response = {
  version,
  kind,
  source,
  request_id,
  response_kind,
  option_id?,
  value
}
```

Change 01 runtime 可以接受无 metadata 的 plain visible response，但正式 TUI 集成应保留结构化 request correlation，避免 stale/cross-request response 被误用，也不能依赖模型从 fallback JSON 猜测恢复参数。

## 目标

让 DeerFlow Terminal Workbench 成为通用 `artifact.human_input` 客户端，并用 Change 01 full-fake lifecycle 证明完整链路：

```text
TUI user request
  -> lead calls deep_research(start)
  -> TUI renders HITL1 request
  -> user submits correlated response
  -> lead calls deep_research(resume)
  -> TUI renders HITL2 choices
  -> user selects decision
  -> lead resumes to terminal fixture
```

该能力应是通用 human-input contract 支持，而不是把 Deep Research phase/topology 硬编码进 TUI。

## 建议 Scope

### 1. Embedded client message input contract

- 保持 `DeerFlowClient.stream(message: str, ...)` 完全向后兼容。
- 增加接受受控 `HumanMessage` 或显式 message-input contract 的入口。
- 禁止调用方通过该扩展伪造 trusted runtime identity/context。
- 确保 structured response 的 `additional_kwargs` 进入同一 thread 的真实 graph state。
- 同步 `chat()`/headless CLI 行为，避免不同入口出现不同消息语义。

### 2. Stream event artifact preservation

- tool-message serialization 保留 bounded、JSON-safe `artifact`。
- TUI translator 只识别 version-1 `artifact.human_input`。
- 未知 artifact/version 仍按普通 ToolResult 展示，不崩溃、不猜测。
- 不把整个 checkpoint、runtime context 或 authority 数据暴露给 UI。

### 3. TUI view-state contract

- 新增纯 view-state action，例如 `HumanInputRequested` / `HumanInputSubmitted`。
- pending request 至少包含：`source`、`request_id`、`mode`、`title`、`context`、bounded options。
- pending request 以最新合法 ToolMessage 为 authority；普通 tool result 不进入 HITL 模式。
- thread 切换、run interrupt、重复 stream event、未知版本有确定性 reducer 行为。

### 4. Textual interaction

- text mode：聚焦 composer 或专用 modal，提交非空 bounded text。
- choice mode：显示可导航 option list，并提交原始 option id/value。
- 清晰显示当前处于 human-input waiting，而不是普通 run completed。
- 提交期间禁用重复提交；失败后允许安全重试。
- Esc/Ctrl+C 的现有 run interruption 行为不被错误映射为 HITL `cancel`。
- `cancel` 必须仍由显式 lifecycle control action触发。

### 5. Structured response submission

- TUI 从 pending request 构造 version-1 `HumanMessage` response。
- `source` 和 `request_id` 必须来自当前 view-state request，不接受用户手输。
- choice response 的 `option_id == value`，且必须属于 advertised options。
- response 进入同一 DeerFlow thread；不得创建隐式新 thread。
- consumed response 的 UI retry 不得重复推进 nested graph。

### 6. Demo and operational entry

- 增加 `make -C agent demo-tui` 或等价 project-owned入口。
- demo 不要求真实 LLM、网络或 Gateway；使用 deterministic test model/session 驱动 lead tool calls。
- demo 必须复用正式 TUI artifact/response pipeline，而不是另写 Deep Research 专用伪 UI。
- 保留现有 `make -C agent demo` 作为更低层、无 Textual 依赖的 lifecycle smoke test。
- 标注 `implementation_mode=full_fake`，终态不得呈现为研究发现或报告。

## 测试计划

### Pure contracts

- tool artifact -> TUI action translation；
- unknown/malformed/oversized human-input artifact；
- text/choice request reducer；
- duplicate event and thread switch；
- option validation and response construction；
- ordinary ToolResult behavior unchanged。

### Embedded client

- legacy string input remains identical；
- structured HumanMessage round-trip preserves metadata；
- metadata cannot override user/thread/runtime authority；
- same-thread checkpoint receives the exact response message；
- headless and TUI paths share the same message contract。

### Textual pilot tests

- HITL1 text modal/composer interaction；
- HITL2 keyboard option selection；
- submit disables duplicate action；
- retry after delivery failure；
- switching away from and back to a waiting thread；
- malformed request degrades to ordinary tool output；
- Esc/Ctrl+C semantics remain correct。

### Zero-API E2E

- start -> HITL1 -> HITL2 proceed -> full-fake terminal；
- HITL2 stop；
- lifecycle cancel；
- stale request rejection；
- consumed response reprojection；
- memory same-process continuation；
- no model/network/sandbox research call。

## 验收标准

- `deerflow --tui` 能展示通用 human-input text/choice UI。
- TUI 提交的 response 是带正确 source/request id 的真实 `HumanMessage`。
- Change 01 public lifecycle 在 TUI 中可完整跑通两次 HITL 和终态。
- 未知 artifact/version fail closed 或降级为普通 ToolResult，不静默猜测。
- 普通聊天、普通工具、thread persistence、run interruption 和 headless CLI 无回归。
- `make -C agent demo-tui` 是零 API、确定性、可自动测试的真实 TUI integration demo。
- 所有演示清晰标注 `implementation_mode=full_fake`，不输出或暗示真实研究报告。

## Non-Goals

- 不在该 change 中实现任何真实 research node、搜索、证据或报告。
- 不修改 Deep Research topology、fixture routes 或 checkpoint schema。
- 不把 TUI 变成 Deep Research 专用客户端；能力应服务所有 versioned human-input artifacts。
- 不在 TUI 中复制 RuntimeAdapter authority 或 nested graph routing。
- 不顺带处理 IM channel human-input compatibility。
- 不引入 Gateway/Web UI 改动，除非实施时证明 embedded client 无法提供必要的正式消息合同；此时应先升级 proposal，而不是扩大实现范围。

## 风险与决策

### 为什么不继续塞进 Change 01

- Change 01 **已归档**。
- Change 01 明确禁止修改 `backend/` / `frontend/`。
- 正式实现跨越 embedded client、stream serialization、TUI state、Textual UI 和 agent integration，属于独立兼容边界。
- 单独 change 能清楚验证普通 TUI 行为没有回归，也不会让 graph skeleton 的验收范围失焦。

### 为什么不只做一个 agent-owned Textual 假壳

单独写一个 Deep Research 专用 Textual app 可以快速展示，但不会验证 DeerFlow Terminal Workbench、`DeerFlowClient`、ToolMessage artifact 和真实 response correlation。它会形成第二套 UI/消息合同，后续仍需重做，因此不建议作为正式路线。

### 排期建议

该 change 技术上只依赖已归档的 Change 01，不依赖 Change 02。若近期需要产品演示，可独立排期；若当前优先冻结 ResearchState（Change 02），则保持在 backlog。
