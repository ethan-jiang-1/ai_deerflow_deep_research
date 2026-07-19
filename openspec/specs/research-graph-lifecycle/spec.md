# research-graph-lifecycle Specification

> req: REG-001, REG-002, REG-003, REG-004, REG-005, REG-006, REG-007, REG-008, REG-009, REG-010, REG-011

## Purpose
The stable Deep Research graph topology, deterministic implementation selection,
full-fake routing and fan-in, graph-owned HITL lifecycle, and durable checkpoint
semantics that later changes replace node by node without redefining control flow.
## Requirements
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

Real HITL1 SHALL add exactly two HITL1 route labels to the normalized topology:
`needs_followup -> hitl1` and `exhausted -> blocked/END`. Existing HITL1 labels
`accepted -> topic_planning` and `cancel -> cancelled/END` SHALL remain unchanged.
The self-edge is the durable same-phase follow-up path for incomplete profile answers;
the exhausted edge is the typed blocked path for pre-interrupt brief-generation failure.
No new top-level phase is introduced, and no later fake phase is allowed to observe a
partially completed HITL1 profile as if it were accepted.

Real topic planning SHALL add exactly one topic-planning route label to the normalized
topology: `exhausted -> blocked/END`. The existing `topic_planning --next--> wave0`
label and the inbound `bootstrap/hitl1 -> topic_planning` and `rerun -> topic_planning`
edges SHALL remain unchanged. The exhausted edge is the typed blocked path for a
planner that fails validation or coverage after its bounded repair. topic_planning
remains a non-gated controller node that writes its own route labels and does not
import LangGraph. Real topic planning SHALL chain off the real profile: selecting
`topic_planning=real` without `hitl1=real` (which itself requires `bootstrap=real`)
SHALL fail closed before graph invocation, because the planner consumes the real
HITL1 profile constraints.

Real Wave2 synthesis SHALL add exactly one Wave2 route label to the normalized
topology: `exhausted -> blocked/END`. Existing labels
`evidence_needed -> targeted_evidence` and `pass -> hitl2`, plus the
`targeted_evidence -> wave2_synthesis` return edge, SHALL remain unchanged. The
exhausted edge is the typed blocked path when searchable gaps remain after the
existing Wave2 gate repair budget or fatigue contract is exhausted; no new top-level
phase or alternate bypass around synthesis is introduced.

#### Scenario: Full-fake topology resolves explicitly
- **WHEN** the builder receives the default implementation map
- **THEN** all eleven stable logical nodes resolve from their public package-root `NODE_SPEC`, every top-level node is reachable from START and can reach a terminal path, and no filesystem discovery occurs

#### Scenario: Unavailable real selection fails closed
- **WHEN** an implementation map selects real for a node whose real implementation is not supplied by its owning later change
- **THEN** graph binding fails with the logical node name and `implementation_unavailable` before a checkpoint, model, sandbox tool, or node is invoked

#### Scenario: Real HITL1 follow-up and blocked routes are explicit
- **WHEN** the mixed graph selects real HITL1
- **THEN** the builder contains conditional edges for `hitl1 --needs_followup--> hitl1` and `hitl1 --exhausted--> END`, and topology validation recognizes the exhausted route as terminal `blocked`

#### Scenario: Internal component cannot become a phase accidentally
- **WHEN** a Wave dispatch/join component, HITL1 follow-up helper, or an unlisted node package is present on disk
- **THEN** the normalized top-level topology and registry omit it and the topology contract rejects any edge that exposes it as a logical phase

#### Scenario: Real topic planning blocked route is explicit
- **WHEN** the mixed graph selects real topic planning
- **THEN** the builder carries a conditional edge `topic_planning -> {next: wave0, exhausted: END}`, the `next` and inbound edges are unchanged, and topology validation recognizes the topic-planning `exhausted` route as terminal `blocked`

#### Scenario: Real topic planning without the real profile chain fails closed
- **WHEN** a recipe selects `topic_planning=real` without `hitl1=real`
- **THEN** recipe construction fails with a typed dependency error before the graph is compiled or invoked

#### Scenario: Real Wave2 blocked route is explicit
- **WHEN** the real Wave2 gate exhausts its bounded repair or fatigue contract while searchable gaps remain
- **THEN** the builder routes `wave2_synthesis --exhausted--> END`, normalized topology classifies the endpoint as `blocked`, and no targeted or HITL2 bypass occurs

### Requirement: Deterministic fakes exercise routing and parallel fan-in

Every fake node implementation SHALL be deterministic and fixture-driven. No fake
SHALL call a model, network API, MCP server, ACP agent, DeerFlow `task` subagent, or
sandbox research tool. Wave0 and Wave1 SHALL each execute a phase-local three-branch
LangGraph `Send` fan-out through the shared work-unit kernel, reduce fixture
`CandidateResult` values without losing or replacing a winner, run deterministic
submit, drain pending/in-flight work, and return one typed phase result. Their fixture
workers MAY write only their controller-assigned `work/<work_id>/<attempt_id>/`
artifacts, and only deterministic submit MAY publish the fixture submission ledger.

Typed routers SHALL support pass, bounded repair, targeted-evidence convergence, all
five HITL2 decisions (`proceed | revise_view | repair | rerun | stop`), typed readiness
repair targets, bounded final-delivery self-repair/evidence-blocked return, real HITL1
follow-up/blocking routes (`needs_followup`, `exhausted`), and completion without
reading free-form model text in fake phases. The validated fixture plan SHALL come from
handler/test construction rather than public tool arguments and SHALL be persisted as
closed data needed for deterministic resume. Bootstrap SHALL expose both
`needs_input -> hitl1` and `profile_complete -> topic_planning`; the default fake path
SHALL still exercise fake HITL1 exactly once and SHALL NOT take the real-HITL1
`needs_followup` or `exhausted` routes unless real HITL1 is selected.

Gate evaluation SHALL remain the routing authority for gated phases. Every gated phase
node SHALL have a registered `GateDefinition` containing a `FixtureSequenceRule` (fake
graph) or real rules (later changes). Wave0 and Wave1 SHALL prepend the shared
deterministic work-completion rule so fixture `pass` cannot override failed or
unaccepted work. After the phase-local component reports structural drain, the node
wrapper SHALL apply a pure reducer preview of the node's work/status/accepted-ref
update to the input state and invoke `evaluate_gate()` against that post-work view, not
the stale pre-node state. The preview SHALL use the same reducers and ownership checks
as checkpoint application for an explicit allowlist of gate-readable work fields. It
SHALL exclude `phase`, `route`, `execution_trace`, fixture visit counters, and every
gate-owned field so fixture sequence indexing and sole-writer authority do not advance
early. The preview SHALL perform no I/O or checkpoint mutation. Gate evaluation then
runs all rules, collects failures, and produces a typed `PhaseVerdict`. The gate's
`route_map` SHALL translate the verdict to the route string written to
`state["route"]`. The existing `_route()` function SHALL read `state["route"]`
unchanged. The graph's conditional edges SHALL continue to match the same route labels
as change 01. HITL1 remains a non-gated controller node and writes its own route labels
directly.

Fixture sequence indexing SHALL remain in `FixtureSequenceRule`, attempt/budget
tracking SHALL remain in the gate kernel, and the frozen `repair_counts` state field
SHALL remain unwritten. The topology snapshot SHALL remain identical in top-level
node/edge structure and every route label SHALL match change 01. Work-unit dispatch,
worker, submit, and drain nodes are internal components and SHALL NOT become top-level
logical phases.

#### Scenario: Three branches join deterministically
- **WHEN** a Wave fake runs with three fixture workers completing in any scheduler order
- **THEN** all three unique candidates are reduced exactly once, normalized into stable order, accepted with at most one winner per logical work across all its attempts, and the parent phase advances only after submit fan-in and drain

#### Scenario: Complete profile bypass is already part of topology
- **WHEN** the bootstrap fixture returns `profile_complete`
- **THEN** the graph routes directly to topic planning without creating HITL1, while the default fixture still routes through fake HITL1 and the topology snapshot remains deterministic

#### Scenario: Wave0 repair is bounded
- **WHEN** the Wave0 fixture gate definition sequences `repair` then `pass`
- **THEN** gate evaluation returns `REPAIR` on the first attempt (route `"repair"`), the repair path retries only unaccepted failed work and allocates new logical work for already accepted quality repair, gate evaluation returns `PASS` on the second attempt (route `"pass"`), `gate_attempts_by_phase["wave0"]` is 2, and the topology advances to Wave1 only after pass

#### Scenario: Invalid fixture work cannot advance on fixture pass
- **WHEN** a Wave fixture worker omits its result or returns a conflicting candidate while the fixture sequence value is `pass`
- **THEN** the work-completion rule keeps the phase on a typed repair/blocked path, no invalid accepted ref is created, and the graph does not advance to the next phase

#### Scenario: Targeted evidence always returns through synthesis
- **WHEN** Wave2, HITL2 repair, or readiness routes to targeted evidence
- **THEN** the targeted phase returns to Wave2 synthesis before HITL2 or readiness can be reached again, and a fixture cannot bypass synthesis by routing directly to HITL2

#### Scenario: Every later repair edge remains explicit
- **WHEN** fixture gate definitions produce Wave1 repair, HITL2 revise-view/repair, any readiness repair target, final-delivery self-repair, or final evidence-blocked return to readiness
- **THEN** the normalized topology follows the declared bounded edge and eventually reaches the expected next gate or typed terminal without changing unrelated node implementations

#### Scenario: Fake execution has only bounded fixture side effects
- **WHEN** the complete graph runs under spies for model, web, subagent, and sandbox research tools
- **THEN** every spy remains unused, Wave0/Wave1 write only controller-assigned fixture specs/results/outputs plus the validated submissions ledger and its lock/staging files, and no fetched cache, synthesis, review, final report, or non-fixture research output is created

#### Scenario: Gate verdict drives routing through unchanged _route function
- **WHEN** a gated phase node completes its work-unit drain
- **THEN** the gate evaluates the reducer-previewed current-batch submissions, writes `route` via `route_map` (for example `PhaseVerdict.PASS -> "pass"`), `_route()` reads `state["route"]` exactly as in change 01, and the conditional edge matches the identical route label

#### Scenario: Gate preview does not advance fixture visit indexing
- **WHEN** a Wave node returns current-batch work fields plus its normal phase and execution-trace update
- **THEN** the gate preview includes only allowlisted work fields, `FixtureSequenceRule` selects the same current fixture index as before change 04, and phase/trace/gate-owned fields are applied only by the final graph transition

#### Scenario: Fixture gate rules preserve lifecycle outcomes
- **WHEN** the fake graph runs with fixture gate definitions encoding the same sequences as the prior `fixture_plan`
- **THEN** every top-level phase transition follows the same path and every E2E lifecycle test (happy completion, repair, rerun, stop, cancel, stale-response denial) passes while Wave0/Wave1 exercise validated work-unit submission

#### Scenario: Full-fake HITL1 remains unchanged
- **WHEN** the full-fake graph reaches HITL1
- **THEN** fake HITL1 presents its hardcoded fixture prompt, accepts the matching response once, routes `accepted`, and does not call a model, request-bundle writer, or real-HITL1 follow-up route

#### Scenario: Real HITL1 follow-up does not affect gated phase routing
- **WHEN** real HITL1 routes `needs_followup` or `exhausted`
- **THEN** gate evaluation is not invoked for HITL1, gated phase route ownership remains unchanged, and later Wave/Readiness/Final route labels still come from their gate definitions

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
outside the graph. Pre-suspension, mismatched, empty, synthetic-summary, ToolMessage,
AIMessage, model-provided argument, and already consumed responses SHALL NOT advance the
graph. After checkpoint inspection, an exact match to the checkpointed consumed
request/message pair SHALL be classified before fresh-answer correlation and MAY only
reproject the current durable pending or terminal result without requiring the old
interrupt to remain pending or invoking another node.

The LangGraph checkpoint interrupt task SHALL be the only pending-request authority;
ResearchState SHALL NOT duplicate a mutable pending descriptor. Request ids SHALL
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

For real HITL1, an incomplete answer MAY route `needs_followup` and create a later
HITL1 interrupt with a new ordinal; the consumed response ids for the incomplete answer
SHALL still be recorded before the follow-up route is published. Durable HITL1
profile-progress fields are allowed only as bounded profile data, not as a second
pending request copy.

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

#### Scenario: Incomplete real-HITL1 answer creates a fresh pending request
- **WHEN** real HITL1 consumes a matching incomplete response and routes `needs_followup`
- **THEN** the next suspended checkpoint contains exactly one new HITL1 interrupt with an incremented ordinal, and the consumed response cannot be replayed as the follow-up answer

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
truncated. Gate fatigue escalation or budget exhaustion SHALL produce typed `blocked`
with `terminal_reason=GATE_BLOCKED`; the change-01 `REPAIR_EXHAUSTED` reason SHALL be
retained in the enum but no longer produced (gate-produced `GATE_BLOCKED` replaces it).

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

#### Scenario: Gate-blocked terminal reason replaces fixture exhaustion
- **WHEN** gate fatigue escalation or budget exhaustion produces a `BLOCKED` verdict
- **THEN** `terminal_reason` is `GATE_BLOCKED`, not the change-01 `REPAIR_EXHAUSTED`, and the lifecycle transitions to typed terminal `blocked`

### Requirement: Checkpoints and topology contracts remain durable and deterministic

The fake graph SHALL use a versioned research checkpoint namespace isolated from the
outer lead-agent and infra-probe namespaces. ResearchState SHALL contain only bounded
control fields, artifact refs, branch summaries, HITL correlation, consumed-response
ids, bounded profile progress, bounded topic planning data, and a bounded logical
trace, per REG-006 through REG-008; it SHALL NOT contain raw runtime authority or
large research content. File-backed SQLite SHALL recover a suspended HITL across
provider close and a fresh process. Memory and SQLite memory mode SHALL be labelled
same-process only. A committed normalized topology snapshot SHALL reject unexpected
node/edge or reachability changes. Zero-API E2E coverage SHALL include happy
completion, repair, rerun, stop, cancel, stale-response denial, consumed-response
delivery reprojection, restart resume, the real-HITL1 follow-up restart path, and the
real-topic-planning blocked path.

#### Scenario: SQLite restart resumes the same interrupt
- **WHEN** one process starts a lifecycle to HITL, closes the provider, and a fresh process resumes the same trusted user/thread/research id with a matching HumanMessage
- **THEN** the prior pending interrupt and state are recovered, resume continues from that point, and no outer lead-agent or infra-probe checkpoint is read

#### Scenario: Committed suspension survives result-delivery failure
- **WHEN** the nested HITL checkpoint commits and the action fails before the outer ToolMessage is delivered
- **THEN** retrying start from the same trusted scope and start HumanMessage reopens the same namespace and reprojects the same pending request without rerunning completed nodes

#### Scenario: Unknown skeleton schema fails closed
- **WHEN** status, resume, or cancel reads a research checkpoint whose stored `ResearchState.schema_version` is unsupported
- **THEN** it returns `schema_unsupported` before node execution or checkpoint mutation

#### Scenario: Topology drift is detected
- **WHEN** a logical node, edge, route label, or reachability property changes beyond the declared HITL1 `needs_followup`/`exhausted`, topic_planning `exhausted`, and wave2_synthesis `exhausted` routes without regenerating the approved semantic snapshot
- **THEN** the topology contract fails with the normalized difference

#### Scenario: Memory does not claim restart durability
- **WHEN** the same-process memory host revisits a lifecycle and a fresh-process capability is inspected
- **THEN** same-process actions work on the retained host but status reports restart recovery unsupported and no restart E2E claim is made

#### Scenario: Real HITL1 follow-up survives restart
- **WHEN** real HITL1 commits partial profile progress, routes `needs_followup`, and suspends with a follow-up interrupt before the provider is closed
- **THEN** a fresh process resumes the follow-up using the checkpointed profile progress and the new pending request, without relying on Python closure state

#### Scenario: Real topic planning blocked terminal is durable
- **WHEN** real topic planning fails validation or coverage after its bounded repair and routes `exhausted` with terminal `BLOCKED`
- **THEN** the checkpoint records `terminal_status=BLOCKED` and `terminal_reason=GATE_BLOCKED`, no planner-owned topic state is written, status/cancel return the terminal result idempotently, and resume returns `invalid_transition` because no interrupt is pending

### Requirement: One typed ResearchState is the canonical checkpointed control authority

The downstream package SHALL define one versioned typed `ResearchState` in
`domain/state.py` as the sole checkpointed control authority for a research lifecycle,
replacing the change-01 `SkeletonState` and `SkeletonCheckpoint` payload. `ResearchState`
SHALL organize its fields into `identity`, `request`, `control`, `planning`, `work`,
`quality`, and `delivery` blocks. The `identity` block SHALL carry `research_id`,
`outer_thread_id`, `generation`, and `schema_version`, and identity and scope SHALL come
only from the trusted `RuntimeAdapter` envelope and SHALL NOT be overridable by a node,
worker, or model. The `control` block SHALL carry `phase`, `phase_status`, `waiting_for`,
`terminal_status`, `gate_attempts_by_phase`, and `repair_budget_by_phase`; exactly one
legal `phase` and at most one `waiting_for` condition SHALL hold at any time, and
`phase_status`, `waiting_for`, and `terminal_status` SHALL be distinct control fields. The
`work` block SHALL carry `work_specs_by_id`, `work_status_by_id`, and
`accepted_submission_refs`, where `work_status_by_id` is closed to the `WorkStatus` enum
`pending | running | submitted | failed | timed_out | cancelled`. The fake graph SHALL bind
`StateGraph` to the typed `ResearchState`, the temporary `graph/skeleton_state.py` module
SHALL be removed, and the two schemas SHALL never coexist as authorities. Any future
addition to `ResearchState` SHALL explicitly declare its writer, reader, and reducer.

Real HITL1 SHALL compatibly extend the request/control data by adding the controller
profile fields `profile_ref`, `research_depth`, `target_audience`, `output_format`,
`cost_tolerance`, `time_budget`, `must_answer_questions`, and `degraded_profile`, plus
bounded transient follow-up progress fields `pending_profile` and
`profile_followup_round`. These fields SHALL be declared in `ResearchState`,
`ResearchCheckpoint`, and the ownership table with explicit writer, reader, and reducer
entries. They SHALL NOT create a second pending-interrupt authority, a second phase
cursor, or any raw runtime capability in checkpoint state.

#### Scenario: Typed state replaces the skeleton payload without changing fake paths
- **WHEN** the fake graph runs start, resume, status, and cancel after the builder binds `ResearchState`
- **THEN** every change-01 fake route, interrupt, terminal marker, and restart-resume path behaves identically, the checkpointed payload is `ResearchState`, and no `graph/skeleton_state.py` symbol is imported

#### Scenario: Identity cannot be overridden by a node or worker
- **WHEN** a node or worker attempts to write `research_id`, `outer_thread_id`, `generation`, or `schema_version`
- **THEN** the reducer rejects the write and the trusted identity derived from `RuntimeAdapter` is preserved

#### Scenario: Only one legal phase and waiting state hold at once
- **WHEN** a reducer receives an update that would set a second active phase or a second `waiting_for` condition
- **THEN** it rejects the update and the prior single legal control state is preserved

#### Scenario: Every field declares its writer, reader, and reducer
- **WHEN** the `ResearchState` field set is inspected
- **THEN** each field has a declared writer, reader, and reducer in the ownership table, and a contract test fails if any field lacks one

#### Scenario: HITL1 profile fields are typed checkpoint control data
- **WHEN** real HITL1 accepts a valid profile
- **THEN** the checkpoint contains the profile `ContentRef` and short controller-owned profile fields, and downstream nodes can read the short fields without loading `profile.json`

#### Scenario: HITL1 transient progress is bounded state, not pending authority
- **WHEN** real HITL1 consumes an incomplete answer and routes `needs_followup`
- **THEN** `pending_profile` and `profile_followup_round` are the only HITL1 follow-up progress fields in `ResearchState`, and the pending request descriptor remains solely in the LangGraph interrupt task

### Requirement: State reducers enforce terminal monotonicity, duplicate-hash idempotency, and sole-writer ownership

`ResearchState` SHALL be updated only through declared reducers. A terminal
`work_status` SHALL be monotonic: a later `running` or stale value SHALL NOT downgrade a
terminal status, and at most one terminal winner SHALL hold per work/attempt. The
`generation` field SHALL be monotonic non-decreasing and a reducer SHALL reject any
update that would decrease it. Replaying the same work/attempt with the same content
hash SHALL be idempotent and SHALL NOT append a duplicate or advance phase or
generation; replaying the same work/attempt with a different content hash SHALL be
flagged as a conflict and SHALL NOT be resolved last-write-wins.
`accepted_submission_refs` SHALL be dedupe-append only. `latest_gate_feedback`,
`gate_attempts_by_phase`, and `repair_budget_by_phase` SHALL be writable solely by the
gate node; worker, planner, and repair agents SHALL NOT write gate feedback, gate
attempts or repair budgets, `phase`, or `accepted_submission_refs`.

HITL1 profile fields SHALL be writable only by controller-authorized graph updates. A
worker, planner, repair agent, model output, node-agent result, or runtime capability
SHALL NOT directly mutate `profile_ref`, short profile fields, or transient follow-up
progress. Profile publication SHALL be all-or-nothing from the graph perspective:
`accepted` publishes final fields and clears transient progress; `needs_followup`
publishes only transient progress; `cancel` and `exhausted` leave final profile fields
unset and clear transient progress when present.

#### Scenario: Terminal status cannot be downgraded
- **WHEN** a reducer receives `running` for a work/attempt whose status is already `submitted`, `failed`, `timed_out`, or `cancelled`
- **THEN** the terminal status is preserved and the late update is rejected

#### Scenario: Same-hash replay is idempotent
- **WHEN** the same work/attempt result with the same content hash is reduced twice
- **THEN** the second reduction performs no append and does not advance phase or generation

#### Scenario: Different-hash replay is a conflict
- **WHEN** the same work/attempt is reduced again with a different content hash
- **THEN** the reducer flags `conflict` rather than overwriting, and the original accepted result is preserved

#### Scenario: Generation cannot decrease
- **WHEN** a reducer receives an update that would lower `generation`
- **THEN** it rejects the update and the current `generation` is preserved

#### Scenario: Workers cannot write gated authority
- **WHEN** a worker or repair agent update attempts to set `latest_gate_feedback`, `gate_attempts_by_phase`, `repair_budget_by_phase`, `phase`, or `accepted_submission_refs`
- **THEN** the reducer rejects the write and only the gate node or controller authority is preserved

#### Scenario: Non-controller writers cannot mutate HITL1 profile authority
- **WHEN** a planner, worker, repair agent, or model-derived update attempts to set `profile_ref`, a short profile field, `pending_profile`, or `profile_followup_round`
- **THEN** reducer ownership rejects the update and the prior checkpoint profile authority is preserved

#### Scenario: Final and transient profile updates do not mix
- **WHEN** HITL1 routes `needs_followup`
- **THEN** only bounded transient profile progress is written, and `profile_ref`, final short fields, and `profile.json` remain absent until an accepted final profile exists

### Requirement: Large research content stays out of the checkpoint as bounded content refs

`ResearchState` SHALL NOT store web page bodies, PDFs, full evidence summaries, full
reports, screenshots, large tool output, or full HITL1 profile JSON bodies. Such content
SHALL live only as sandbox artifact files, and `ResearchState` SHALL reference it by at
most a sandbox path, a content hash, a schema version, and a short summary. A hard
checkpoint-size bound SHALL reject any state update whose serialized form exceeds the
bound; semantic content SHALL fail validation rather than be silently truncated. Raw
runtime authority - `TrustedRuntimeEnvelope` fields, AppConfig, model and tool handles,
sandbox handles, file handles, host paths, and credentials - SHALL NOT enter the
checkpoint.

The HITL1 final `ResearchProfile` SHALL be serialized as canonical JSON in
`request/profile.json`; the checkpoint SHALL store only `profile_ref`, short enum/string
fields, bounded `must_answer_questions`, `degraded_profile`, and bounded transient
progress needed to ask follow-ups.

#### Scenario: Oversized content is rejected
- **WHEN** a node returns a state update whose serialized size exceeds the hard checkpoint-size bound
- **THEN** the update is rejected with a typed failure and the checkpoint is not mutated

#### Scenario: Content is referenced, not embedded
- **WHEN** a state update carries large content
- **THEN** the reducer stores only a `ContentRef` (sandbox path, content hash, schema version, short summary) and excludes the raw body from the checkpoint

#### Scenario: Raw runtime authority is rejected
- **WHEN** a state update includes a `TrustedRuntimeEnvelope`, AppConfig, model/tool handle, sandbox handle, or credential field
- **THEN** the reducer rejects the unknown field and the checkpoint is not mutated

#### Scenario: HITL1 profile body is referenced, not embedded
- **WHEN** a complete HITL1 profile includes scope boundaries or custom notes
- **THEN** those full profile values live in `request/profile.json`, while the checkpoint contains only the bounded `ContentRef` and short planning fields

#### Scenario: Runtime authority is rejected from profile state
- **WHEN** a state update tries to carry a request-bundle writer, host path, file handle, AppConfig, model handle, or sandbox handle
- **THEN** checkpoint validation rejects the update and no profile state is mutated

### Requirement: Control, evidence, and content authorities remain distinct

The system SHALL keep three authorities distinct: checkpointed `ResearchState` is the
control truth for phase, interrupt, retry, work status, HITL1 profile progress, final
profile `ContentRef`, and legal transitions; the append-only validated submission ledger
is the evidence truth for which work output, claim, or source has been formally
accepted; and sandbox artifact files are the content truth for request profile data,
page cache, evidence, synthesis, and report. The graph checkpoint SHALL be the sole
legal execution path and the system SHALL NOT maintain a second phase-cursor file.
`accepted_submission_refs` in `ResearchState` SHALL hold references into the submission
ledger, not a duplicate of ledger records; the ledger remains the sole evidence
authority. File existence, worker final text, a tool event, profile file existence, or a
`running` status SHALL NOT count as a validated submission or as phase advancement.

Within the checkpointed work block, `work_specs_by_id` SHALL be keyed by logical work id;
`attempts_by_id` and the compatibility-named `work_status_by_id` SHALL be keyed by
attempt id; and `active_attempt_by_work_id` SHALL identify at most one non-terminal
attempt for each logical work. A retry SHALL append a fresh attempt/status entry without
rewriting terminal history. The accepted-ref set SHALL contain only the sole validated
record hash for a logical work, even when reconciliation discovers that a sibling retry
was active. Compact map values SHALL not repeat identity derivable from their canonical
keys; the active window SHALL be bounded to 32 works, 64 attempts, 32 keyed terminal
failures, 64 accepted hashes, a 40,960-byte work block, and the existing 65,536-byte
whole checkpoint.

The Wave0 and Wave1 full-fake paths introduced by change 04 SHALL exercise this real
authority split with deterministic fixture content: controller state remains in the
checkpoint, fixture result/output bodies remain in the sandbox workspace, and only the
controller submit path writes validated `SubmissionRecord` values and accepted refs.
Those fixture submissions SHALL remain visibly non-research output and SHALL NOT let a
fixture file, staging file, or ledger-ahead crash window bypass reconciliation before a
gate reads coverage.

Real HITL1's request-bundle `profile.json` SHALL be content authority only. It SHALL NOT
be a submission ledger entry, a status file, a phase cursor, or a durable pending-HITL
descriptor. The checkpointed `profile_ref` is the only control link from the graph to
that content artifact.

#### Scenario: No second phase cursor exists
- **WHEN** a lifecycle advances phase, suspends, terminates, retries a work unit, or replays a submission
- **THEN** the checkpointed `ResearchState` is the only control authority and no companion status, queue, or index file is read or written as a phase cursor

#### Scenario: Only reconciled ledger refs count as accepted submissions
- **WHEN** the accepted-submission authority is inspected after fixture worker completion or crash replay
- **THEN** only `accepted_submission_refs` resolving to valid matching ledger records mark accepted submissions, and no file, worker text, tool event, running status, staging file, or unreferenced record counts as coverage

#### Scenario: Profile artifact is not an evidence submission or phase cursor
- **WHEN** `request/profile.json` exists in the bundle
- **THEN** it counts only as request content referenced by `profile_ref`; it does not mark topic planning complete, satisfy evidence coverage, or advance the lifecycle without the checkpoint transition

#### Scenario: No second HITL1 status file exists
- **WHEN** HITL1 suspends, follows up, accepts, cancels, or blocks
- **THEN** the checkpointed `ResearchState` plus LangGraph interrupt task are the only control authorities, and no companion request/profile status file is read as control state

### Requirement: A minimal research bundle layout and path-containment contract scope sandbox writes

The system SHALL define a minimal research bundle rooted at
`workspace/deep-research/<research_id>/` containing `request/`,
`work/<work_id>/<attempt_id>/`, `evidence/`, `synthesis/`, `review/`, `final/`, and
`diagnostics/` subtrees. A worker SHALL write only its own
`<work_id>/<attempt_id>/` directory and controlled cache regions, and writes outside the
assigned research and attempt root SHALL fail closed. The runtime work-unit projection
SHALL derive the worker's virtual attempt root from the trusted research scope plus
controller-assigned work/attempt ids; it SHALL NOT use a caller-selected path or the
phase-level `.../attempts/<id>` root. Canonical source URLs SHALL be deduplicated.
`diagnostics/gate-attempts.jsonl` SHALL be audit-only and SHALL NOT serve as a phase
cursor.

Runtime work-unit capability probes MAY use randomized hidden files only under the
current research `diagnostics/` subtree. They SHALL be temporary operational mechanics,
never control/evidence/content refs, and SHALL be removed with any probe-only empty
directories on every exit path. Prelaunch doctor's host-only filesystem probe is a
deployment diagnostic without a research id and SHALL not call the sandbox.

The request subtree SHALL contain request-owned bootstrap/profile artifacts. Real
bootstrap owns `request/marker.json`; real HITL1 owns exactly `request/profile.json`.
The canonical `profile_path(research_id)` helper SHALL reject malformed research ids and
return `workspace/deep-research/<research_id>/request/profile.json`. A runtime-owned
request-bundle writer SHALL write the profile only under the established current
research `request/` subtree, perform host-side path containment and symlink/path-swap
defense, compute the content hash from canonical JSON bytes, and redact host paths from
errors.

The Wave0 and Wave1 change-04 fixture paths MAY write only this bounded subset:
controller-owned `work-spec.json`, worker-owned `result.json` and declared `outputs/`,
and submit-owned `evidence/submissions.jsonl` plus its non-authoritative lock/staging
files. They SHALL NOT write fetched cache, synthesis, review, final-report, DPT
queue/index/status, or non-fixture research artifacts. Host-side controller I/O SHALL
run only after runtime proves that the trusted host workspace and parent sandbox share
the same physical thread workspace; otherwise it SHALL fail before every write.

#### Scenario: Out-of-containment write is rejected
- **WHEN** the path-containment contract resolves a write path outside the assigned `<work_id>/<attempt_id>/` directory or outside the research root
- **THEN** it rejects the path and no artifact may land outside the contained root

#### Scenario: Diagnostics are not a phase cursor
- **WHEN** `diagnostics/gate-attempts.jsonl` or a submission lock/staging file is written
- **THEN** it is used only for audit or atomic-publication mechanics and the checkpointed `ResearchState` remains the sole phase authority

#### Scenario: Fixture writes remain bounded and role-owned
- **WHEN** a full-fake Wave0 or Wave1 batch completes
- **THEN** controller, worker, and submit code write only their declared bundle files under the canonical roots, and no actor writes another role's artifact or any real research output category

#### Scenario: Profile path is request-scoped and contained
- **WHEN** HITL1 asks for the profile path for a valid research id
- **THEN** the path is exactly `workspace/deep-research/<research_id>/request/profile.json`, is classified as request/content owned, and any malformed id or path escape is rejected before write

#### Scenario: Request-bundle writer rejects cross-research writes
- **WHEN** the runtime writer is bound to research A but receives or derives a profile path for research B or outside the request subtree
- **THEN** it fails closed without writing and without exposing host paths

### Requirement: A versioned ResearchState schema fails closed on incompatible versions

`ResearchState` SHALL carry a `schema_version` field. On read, if the stored
`schema_version` is unsupported or incompatible, the handler SHALL stop and return
`schema_unsupported` before node execution or checkpoint mutation, and SHALL NOT
silently reset, auto-migrate, or reinterpret an incompatible payload. This change SHALL
establish only the version field and the fail-closed contract; business state migration
across versions is explicitly out of scope. The change-01 skeleton schema-version gate
SHALL be preserved in typed form under `ResearchState`.

Real HITL1 SHALL add only backward-compatible version-2 defaulted fields. Existing
version-2 checkpoints that lack HITL1 profile fields SHALL validate with
`profile_ref=None`, empty short profile fields, `must_answer_questions=()`,
`degraded_profile=False`, `pending_profile=None`, and `profile_followup_round=0`.
Because no incompatible interpretation is introduced, `RESEARCH_STATE_SCHEMA_VERSION`
SHALL NOT be bumped by this change.

#### Scenario: Unsupported schema version fails closed
- **WHEN** status, resume, or cancel reads a research checkpoint whose `ResearchState.schema_version` is unsupported
- **THEN** it returns `schema_unsupported` before node execution or checkpoint mutation and does not reset or reinterpret the payload

#### Scenario: No silent migration
- **WHEN** a stored payload carries an incompatible `schema_version`
- **THEN** the handler does not auto-migrate, reinterpret, or silently reset state, and requires an explicit migration path

#### Scenario: Existing version-2 checkpoint defaults HITL1 profile fields
- **WHEN** status, resume, or cancel reads a version-2 checkpoint created before real HITL1 profile fields existed
- **THEN** validation succeeds with the HITL1 profile defaults and does not reset, auto-migrate, or reinterpret any existing field

#### Scenario: Unsupported schema still fails before HITL1 runs
- **WHEN** a stored checkpoint carries an unsupported `schema_version`
- **THEN** the handler returns `schema_unsupported` before constructing HITL1 dependencies, writing `profile.json`, or mutating profile fields
