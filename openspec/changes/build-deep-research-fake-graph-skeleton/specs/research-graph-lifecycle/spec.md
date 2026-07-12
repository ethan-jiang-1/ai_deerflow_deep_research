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
SHALL NOT silently fall back to fake. Change-01 packages SHALL use one canonical pure
unavailable-real sentinel rather than divergent placeholder behavior.

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
targeted-evidence convergence, all five HITL2 decisions
(`proceed | revise_view | repair | rerun | stop`), typed readiness repair targets,
bounded final-delivery self-repair/evidence-blocked return, and completion without reading free-form model text.
The validated fixture plan SHALL come from handler/test construction rather than public
tool arguments and SHALL be persisted as closed data needed for deterministic resume.
Bootstrap SHALL expose both `needs_input -> hitl1` and
`profile_complete -> topic_planning`; the default fake path SHALL still exercise HITL1.

#### Scenario: Three branches join deterministically
- **WHEN** a Wave fake runs with three branch fixtures completing in any scheduler order
- **THEN** all three unique results are reduced exactly once, normalized into stable order, and the parent phase advances only after fan-in

#### Scenario: Complete profile bypass is already part of topology
- **WHEN** the bootstrap fixture returns `profile_complete`
- **THEN** the graph routes directly to topic planning without creating HITL1, while the default fixture still routes through HITL1 and the topology snapshot remains unchanged

#### Scenario: Wave0 repair is bounded
- **WHEN** the first Wave0 fixture verdict is repair and the next verdict is pass
- **THEN** the topology executes Wave0 twice, increments the bounded repair counter, records both logical visits, and advances to Wave1 only after pass

#### Scenario: Targeted evidence always returns through synthesis
- **WHEN** Wave2, HITL2 repair, or readiness routes to targeted evidence
- **THEN** the targeted phase returns to Wave2 synthesis before HITL2 or readiness can be reached again, and a fixture cannot bypass synthesis by routing directly to HITL2

#### Scenario: Every later repair edge remains explicit
- **WHEN** fixtures select Wave1 repair, HITL2 revise-view/repair, any readiness repair target, final-delivery self-repair, or final evidence-blocked return to readiness
- **THEN** the normalized topology follows the declared bounded edge and eventually reaches the expected next gate or typed terminal without changing node implementations

#### Scenario: Fake execution has no external side effect
- **WHEN** the complete graph runs under spies for model, web, subagent, and sandbox research tools
- **THEN** every spy remains unused and no evidence, cache, ledger, report, or research output file is created

### Requirement: Graph-owned HITL bridges and resumes from one matching HumanMessage

HITL1 and HITL2 SHALL use public LangGraph interrupts and checkpoint their pending
request before returning. Suspension SHALL project one stable outer `ToolMessage` with
`name=deep_research`, the active tool-call id, and a version-1
`artifact.human_input` request whose source and request id identify the pending research
interrupt. Its title/context SHALL visibly identify `implementation_mode=full_fake`.
Its bounded text fallback SHALL contain the same version-1 control-result
envelope, including opaque research and request ids, that non-suspended actions return.
Resume tool arguments SHALL contain no answer. Resume SHALL select only the
latest eligible post-suspension `HumanMessage` from trusted runtime state, correlate a
structured response to the pending source/request id when present, and supply the
accepted request id, HumanMessage id, exact value, response kind, and optional option id
as one typed `Command(resume=...)` payload. The resumed HITL node SHALL let LangGraph
consume the pending interrupt and SHALL record consumed request/message ids in the same
graph transition; runtime code SHALL NOT patch interrupt tasks or checkpoint fields
outside the graph. Pre-suspension, mismatched, empty,
synthetic-summary, ToolMessage, AIMessage, model-provided argument, and already consumed
responses SHALL NOT advance the graph. After checkpoint inspection, an exact match to
the checkpointed consumed request/message pair SHALL be classified before fresh-answer
correlation and MAY only reproject the current durable pending or terminal result
without requiring the old interrupt to remain pending or invoking another node.

The LangGraph checkpoint interrupt task SHALL be the only pending-request authority;
skeleton state SHALL NOT duplicate a mutable pending descriptor. Request ids SHALL
include a deterministic HITL ordinal derived from prior checkpointed logical HITL
visits, so retrying the same interrupt is stable and a later HITL2 in the same
generation cannot collide. A suspended lifecycle and every fresh resume SHALL require
exactly one pending interrupt descriptor. Multiple descriptors SHALL always fail
closed; zero SHALL be valid only for a typed terminal lifecycle or the locked action
before suspension, and an exact consumed-response delivery retry MAY only reproject
that current durable outcome.

HITL2 SHALL advertise stable option ids and machine values for
`proceed | revise_view | repair | rerun | stop`. Structured option responses SHALL
match both the pending id and value; plain responses SHALL match one advertised value
after bounded normalization. Invalid choice data SHALL be rejected before graph resume
and SHALL leave the same pending interrupt intact.

#### Scenario: Reflected suspension produces the existing UI contract
- **WHEN** the fake graph reaches HITL1 through the reflected async tool
- **THEN** the nested checkpoint contains the pending interrupt before the tool returns a `Command` that adds one stable human-input `ToolMessage`, visibly labels the card `full_fake`, and ends the current lead-agent turn

#### Scenario: Matching card response resumes once
- **WHEN** the newest eligible HumanMessage carries a non-empty `human_input_response` with source `deep_research` and the pending request id
- **THEN** one typed response envelope resumes that interrupt exactly once, LangGraph consumes the pending interrupt, the HITL node records the response request/message ids and completed logical visit in the same transition, and later replay cannot advance another interrupt

#### Scenario: Plain-client response can resume
- **WHEN** a client without structured-card metadata supplies one newer visible non-empty HumanMessage after the suspension cursor
- **THEN** its normalized text is accepted for the one pending request and no earlier message is substituted

#### Scenario: Forged or stale response is denied
- **WHEN** an answer appears only in tool arguments, an AI/ToolMessage, a hidden summary, a pre-suspension HumanMessage, a mismatched request id, or a different outer thread
- **THEN** resume returns `response_mismatch` for an in-scope correlation failure or indistinguishable `research_not_found` for another thread, and leaves the checkpoint and pending interrupt unchanged

#### Scenario: Consumed response reprojects durable outcome
- **WHEN** resume is retried with a HumanMessage already recorded as consumed after the graph reached its next interrupt or terminal checkpoint
- **THEN** the handler reprojects that current suspended or terminal result without invoking a node or accepting the message as another answer

#### Scenario: HITL2 option tampering is denied
- **WHEN** an option response pairs a valid option id with another value, supplies an unknown id/value, or plain text does not match one advertised decision
- **THEN** resume returns `response_invalid` before `Command(resume=...)` and preserves the same HITL2 pending request

### Requirement: Lifecycle actions enforce typed and idempotent transitions

The reflected control surface SHALL support `start`, `resume`, `status`, and `cancel`
for the research graph in addition to the independent `infra_probe`. Start SHALL accept
no caller-selected research id or question. It SHALL bind the newest visible genuine
user `HumanMessage` candidate, require its stable message id and bounded exact text, and derive a
URL-safe collision-resistant opaque research id from a versioned domain-separated hash
of a canonical boundary-preserving encoding of trusted user/thread scope. Repeating
start for the same message SHALL inspect and reproject the same pending or terminal
lifecycle; it SHALL NOT invoke a
second graph or reset state. A different eligible start message in the same outer thread
SHALL return `thread_research_exists` with the existing opaque id/status and SHALL NOT
create a second lifecycle or reset state. New research requires a new outer thread. An
existing checkpoint with malformed stored start correlation SHALL fail closed. Every
fresh resume SHALL require one pending interrupt; an exact checkpointed
consumed-response retry SHALL only reproject the current durable outcome. Status SHALL
inspect without mutating. Cancel SHALL
route a checkpointed suspended lifecycle through a typed cancel
decision to terminal `cancelled`; it SHALL NOT rewrite checkpoint values around the
topology or claim to preempt an active task on another worker. Status SHALL always be
read-only. Cancel on `completed | stopped | cancelled | blocked` SHALL return that
terminal result idempotently. Resume without exactly one pending interrupt, including
every terminal lifecycle, SHALL return `invalid_transition`; an already consumed
response SHALL instead reproject the current pending or terminal durable result without
graph invocation; wrong user/thread scope and absence SHALL both return
`research_not_found`; unsupported checkpoint schema SHALL return
`schema_unsupported`. None SHALL create or mutate a lifecycle. Every action SHALL
return a bounded version-1 control-result envelope. Schema version, action, code,
durability, and `implementation_mode=full_fake` SHALL always be present. A validated or
generated research id SHALL be present only when safe and applicable. Status, phase,
and generation SHALL be present only once a lifecycle is known; a pre-lifecycle denial
SHALL omit them rather than invent graph state and SHALL use `unavailable` durability
if provider classification has not occurred. A suspended result SHALL add its pending
request id, and a terminal result MAY add its terminal reason. Every result SHALL omit
raw identity, internal namespace, host paths, fixtures, and checkpoint values. Exact
start text SHALL be limited to 16,384 characters and serialized control results to
4,096 characters; semantic content SHALL fail validation rather than be silently
truncated. Fake repair exhaustion SHALL produce typed `blocked`.

After strict schema and registered-action validation, version-1 lifecycle-owned result
codes SHALL be closed to normal `suspended | completed | stopped | cancelled | blocked`,
read-only `status_ok`, and denial `start_message_invalid | thread_research_exists |
response_mismatch | response_invalid | invalid_transition | research_not_found |
schema_unsupported | checkpoint_inconsistent | interactive_required |
human_input_transport_unavailable | exclusive_control_call_required |
implementation_unavailable`. RuntimeAdapter/GraphHost MAY preserve an existing
change-00 redacted infrastructure code such as `restart_required`; arbitrary free-form
codes SHALL be rejected. Strict schema diagnostics and unknown-action
`action_unavailable` SHALL remain pre-lifecycle tool contracts.

Generated and accepted research ids SHALL match `^r_[A-Za-z0-9_-]{43}$`; malformed
lifecycle ids SHALL fail strict validation before trusted runtime or provider access and
SHALL remain distinct from the infra-probe id domain.

Fake final delivery SHALL emit only a typed terminal fixture marker. It SHALL NOT emit
or imply research findings, evidence, citations, report content, or user-ready research
completion.

Start selection SHALL ignore non-Human and hidden synthetic/summary/dynamic-context
messages only while locating the newest visible genuine HumanMessage, and SHALL NOT
fall back to an older visible request when that newest candidate is a human-input
response, lacks a stable id, or has invalid content. Start and plain-response content
SHALL accept either a string or an ordered list containing only text blocks, concatenate
list text in order without an inserted separator, and reject non-text/malformed blocks,
empty text, or oversized content rather than silently dropping or normalizing it. A
structured human-input response MAY remain genuine when hidden by the UI; every other
hidden HumanMessage SHALL remain ineligible. Fresh resume SHALL deny a failing newest
candidate without substituting an older response.

#### Scenario: Start returns an opaque scope and suspends
- **WHEN** a trusted user/thread starts a new fake research lifecycle
- **THEN** the handler binds the latest eligible visible HumanMessage, derives a stable opaque research id, records its message correlation and request digest, runs to HITL1, and returns the versioned suspended result without exposing the internal checkpoint key

#### Scenario: Repeated start reprojects instead of duplicating
- **WHEN** the same start is retried after the nested HITL checkpoint was committed but before its outer ToolMessage was delivered
- **THEN** the same research id and pending request are recovered and reprojected with the current tool-call id, no node runs twice, and no orphan lifecycle is created

#### Scenario: Invalid start message is denied
- **WHEN** no visible genuine HumanMessage remains after synthetic-context filtering, or the newest visible candidate is missing a stable id, empty/oversized, a human-input response, or otherwise ineligible as a new research request
- **THEN** start returns redacted `start_message_invalid` before namespace derivation or checkpoint mutation

#### Scenario: Different start in the same thread does not create a multi-active run
- **WHEN** a different eligible HumanMessage requests start in an outer thread that already owns a suspended or terminal research lifecycle
- **THEN** the action returns `thread_research_exists` with the existing opaque id/status and does not invoke or reset the graph

#### Scenario: Status is read-only
- **WHEN** status is requested for a suspended or terminal lifecycle
- **THEN** it reports the bounded version-1 control result with typed phase, generation, status, pending request metadata if any, and durability class without invoking a node or changing the checkpoint

#### Scenario: Full-fake terminal cannot masquerade as research output
- **WHEN** the fake lifecycle reaches final delivery
- **THEN** the result is marked `implementation_mode=full_fake`, contains only a terminal fixture marker, and contains no finding, evidence, citation, report, or claim that real research completed

#### Scenario: Cancel follows graph routing
- **WHEN** cancel targets a suspended lifecycle
- **THEN** the pending interrupt receives an internal cancel decision, the graph records terminal `cancelled`, and a repeated cancel returns the same terminal state

#### Scenario: Cross-scope and invalid transitions fail closed
- **WHEN** another outer thread reuses the research id, a fresh response resumes with no pending interrupt or targets a terminal lifecycle, or start targets an existing namespace
- **THEN** wrong scope returns `research_not_found`, fresh no-pending or terminal resume returns `invalid_transition`, same-message start reprojects, different-message start returns `thread_research_exists`, and no path mutates or discloses another scope's lifecycle

### Requirement: Checkpoints and topology contracts remain durable and deterministic

The fake graph SHALL use a versioned research checkpoint namespace isolated from the
outer lead-agent and infra-probe namespaces. Skeleton state SHALL contain only bounded
control fields, branch summaries, HITL correlation, consumed-response ids, and a
bounded logical trace; it SHALL NOT contain raw runtime authority or large research
content. File-backed SQLite SHALL recover a suspended HITL across provider close and a
fresh process. Memory and SQLite memory mode SHALL be labelled same-process only. A
committed normalized topology snapshot SHALL reject unexpected node/edge or reachability
changes. Zero-API E2E coverage SHALL include happy completion, repair, rerun, stop,
cancel, stale-response denial, consumed-response delivery reprojection, and restart
resume.

#### Scenario: SQLite restart resumes the same interrupt
- **WHEN** one process starts a lifecycle to HITL, closes the provider, and a fresh process resumes the same trusted user/thread/research id with a matching HumanMessage
- **THEN** the prior pending interrupt and state are recovered, resume continues from that point, and no outer lead-agent or infra-probe checkpoint is read

#### Scenario: Committed suspension survives result-delivery failure
- **WHEN** the nested HITL checkpoint commits and the action fails before the outer ToolMessage is delivered
- **THEN** retrying start from the same trusted scope and start HumanMessage reopens the same namespace and reprojects the same pending request without rerunning completed nodes

#### Scenario: Unknown skeleton schema fails closed
- **WHEN** status, resume, or cancel reads a research checkpoint with an unsupported skeleton schema version
- **THEN** it returns `schema_unsupported` before node execution or checkpoint mutation

#### Scenario: Topology drift is detected
- **WHEN** a logical node, edge, route label, or reachability property changes without regenerating the approved semantic snapshot
- **THEN** the topology contract fails with the normalized difference

#### Scenario: Memory does not claim restart durability
- **WHEN** the same-process memory host revisits a lifecycle and a fresh-process capability is inspected
- **THEN** same-process actions work on the retained host but status reports restart recovery unsupported and no restart E2E claim is made
