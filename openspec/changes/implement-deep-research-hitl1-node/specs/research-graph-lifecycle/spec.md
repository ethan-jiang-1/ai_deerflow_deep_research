> req: REG-001, REG-002, REG-003, REG-005, REG-006, REG-007, REG-008, REG-009, REG-010, REG-011

## MODIFIED Requirements

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

Gate evaluation SHALL remain the routing authority for gated phases. HITL1 remains a
non-gated controller node and writes its own route labels directly. The graph's
conditional edges SHALL match the route labels declared in the normalized topology.

#### Scenario: Complete profile bypass is already part of topology
- **WHEN** the bootstrap fixture returns `profile_complete`
- **THEN** the graph routes directly to topic planning without creating HITL1, while the default fixture still routes through fake HITL1 and the topology snapshot remains deterministic

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
interrupt. The wire schemas for `PendingResearchInterrupt`, `HumanInputRequest`,
`AcceptedHumanResponse`, and `InternalCancelDecision` SHALL remain stable. Resume tool
arguments SHALL contain no answer. Resume SHALL select only the latest eligible
post-suspension `HumanMessage` from trusted runtime state, correlate a structured
response to the pending source/request id when present, and supply the accepted request
id, HumanMessage id, exact value, response kind, and optional option id as one typed
`Command(resume=...)` payload.

The resumed HITL node SHALL let LangGraph consume the pending interrupt and SHALL record
consumed request/message ids in the same graph transition. For real HITL1, an
incomplete answer MAY route `needs_followup` and create a later HITL1 interrupt with a
new ordinal; the consumed response ids for the incomplete answer SHALL still be recorded
before the follow-up route is published. Runtime code SHALL NOT patch interrupt tasks
or checkpoint fields outside the graph.

The LangGraph checkpoint interrupt task SHALL be the only pending-request authority;
ResearchState SHALL NOT duplicate a mutable pending descriptor. Durable HITL1
profile-progress fields are allowed only as bounded profile data, not as a second
pending request copy. Request ids SHALL include a deterministic HITL ordinal derived
from prior checkpointed logical HITL visits, so retrying the same interrupt is stable
and a later HITL interrupt in the same generation cannot collide.

#### Scenario: Matching card response resumes once
- **WHEN** the newest eligible HumanMessage carries a non-empty `human_input_response` with source `deep_research` and the pending request id
- **THEN** one typed response envelope resumes that interrupt exactly once, LangGraph consumes the pending interrupt, the HITL node records the response request/message ids and completed logical visit in the same transition, and later replay cannot advance another interrupt

#### Scenario: Incomplete real-HITL1 answer creates a fresh pending request
- **WHEN** real HITL1 consumes a matching incomplete response and routes `needs_followup`
- **THEN** the next suspended checkpoint contains exactly one new HITL1 interrupt with an incremented ordinal, and the consumed response cannot be replayed as the follow-up answer

#### Scenario: Forged or stale response is denied
- **WHEN** an answer appears only in tool arguments, an AI/ToolMessage, a hidden summary, a pre-suspension HumanMessage, a mismatched request id, or a different outer thread
- **THEN** resume returns `response_mismatch` for an in-scope correlation failure or indistinguishable `research_not_found` for another thread, and leaves the checkpoint and pending interrupt unchanged

### Requirement: Checkpoints and topology contracts remain durable and deterministic

The fake graph SHALL use a versioned research checkpoint namespace isolated from the
outer lead-agent and infra-probe namespaces. ResearchState SHALL contain only bounded
control fields, artifact refs, branch summaries, HITL correlation, consumed-response
ids, bounded profile progress, and a bounded logical trace, per REG-006 through
REG-008; it SHALL NOT contain raw runtime authority or large research content.
File-backed SQLite SHALL recover a suspended HITL across provider close and a fresh
process. Memory and SQLite memory mode SHALL be labelled same-process only. A committed
normalized topology snapshot SHALL reject unexpected node/edge or reachability changes.
Zero-API E2E coverage SHALL include happy completion, repair, rerun, stop, cancel,
stale-response denial, consumed-response delivery reprojection, restart resume, and the
real-HITL1 follow-up restart path introduced by this change.

#### Scenario: SQLite restart resumes the same interrupt
- **WHEN** one process starts a lifecycle to HITL, closes the provider, and a fresh process resumes the same trusted user/thread/research id with a matching HumanMessage
- **THEN** the prior pending interrupt and state are recovered, resume continues from that point, and no outer lead-agent or infra-probe checkpoint is read

#### Scenario: Real HITL1 follow-up survives restart
- **WHEN** real HITL1 commits partial profile progress, routes `needs_followup`, and suspends with a follow-up interrupt before the provider is closed
- **THEN** a fresh process resumes the follow-up using the checkpointed profile progress and the new pending request, without relying on Python closure state

#### Scenario: Topology drift is detected
- **WHEN** a logical node, edge, route label, or reachability property changes beyond the declared HITL1 `needs_followup` and `exhausted` routes without regenerating the approved semantic snapshot
- **THEN** the topology contract fails with the normalized difference

### Requirement: One typed ResearchState is the canonical checkpointed control authority

The downstream package SHALL define one versioned typed `ResearchState` in
`domain/state.py` as the sole checkpointed control authority for a research lifecycle.
`ResearchState` SHALL organize its fields into `identity`, `request`, `control`,
`planning`, `work`, `quality`, and `delivery` blocks. The `identity` block SHALL carry
`research_id`, `outer_thread_id`, `generation`, and `schema_version`, and identity and
scope SHALL come only from the trusted `RuntimeAdapter` envelope and SHALL NOT be
overridable by a node, worker, or model. The `control` block SHALL carry `phase`,
`phase_status`, `waiting_for`, `terminal_status`, `gate_attempts_by_phase`, and
`repair_budget_by_phase`; exactly one legal `phase` and at most one `waiting_for`
condition SHALL hold at any time, and `phase_status`, `waiting_for`, and
`terminal_status` SHALL be distinct control fields. The `work` block SHALL carry
`work_specs_by_id`, `work_status_by_id`, and `accepted_submission_refs`, where
`work_status_by_id` is closed to the `WorkStatus` enum
`pending | running | submitted | failed | timed_out | cancelled`.

Real HITL1 SHALL compatibly extend the request/control data by adding the controller
profile fields `profile_ref`, `research_depth`, `target_audience`, `output_format`,
`cost_tolerance`, `time_budget`, `must_answer_questions`, and `degraded_profile`, plus
bounded transient follow-up progress fields `pending_profile` and
`profile_followup_round`. These fields SHALL be declared in `ResearchState`,
`ResearchCheckpoint`, and the ownership table with explicit writer, reader, and reducer
entries. They SHALL NOT create a second pending-interrupt authority, a second phase
cursor, or any raw runtime capability in checkpoint state.

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

Real HITL1's request-bundle `profile.json` SHALL be content authority only. It SHALL NOT
be a submission ledger entry, a status file, a phase cursor, or a durable pending-HITL
descriptor. The checkpointed `profile_ref` is the only control link from the graph to
that content artifact.

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
silently reset, auto-migrate, or reinterpret an incompatible payload. Business state
migration across versions is explicitly out of scope.

Real HITL1 SHALL add only backward-compatible version-2 defaulted fields. Existing
version-2 checkpoints that lack HITL1 profile fields SHALL validate with
`profile_ref=None`, empty short profile fields, `must_answer_questions=()`,
`degraded_profile=False`, `pending_profile=None`, and `profile_followup_round=0`.
Because no incompatible interpretation is introduced, `RESEARCH_STATE_SCHEMA_VERSION`
SHALL NOT be bumped by this change.

#### Scenario: Existing version-2 checkpoint defaults HITL1 profile fields
- **WHEN** status, resume, or cancel reads a version-2 checkpoint created before real HITL1 profile fields existed
- **THEN** validation succeeds with the HITL1 profile defaults and does not reset, auto-migrate, or reinterpret any existing field

#### Scenario: Unsupported schema still fails before HITL1 runs
- **WHEN** a stored checkpoint carries an unsupported `schema_version`
- **THEN** the handler returns `schema_unsupported` before constructing HITL1 dependencies, writing `profile.json`, or mutating profile fields
