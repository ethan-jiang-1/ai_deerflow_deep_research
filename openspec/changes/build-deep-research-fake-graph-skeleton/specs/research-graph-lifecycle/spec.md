> req: REG-001, REG-002, REG-003, REG-004, REG-005

## ADDED Requirements

### Requirement: One explicit topology and implementation map own every phase

The downstream package SHALL declare one normalized top-level Deep Research topology
containing `bootstrap`, `hitl1`, `topic_planning`, `wave0`, `wave1`,
`wave2_synthesis`, `targeted_evidence`, `hitl2`, `rerun`, `readiness`, and
`final_delivery`. The builder SHALL load only explicitly listed package-root
`NODE_SPEC` values and SHALL resolve every logical node through one implementation map.
Fake selection SHALL bind the permanent deterministic fake; real selection without an
explicitly available implementation SHALL fail closed before graph invocation and
SHALL NOT silently fall back to fake.

#### Scenario: Full-fake topology resolves explicitly
- **WHEN** the builder receives the default implementation map
- **THEN** all eleven stable logical nodes resolve from their public package-root `NODE_SPEC`, every top-level node is reachable from START and can reach a terminal path, and no filesystem discovery occurs

#### Scenario: Unavailable real selection fails closed
- **WHEN** an implementation map selects real for a node whose real implementation is not supplied by its owning later change
- **THEN** graph binding fails with the logical node name and `implementation_unavailable` before a checkpoint, model, sandbox tool, or node is invoked

#### Scenario: Internal component cannot become a phase accidentally
- **WHEN** a Wave dispatch/join component or an unlisted node package is present on disk
- **THEN** the normalized top-level topology and registry omit it and the topology contract rejects any edge that exposes it as a logical phase

### Requirement: Deterministic fakes exercise routing and parallel fan-in

Every change-01 node implementation SHALL be deterministic and fixture-driven. No fake
SHALL call a model, network API, MCP server, ACP agent, DeerFlow `task` subagent, or
sandbox research tool. Wave0 and Wave1 SHALL each execute a phase-local three-branch
LangGraph `Send` fan-out and reducer-based fan-in, normalize branch ordering, and
return one typed phase result. Typed routers SHALL support pass, bounded repair,
targeted-evidence repair, rerun, readiness, stop, and final completion without reading
free-form model text.

#### Scenario: Three branches join deterministically
- **WHEN** a Wave fake runs with three branch fixtures completing in any scheduler order
- **THEN** all three unique results are reduced exactly once, normalized into stable order, and the parent phase advances only after fan-in

#### Scenario: Wave0 repair is bounded
- **WHEN** the first Wave0 fixture verdict is repair and the next verdict is pass
- **THEN** the topology executes Wave0 twice, increments the bounded repair counter, records both logical visits, and advances to Wave1 only after pass

#### Scenario: Fake execution has no external side effect
- **WHEN** the complete graph runs under spies for model, web, subagent, and sandbox research tools
- **THEN** every spy remains unused and no evidence, cache, ledger, report, or research output file is created

### Requirement: Graph-owned HITL bridges and resumes from one matching HumanMessage

HITL1 and HITL2 SHALL use public LangGraph interrupts and checkpoint their pending
request before returning. Suspension SHALL project one stable outer `ToolMessage` with
`name=deep_research`, the active tool-call id, and a version-1
`artifact.human_input` request whose source and request id identify the pending research
interrupt. Resume tool arguments SHALL contain no answer. Resume SHALL select only the
latest eligible post-suspension `HumanMessage` from trusted runtime state, correlate a
structured response to the pending source/request id when present, and supply the
accepted value through `Command(resume=...)`. Pre-suspension, mismatched, empty,
synthetic-summary, ToolMessage, AIMessage, model-provided argument, and already consumed
responses SHALL NOT advance the graph.

#### Scenario: Reflected suspension produces the existing UI contract
- **WHEN** the fake graph reaches HITL1 through the reflected async tool
- **THEN** the nested checkpoint contains the pending interrupt before the tool returns a `Command` that adds one stable human-input `ToolMessage` and ends the current lead-agent turn

#### Scenario: Matching card response resumes once
- **WHEN** the newest eligible HumanMessage carries a non-empty `human_input_response` with source `deep_research` and the pending request id
- **THEN** its value resumes that interrupt exactly once, the response message id is recorded as consumed, and later replay cannot advance another interrupt

#### Scenario: Plain-client response can resume
- **WHEN** a client without structured-card metadata supplies one newer visible non-empty HumanMessage after the suspension cursor
- **THEN** its normalized text is accepted for the one pending request and no earlier message is substituted

#### Scenario: Forged or stale response is denied
- **WHEN** an answer appears only in tool arguments, an AI/ToolMessage, a hidden summary, a pre-suspension HumanMessage, a mismatched request id, a different outer thread, or an already consumed HumanMessage
- **THEN** resume returns a typed denial and leaves the checkpoint and pending interrupt unchanged

### Requirement: Lifecycle actions enforce typed and idempotent transitions

The reflected control surface SHALL support `start`, `resume`, `status`, and `cancel`
for the research graph in addition to the independent `infra_probe`. Start SHALL create
a server-generated bounded opaque research id and fail if that trusted-scope namespace
already exists. Resume SHALL require one pending interrupt. Status SHALL inspect without
mutating. Cancel SHALL route a checkpointed suspended lifecycle through a typed cancel
decision to terminal `cancelled`; it SHALL NOT rewrite checkpoint values around the
topology or claim to preempt an active task on another worker. Completed, stopped, and
cancelled status/cancel reads SHALL be idempotent. Wrong-scope, missing, duplicate,
completed-resume, and unsupported-state actions SHALL fail closed or return the existing
terminal state without creating a new lifecycle.

#### Scenario: Start returns an opaque scope and suspends
- **WHEN** a trusted user/thread starts a new fake research lifecycle
- **THEN** the server creates a non-derived opaque research id, runs to HITL1, and returns that id with suspended status without exposing the internal checkpoint key

#### Scenario: Status is read-only
- **WHEN** status is requested for a suspended or terminal lifecycle
- **THEN** it reports the typed phase, generation, status, pending request metadata if any, and durability class without invoking a node or changing the checkpoint

#### Scenario: Cancel follows graph routing
- **WHEN** cancel targets a suspended lifecycle
- **THEN** the pending interrupt receives an internal cancel decision, the graph records terminal `cancelled`, and a repeated cancel returns the same terminal state

#### Scenario: Cross-scope and invalid transitions fail closed
- **WHEN** another outer thread reuses the research id, resume has no pending interrupt, start targets an existing namespace, or resume targets a completed lifecycle
- **THEN** the action returns a redacted typed error or idempotent terminal result and does not mutate or disclose the original lifecycle

### Requirement: Checkpoints and topology contracts remain durable and deterministic

The fake graph SHALL use a versioned research checkpoint namespace isolated from the
outer lead-agent and infra-probe namespaces. Skeleton state SHALL contain only bounded
control fields, branch summaries, HITL correlation, consumed-response ids, and a
bounded logical trace; it SHALL NOT contain raw runtime authority or large research
content. File-backed SQLite SHALL recover a suspended HITL across provider close and a
fresh process. Memory and SQLite memory mode SHALL be labelled same-process only. A
committed normalized topology snapshot SHALL reject unexpected node/edge or reachability
changes. Zero-API E2E coverage SHALL include happy completion, repair, rerun, stop,
cancel, replay denial, and restart resume.

#### Scenario: SQLite restart resumes the same interrupt
- **WHEN** one process starts a lifecycle to HITL, closes the provider, and a fresh process resumes the same trusted user/thread/research id with a matching HumanMessage
- **THEN** the prior pending interrupt and state are recovered, resume continues from that point, and no outer lead-agent or infra-probe checkpoint is read

#### Scenario: Unknown skeleton schema fails closed
- **WHEN** status, resume, or cancel reads a research checkpoint with an unsupported skeleton schema version
- **THEN** it returns `schema_unsupported` before node execution or checkpoint mutation

#### Scenario: Topology drift is detected
- **WHEN** a logical node, edge, route label, or reachability property changes without regenerating the approved semantic snapshot
- **THEN** the topology contract fails with the normalized difference

#### Scenario: Memory does not claim restart durability
- **WHEN** the same-process memory host revisits a lifecycle and a fresh-process capability is inspected
- **THEN** same-process actions work on the retained host but status reports restart recovery unsupported and no restart E2E claim is made
