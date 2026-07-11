> req: NOA-001, NOA-002, NOA-003, NOA-004, NOA-005, NOA-006

## ADDED Requirements

### Requirement: Phase agents inherit one parent runtime
The runtime-owned node-agent bridge SHALL implement a pure domain capability protocol used by graph nodes. It SHALL resolve model/tools from TrustedRuntimeEnvelope, seed an ephemeral child state/context with the already validated parent sandbox and thread data, and invoke a bounded embedded agent produced by the full-takeover factory. The agents layer SHALL not import runtime; raw AppConfig, identity, host paths, sandbox internals, and checkpoint identity SHALL not enter graph/node contracts, checkpoints, events, or model-visible context. Each bound compiled child SHALL be created for one `run_agent` request, invoked as a separate runnable with `checkpointer=None`, and discarded after completion/cancellation; it SHALL never be cached across actions/users/threads/attempts, mounted as a checkpoint-inheriting subgraph, or create another sandbox lifecycle, thread namespace, or persistent controller.

#### Scenario: Parent context is preserved
- **WHEN** a fake node starts an embedded agent with a parent sandbox and thread-data fixture
- **THEN** authorized tools observe those same scoped values and no independent checkpointer or thread root is created

#### Scenario: Missing parent isolation fails
- **WHEN** a node requests an agent without validated parent sandbox/thread context
- **THEN** the factory refuses construction before a model or tool is invoked

### Requirement: Phase-agent execution has explicit budgets
Every node-agent policy SHALL specify a resolved model, exact tools, maximum model calls, total tool calls, tool calls per model response, parallel tool-call limit, total token budget, per-model-call output-token cap, per-tool-result size cap, structured-result size cap, and wall-time budget. Before each text-only model call the runtime SHALL use a deterministic no-network conservative upper bound over the actual messages/tool schemas plus capped model output; non-text content SHALL require an explicit conservative modality estimator or fail admission. It SHALL then reconcile actual usage metadata. Missing usable token accounting SHALL terminate with `usage_unavailable` before tool execution or another model call. Tool results SHALL be bounded before re-entering model context. Exhausting any budget SHALL stop the agent with a typed non-success finish reason and cancel outstanding child work.

#### Scenario: Work completes within budget
- **WHEN** ReplayChatModel returns a valid structured result within all configured limits
- **THEN** the adapter returns a successful normalized result with recorded usage and finish reason

#### Scenario: Budget exhaustion stops execution
- **WHEN** a fake model exceeds the model-call, tool-call, parallelism, token, tool-result, structured-result, or wall-time limit
- **THEN** execution terminates without another tool call and reports the exhausted budget as a failure

#### Scenario: Missing usage cannot disable the token budget
- **WHEN** a model response omits usable token accounting
- **THEN** the runtime emits terminal `usage_unavailable`, strips tool calls, and does not make another model request

### Requirement: Tool and path policy fails closed
The node-agent runtime SHALL expose only explicitly allowed tools and SHALL revalidate the runtime tool name and path-bearing arguments before dispatch. Every allowed tool SHALL have a typed ToolPolicySpec declaring path fields, effects, validator, and cancellation class; unknown argument shapes and tools without an approved native async/cancellable path SHALL be denied. Reads and writes SHALL stay within policy roots; writes SHALL stay within the active attempt and SHALL never mutate graph phase, gates, ledger, sibling attempts, package source, or host paths.

#### Scenario: Allowed attempt write succeeds
- **WHEN** a fake file tool writes a canonical path within the active attempt write root
- **THEN** policy authorizes the call and records its scoped artifact reference

#### Scenario: Forged tool or path is denied
- **WHEN** a model requests an unlisted tool, traversal path, symlink escape, cross-attempt write, or gate/ledger mutation
- **THEN** middleware blocks execution, leaves the target unchanged, and returns a typed policy denial

### Requirement: External source content remains untrusted data
The runtime SHALL keep package system/policy prompts separate from external source payloads. Source text SHALL only enter model context as delimited untrusted data or an artifact reference, and its instructions SHALL never grant tool, path, phase, gate, or ledger authority.

#### Scenario: Benign source remains data
- **WHEN** ReplayChatModel receives a normal source fixture
- **THEN** the source is present only in the untrusted data channel and the agent can produce output within its existing policy

#### Scenario: Prompt-injected source cannot escalate
- **WHEN** a source fixture asks the agent to ignore rules, call a forbidden tool, or mark a gate passed
- **THEN** the system prompt remains unchanged, forbidden actions are denied, and no control or ledger state changes

### Requirement: Results, progress, failure, and cancellation are normalized
The adapter SHALL validate structured model output and project stable redacted progress events through the supported stream-writer API. Malformed output SHALL fail; outer `CancelledError` SHALL propagate after child/provider cleanup and SHALL not leave background work running.

#### Scenario: Valid result and progress are projected
- **WHEN** a fake agent emits progress and a result matching the node output schema
- **THEN** the parent receives stable progress records and one validated normalized result without raw secrets or source bodies

#### Scenario: Cancellation cannot become success
- **WHEN** the outer task is cancelled while a fake embedded agent has child work in flight
- **THEN** child work is cancelled and awaited, cleanup completes, and no successful result is emitted

### Requirement: Clarification belongs only to graph HITL nodes
The phase-agent factory SHALL omit `ask_clarification` and clarification middleware. A phase agent SHALL not create a user interrupt; only a graph-owned HITL node introduced by a later change can do so.

#### Scenario: Normal node toolset has no clarification
- **WHEN** the factory builds its full-takeover middleware and tool list
- **THEN** neither the clarification tool nor clarification middleware is present

#### Scenario: Fabricated clarification call is refused
- **WHEN** a fake model emits an `ask_clarification` tool call despite the schema
- **THEN** tool policy rejects it and no graph interrupt or user-input artifact is created
