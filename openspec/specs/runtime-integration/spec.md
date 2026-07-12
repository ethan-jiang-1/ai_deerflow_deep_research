# runtime-integration Specification

> req: RUI-001, RUI-002, RUI-003, RUI-004, RUI-005, RUI-006

## Purpose
The reflected Deep Research control tool, trusted runtime adaptation, isolated checkpoint namespaces, GraphHost lifecycle, and infrastructure-probe persistence.
## Requirements
### Requirement: One reflected control tool exposes an infrastructure probe

DeerFlow SHALL continue to resolve
`deerflow_deep_research.tool:deep_research_tool` as the one `deep_research` tool.
The independent business-free `infra_probe` action SHALL retain its optional bounded
URL-safe opaque probe id, isolated topology/namespace, structured redacted result, and
server-generated id behavior. When omitted, the probe id SHALL retain at least 128 bits
of server CSPRNG entropy and no scope-derived identity/path text; a caller-supplied id
SHALL never become an internal checkpoint key without trusted scope/domain derivation.
The same strict tool surface SHALL additionally dispatch
the registered research lifecycle actions `start`, `resume`, `status`, and `cancel`
using action-specific validation. Unknown bounded action names SHALL return redacted
`action_unavailable` before RuntimeAdapter, sandbox initialization, namespace derivation,
or checkpoint mutation. Identity, path, sandbox, checkpoint, answer, and every unknown
authority field SHALL remain forbidden.

#### Scenario: Probe starts through the reflected tool
- **WHEN** a fake DeerFlow runtime invokes `infra_probe` with valid trusted context
- **THEN** the tool writes and reads one probe checkpoint and returns an opaque probe reference, backend durability class, and status using the unchanged probe contract

#### Scenario: Probe remains independently available
- **WHEN** a valid trusted runtime invokes `infra_probe` before or after a research lifecycle action
- **THEN** the tool uses the original probe topology and namespace, returns only probe fields, and does not read or mutate a research checkpoint

#### Scenario: Registered lifecycle action reaches trusted dispatch
- **WHEN** the tool receives an action-valid `start`, `resume`, `status`, or `cancel` request
- **THEN** it adapts trusted runtime and dispatches only to that registered lifecycle handler without accepting caller identity, path, checkpoint, or answer authority

#### Scenario: Unsupported control action is refused
- **WHEN** the tool receives an unknown bounded action in an otherwise valid request
- **THEN** it returns typed `action_unavailable` without echoing the rejected value and without adapting runtime or touching sandbox/checkpoint state

#### Scenario: Extra authority field is schema-rejected
- **WHEN** `infra_probe` receives a research id, start receives caller-supplied probe/research ids or question text, resume/status/cancel omit their research id or include a probe/answer/authority field, or any action receives an unknown extra field
- **THEN** strict validation emits only normalized field/code diagnostics and dispatch does not occur

### Requirement: Runtime authority comes only from trusted context
RuntimeAdapter SHALL require the explicit server-injected user, outer thread/run, and AppConfig from DeerFlow runtime context, validate thread-data roots from runtime state against that user/thread, and obtain the same parent sandbox through DeerFlow's public async lazy initializer when it is not yet present. It SHALL place raw values in a runtime-owned TrustedRuntimeEnvelope and SHALL NOT invent a research scope. A separate runtime-owned projection SHALL require a registered research handler's validated opaque scope id before deriving a research root and pure domain GraphContextView/capability/NodeAgentContext values. Graph nodes SHALL consume only those pure contracts, and model-facing NodeAgentContext SHALL contain only opaque attribution, canonical virtual roots, and policy. The tool args schema SHALL forbid caller-supplied identity, path, sandbox, and checkpoint fields; the permissive `resolve_runtime_user_id()` fallback to `default` SHALL NOT satisfy a missing trusted runtime identity. The change 00 infrastructure probe SHALL not create a research projection or workspace.

#### Scenario: Trusted runtime is adapted without inventing research scope
- **WHEN** runtime context and state contain one consistent effective user, thread, sandbox, and thread-data mapping
- **THEN** RuntimeAdapter emits only a runtime-owned envelope and no research root or node-agent projection

#### Scenario: Registered handler scope is authority-reduced
- **WHEN** a registered research handler supplies a validated opaque scope id with a trusted envelope
- **THEN** runtime projection emits frozen pure graph and node-agent contracts with canonical virtual roots and no model-controlled authority fields, AppConfig, or host paths

#### Scenario: Fresh thread initializes its parent sandbox
- **WHEN** trusted thread data exists but lazy parent sandbox state has not yet been created
- **THEN** RuntimeAdapter uses the public async sandbox initializer once, validates the resulting parent sandbox, and does not create a second sandbox/thread lifecycle

#### Scenario: Forged cross-user fields are denied
- **WHEN** tool arguments include user, thread, host path, sandbox, checkpoint, or any unknown field
- **THEN** schema validation rejects the invocation before RuntimeAdapter, namespace derivation, or filesystem access

#### Scenario: Gateway identity overrides client context spoofing
- **WHEN** an authenticated or explicit auth-disabled Gateway request supplies a conflicting user id through body context or body config context
- **THEN** the runtime user is the server-injected authenticated id or synthetic `default`, never the client value

#### Scenario: Missing explicit runtime identity fails closed
- **WHEN** a hand-built runtime has no non-empty `runtime.context["user_id"]` even though DeerFlow's generic helper could fall back to `default`
- **THEN** RuntimeAdapter rejects it before sandbox initialization, namespace derivation, or checkpoint access

#### Scenario: Startup sandbox drift fails before initialization
- **WHEN** live AppConfig sandbox values do not match the launcher-captured startup fingerprint
- **THEN** RuntimeAdapter returns typed `restart_required` before calling the sandbox initializer

### Requirement: Nested checkpoint namespaces are isolated
The runtime SHALL derive the nested checkpoint key from a versioned, domain-separated, collision-resistant encoding of effective user, outer thread, and opaque probe/research id. The caller SHALL not provide the derived key, and the nested graph SHALL not share the outer lead-agent checkpoint identity. Same-namespace mutating actions SHALL be serialized in the supported single-worker runtime; unsupported multi-worker execution SHALL fail readiness rather than claim cross-process exclusion.

#### Scenario: Stable identity revisits the same probe
- **WHEN** the same effective user, outer thread, and probe id are used in a later action
- **THEN** namespace derivation returns the same internal key and the new probe invocation observes the prior visit marker without claiming research resume

#### Scenario: Cross-scope collision is prevented
- **WHEN** two users or two outer threads reuse the same probe id
- **THEN** their internal keys and checkpoint histories differ and neither can inspect the other

### Requirement: GraphHost owns topology but not live SQL resources
GraphHost SHALL cache only request-independent builder/topology recipes and a generic typed action-handler registry, with only the infrastructure-probe handler registered by change 00. Cached objects SHALL NOT retain runtime envelopes, reduced dependencies/capabilities, namespace values, checkpointers, or user/thread data; each action SHALL bind fresh dependencies and compile inside the lifetime of the effective selected checkpointer. SQLite/Postgres SHALL use `make_checkpointer(app_config)` per action and close it on success, failure, or cancellation; the project-owned provider classifier SHALL follow the official legacy `checkpointer`-over-`database` precedence; embedded phase agents SHALL not receive that checkpointer. The infrastructure probe SHALL retain its own versioned topology/namespace when change 01 adds the separate fake research graph.

#### Scenario: SQL provider is reopened and closed
- **WHEN** two probe actions run against a fake async SQL provider
- **THEN** each action enters and exits its own provider context and no compiled graph or connection escapes that context

#### Scenario: Invocation failure still closes resources
- **WHEN** the probe node raises or its outer task is cancelled
- **THEN** provider cleanup and child-task cleanup complete and the error is not reported as success

#### Scenario: Startup provider drift does not split checkpoints
- **WHEN** live AppConfig database/checkpointer values differ from the launcher-captured startup fingerprint
- **THEN** GraphHost returns typed `restart_required` before opening a saver or reading/writing a nested checkpoint

### Requirement: Persistence guarantees match the selected backend
The probe SHALL describe memory and SQLite memory-mode connections as same-process only, file-backed SQLite/Postgres as durable across provider reopen and Gateway restart when correctly configured, and invalid or missing connection data as unavailable. Probe and doctor output SHALL NOT claim stronger durability than the active resolved backend provides.

#### Scenario: Memory revisits only in one process
- **WHEN** two probe actions use the same process-local memory GraphHost
- **THEN** the second action observes prior state and the response labels restart recovery unsupported

#### Scenario: Persistent provider survives reopen
- **WHEN** a file-backed SQLite or valid Postgres probe is written, its provider context is closed, and a fresh context reads the same namespace
- **THEN** the prior checkpoint is recovered without using outer lead-agent checkpoint state

#### Scenario: SQLite memory mode is not restart durable
- **WHEN** the effective legacy SQLite connection is `:memory:` or an equivalent memory-mode URI
- **THEN** GraphHost and doctor report same-process-only durability and never claim provider-reopen or Gateway-restart recovery

#### Scenario: Legacy provider overrides unified database
- **WHEN** legacy `checkpointer` selects memory and `database` selects SQLite, or vice versa
- **THEN** GraphHost and doctor both use and report the legacy selection, matching `make_checkpointer(app_config)`

### Requirement: Research lifecycle dispatch preserves runtime and resource boundaries

The default reflected dispatch SHALL use one lazily created process-local combined
GraphHost registering the infra-probe handler and all four research handlers. The host
MAY retain request-independent recipes, lock stripes, and its process-local memory
saver, but SHALL NOT retain a TrustedRuntimeEnvelope, reduced dependencies, research
scope, raw identity, host path, sandbox handle, AppConfig, SQL provider, or compiled
request-bound graph. Each SQL lifecycle action SHALL continue to open, use, and close
the official effective checkpointer context inside that action. Runtime projection
SHALL occur only after a registered handler validates the research id, and invocation
dependencies SHALL travel through non-checkpointed LangGraph context rather than graph
state. That context SHALL expose a runtime-owned reduced dependency resolver so looped
nodes receive fresh per-attempt NodeBuildDependencies instead of a precomputed stale
attempt context. Lifecycle handlers SHALL return one bounded version-1 control-result
envelope with mandatory `implementation_mode=full_fake`; suspended results SHALL use
the same envelope as ToolMessage text fallback and add the human-input artifact.
All four research handlers SHALL reference the same versioned graph recipe/topology;
they SHALL NOT compile action-specific graph shapes against the shared research
checkpoint namespace.

Internal server-owned `non_interactive` or fail-closed `disable_clarification` context
SHALL make HITL-producing start/resume unavailable until an explicit later auto-decision
policy exists; status and cancel SHALL remain available and no client tool field may
override that interaction capability. A caller-supplied clarification-disabled signal
MAY only remove interaction capability and SHALL NOT enable fixture answers or
autonomous progress.

Known IM-channel contexts identified by reduced `context.channel_user_id` and/or
`context.channel_name` presence SHALL be treated as human-input-transport unavailable
because the current channel bridge only extracts `ask_clarification` ToolMessages.
Until a separate upstream compatibility change adds generic artifact handling,
HITL-producing start/resume SHALL fail before mutation; status/cancel SHALL remain
available and downstream code SHALL NOT emit a synthetic AIMessage workaround.

Each research lifecycle action SHALL require its active tool-call id to identify the
sole `deep_research` call in the latest outer AIMessage. Missing correlation, duplicate
deep-research calls, or any sibling tool call SHALL return
`exclusive_control_call_required` before RuntimeAdapter, provider, or nested graph
mutation. This requirement SHALL NOT claim that downstream code cancels sibling calls;
the independent infra probe retains its existing dispatch behavior.

#### Scenario: Same-process memory lifecycle reuses one host
- **WHEN** start and a later status/resume action use the default reflected tool with the memory provider in one process
- **THEN** both actions reach the same process-local saver and recipe cache without retaining either request's trusted envelope

#### Scenario: Lifecycle actions share one graph recipe
- **WHEN** start, resume, status, and cancel bind the same research namespace
- **THEN** every handler compiles or inspects the identical versioned topology recipe and no action-specific node/edge drift can reinterpret the checkpoint

#### Scenario: SQL provider closes at suspension
- **WHEN** a file-SQLite start or resume action reaches HITL and returns an outer human-input message
- **THEN** the nested checkpoint is durable and the action's provider context is closed before the reflected tool returns

#### Scenario: Request authority is not cached or checkpointed
- **WHEN** two users or outer threads invoke research actions through the retained host
- **THEN** each action constructs fresh reduced invocation context, derives a different trusted namespace, and neither checkpoint nor cache contains the other request's envelope, host paths, sandbox object, or AppConfig

#### Scenario: Looped node receives fresh attempt dependencies
- **WHEN** a node executes again after repair or rerun within the same lifecycle action
- **THEN** the invocation-context resolver creates NodeBuildDependencies with the new deterministic attempt id and does not reuse a cached dependency object from the prior attempt

#### Scenario: Suspended and terminal results share one wire contract
- **WHEN** start or resume suspends, or any lifecycle action returns a non-suspended result
- **THEN** the tool exposes the same bounded versioned control fields, with the suspended form additionally carrying `artifact.human_input`, and neither form leaks internal scope or checkpoint data

#### Scenario: Non-interactive lifecycle fails before suspension
- **WHEN** runtime context marks the run non-interactive or clarification-disabled and start or resume is requested without a later explicit auto-decision policy
- **THEN** the tool returns typed `interactive_required` before graph/checkpoint mutation and does not fabricate a fixture answer, while status and cancel remain dispatchable

#### Scenario: Known IM transport fails closed
- **WHEN** runtime context contains an IM channel-user or channel-name marker for a checked-in bridge that does not consume generic deep-research human-input ToolMessages
- **THEN** start/resume returns `human_input_transport_unavailable` before graph/checkpoint mutation, status/cancel remain dispatchable, and no synthetic AI message is appended

#### Scenario: Lifecycle call with a sibling is refused
- **WHEN** the latest AIMessage has a missing or mismatched active tool-call id, two deep-research calls, or deep research beside any other tool call
- **THEN** the lifecycle action returns `exclusive_control_call_required` before RuntimeAdapter or nested mutation and makes no claim to cancel the sibling call

#### Scenario: Unsupported worker topology remains not ready
- **WHEN** the Gateway worker count is not exactly one
- **THEN** existing readiness continues to fail rather than claiming the combined host locks coordinate lifecycle actions across processes
