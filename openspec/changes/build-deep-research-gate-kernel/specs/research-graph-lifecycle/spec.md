# research-graph-lifecycle Delta Specification

> req: REG-002, REG-004

## MODIFIED Requirements

### Requirement: Deterministic fakes exercise routing and parallel fan-in

Every change-01 node implementation SHALL be deterministic and fixture-driven. No fake
SHALL call a model, network API, MCP server, ACP agent, DeerFlow `task` subagent, or
sandbox research tool. Wave0 and Wave1 SHALL each execute a phase-local three-branch
LangGraph `Send` fan-out and reducer-based fan-in, normalize branch ordering, and
return one typed phase result. Typed routers SHALL support pass, bounded repair,
targeted-evidence convergence, all five HITL2 decisions
(`proceed | revise_view | repair | rerun | stop`), typed readiness repair targets,
bounded final-delivery self-repair/evidence-blocked return, and completion without
reading free-form model text. The validated fixture plan SHALL come from handler/test
construction rather than public tool arguments and SHALL be persisted as closed data
needed for deterministic resume. Bootstrap SHALL expose both `needs_input -> hitl1`
and `profile_complete -> topic_planning`; the default fake path SHALL still exercise
HITL1.

Gate evaluation SHALL replace the change-01 direct fixture-outcome switch. Every gated
phase node SHALL have a registered `GateDefinition` containing a
`FixtureSequenceRule` (fake graph) or real rules (later changes). After the phase node
returns its work result, the node wrapper SHALL invoke `evaluate_gate()` which runs
all rules, collects failures, and produces a typed `PhaseVerdict`. The gate's
`route_map` SHALL translate the verdict to the route string written to
`state["route"]`. The existing `_route()` function SHALL read `state["route"]`
unchanged. The graph's conditional edges SHALL continue to match on the same route
labels as change 01.

The `choose_fixture()` and `bounded_repair_update()` helpers in
`engine/fake_control.py` SHALL be removed; fixture sequence indexing moves into
`FixtureSequenceRule`, and attempt/budget tracking moves into the gate kernel. The
`repair_counts` state field SHALL be frozen (no longer written, superseded by
`gate_attempts_by_phase`). The topology snapshot SHALL be regenerated and SHALL remain
identical in node/edge structure; every route label SHALL match change 01 exactly.

#### Scenario: Three branches join deterministically
- **WHEN** a Wave fake runs with three branch fixtures completing in any scheduler order
- **THEN** all three unique results are reduced exactly once, normalized into stable order, and the parent phase advances only after fan-in

#### Scenario: Complete profile bypass is already part of topology
- **WHEN** the bootstrap fixture returns `profile_complete`
- **THEN** the graph routes directly to topic planning without creating HITL1, while the default fixture still routes through HITL1 and the topology snapshot remains unchanged

#### Scenario: Wave0 repair is bounded
- **WHEN** the Wave0 fixture gate definition sequences `repair` then `pass`
- **THEN** gate evaluation returns `REPAIR` on the first attempt (route `"repair"`), the repair agent runs, gate evaluation returns `PASS` on the second attempt (route `"pass"`), `gate_attempts_by_phase["wave0"]` is 2, and the topology advances to Wave1 only after pass

#### Scenario: Targeted evidence always returns through synthesis
- **WHEN** Wave2, HITL2 repair, or readiness routes to targeted evidence
- **THEN** the targeted phase returns to Wave2 synthesis before HITL2 or readiness can be reached again, and a fixture cannot bypass synthesis by routing directly to HITL2

#### Scenario: Every later repair edge remains explicit
- **WHEN** fixture gate definitions produce Wave1 repair, HITL2 revise-view/repair, any readiness repair target, final-delivery self-repair, or final evidence-blocked return to readiness
- **THEN** the normalized topology follows the declared bounded edge and eventually reaches the expected next gate or typed terminal without changing node implementations

#### Scenario: Fake execution has no external side effect
- **WHEN** the complete graph runs under spies for model, web, subagent, and sandbox research tools
- **THEN** every spy remains unused and no evidence, cache, ledger, report, or research output file is created

#### Scenario: Gate verdict drives routing through unchanged _route function
- **WHEN** a gated phase node completes
- **THEN** the gate writes `route` via `route_map` (e.g. `PhaseVerdict.PASS → "pass"`), `_route()` reads `state["route"]` exactly as in change 01, and the conditional edge matches the identical route label

#### Scenario: Fixture gate rules produce identical outcomes to old fixture plan
- **WHEN** the fake graph runs with fixture gate definitions encoding the same sequences as the change-01 `fixture_plan`
- **THEN** every phase transition follows the same path as the change-01 fake graph, and every E2E test (happy completion, repair, rerun, stop, cancel, stale-response denial) passes identically

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
