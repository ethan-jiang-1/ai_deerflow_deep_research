> req: RUI-001, RUI-006

## MODIFIED Requirements

### Requirement: One reflected control tool exposes an infrastructure probe

DeerFlow SHALL continue to resolve
`deerflow_deep_research.tool:deep_research_tool` as the one `deep_research` tool.
The independent business-free `infra_probe` action SHALL retain its optional bounded
URL-safe opaque probe id, isolated topology/namespace, structured redacted result, and
server-generated id behavior. The same strict tool surface SHALL additionally dispatch
the registered research lifecycle actions `start`, `resume`, `status`, and `cancel`
using action-specific validation. Unknown bounded action names SHALL return redacted
`action_unavailable` before RuntimeAdapter, sandbox initialization, namespace derivation,
or checkpoint mutation. Identity, path, sandbox, checkpoint, answer, and every unknown
authority field SHALL remain forbidden.

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
- **WHEN** `infra_probe` receives a research id, start receives caller-supplied probe/research ids, or resume/status/cancel omit their research id or include a probe/answer/authority field
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
state.

#### Scenario: Same-process memory lifecycle reuses one host
- **WHEN** start and a later status/resume action use the default reflected tool with the memory provider in one process
- **THEN** both actions reach the same process-local saver and recipe cache without retaining either request's trusted envelope

#### Scenario: SQL provider closes at suspension
- **WHEN** a file-SQLite start or resume action reaches HITL and returns an outer human-input message
- **THEN** the nested checkpoint is durable and the action's provider context is closed before the reflected tool returns

#### Scenario: Request authority is not cached or checkpointed
- **WHEN** two users or outer threads invoke research actions through the retained host
- **THEN** each action constructs fresh reduced invocation context, derives a different trusted namespace, and neither checkpoint nor cache contains the other request's envelope, host paths, sandbox object, or AppConfig

#### Scenario: Unsupported worker topology remains not ready
- **WHEN** the Gateway worker count is not exactly one
- **THEN** existing readiness continues to fail rather than claiming the combined host locks coordinate lifecycle actions across processes
