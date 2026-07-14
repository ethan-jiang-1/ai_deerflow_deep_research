> req: REG-002, REG-009, REG-010

## MODIFIED Requirements

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
repair targets, bounded final-delivery self-repair/evidence-blocked return, and
completion without reading free-form model text. The validated fixture plan SHALL come
from handler/test construction rather than public tool arguments and SHALL be persisted
as closed data needed for deterministic resume. Bootstrap SHALL expose both
`needs_input -> hitl1` and `profile_complete -> topic_planning`; the default fake path
SHALL still exercise HITL1.

Gate evaluation SHALL remain the routing authority. Every gated phase node SHALL have a
registered `GateDefinition` containing a `FixtureSequenceRule` (fake graph) or real
rules (later changes). Wave0 and Wave1 SHALL prepend the shared deterministic
work-completion rule so fixture `pass` cannot override failed or unaccepted work. After
the phase-local component reports structural drain, the
node wrapper SHALL apply a pure reducer preview of the node's work/status/accepted-ref
update to the input state and invoke `evaluate_gate()` against that post-work view, not
the stale pre-node state. The preview SHALL use the same reducers and ownership checks as
checkpoint application for an explicit allowlist of gate-readable work fields. It SHALL
exclude `phase`, `route`, `execution_trace`, fixture visit counters, and every gate-owned
field so fixture sequence indexing and sole-writer authority do not advance early. The
preview SHALL perform no I/O or checkpoint mutation. Gate evaluation
then runs all rules, collects failures, and produces a typed `PhaseVerdict`. The gate's
`route_map` SHALL translate the verdict to the route string written to
`state["route"]`. The existing `_route()` function SHALL read `state["route"]`
unchanged. The graph's conditional edges SHALL continue to match the same route labels
as change 01.

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
- **THEN** the graph routes directly to topic planning without creating HITL1, while the default fixture still routes through HITL1 and the topology snapshot remains unchanged

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

### Requirement: Control, evidence, and content authorities remain distinct

The system SHALL keep three authorities distinct: checkpointed `ResearchState` is the
control truth for phase, interrupt, retry, work status, and legal transitions; the
append-only validated submission ledger is the evidence truth for which work output,
claim, or source has been formally accepted; and sandbox artifact files are the content
truth for page cache, evidence, synthesis, and report. The graph checkpoint SHALL be the
sole legal execution path and the system SHALL NOT maintain a second phase-cursor file.
`accepted_submission_refs` in `ResearchState` SHALL hold references into the submission
ledger, not a duplicate of ledger records; the ledger remains the sole evidence
authority. File existence, worker final text, a tool event, or a `running` status SHALL
NOT count as a validated submission.

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

#### Scenario: No second phase cursor exists
- **WHEN** a lifecycle advances phase, suspends, terminates, retries a work unit, or replays a submission
- **THEN** the checkpointed `ResearchState` is the only control authority and no companion status, queue, or index file is read or written as a phase cursor

#### Scenario: Only reconciled ledger refs count as accepted submissions
- **WHEN** the accepted-submission authority is inspected after fixture worker completion or crash replay
- **THEN** only `accepted_submission_refs` resolving to valid matching ledger records mark accepted submissions, and no file, worker text, tool event, running status, staging file, or unreferenced record counts as coverage

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
