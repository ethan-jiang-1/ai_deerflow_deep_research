> req: RUI-001, RUI-006

## MODIFIED Requirements

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

#### Scenario: Unsupported control action is refused early
- **WHEN** the tool receives an unknown bounded action in an otherwise valid request
- **THEN** it returns typed `action_unavailable` without echoing the rejected value and without adapting runtime or touching sandbox/checkpoint state

#### Scenario: Action-field mismatch is schema-rejected
- **WHEN** `infra_probe` receives a research id, start receives caller-supplied probe/research ids or question text, resume/status/cancel omit their research id or include a probe/answer/authority field, or any action receives an unknown extra field
- **THEN** strict validation emits only normalized field/code diagnostics and dispatch does not occur

## ADDED Requirements

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
