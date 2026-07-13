# gate-kernel Specification

> req: GAK-001, GAK-002, GAK-003, GAK-004, GAK-005, GAK-006

## Purpose
The shared deterministic gate evaluation engine, closed failure-code registry,
sole-writer phase-transition authority, bounded repair loop with fatigue
escalation, and fixture-rule adapter that every Deep Research phase consumes
without owning its own transition authority.

## ADDED Requirements

### Requirement: Gate definitions collect all rules and produce deterministic verdicts

The system SHALL define `GateDefinition` as a named collection of `GateRule`
instances registered for a specific phase. `GateRule` SHALL carry a rule name, a
synchronous evaluation function `(ResearchState) -> Failure | None`, and a
`failure_code` (the code this rule is registered to produce; the actual code on a
returned `Failure` MAY differ when the rule discriminates among multiple outcomes).
Rules are pure (no I/O, no model calls), so they are synchronous. `Failure` SHALL
carry the `FailureCode`, its classification (`hard | semantic | repairable |
degradable`), the rule name, a human-readable description, and an optional `ref:
str | None` (a work/attempt id or sandbox path identifying the failing artifact).
`GateResult` SHALL contain the `phase: str` that was evaluated, the typed
`PhaseVerdict`, a stable-ordered list of every `Failure`, an `inspect` summary
string (≤ 512 chars), an `advice` string for the repair agent (≤ 2048 chars),
`failed_refs` (collected from all non-None `Failure.ref` values), a `degraded:
bool` flag, the current `attempt` count for this phase
(`(gate_attempts_by_phase[phase] or 0) + 1` — the post-increment count),
`remaining_budget` (after decrement on REPAIR, or initial default on first
evaluation), `new_generation: int | None` (set to `state["generation"] + 1` on
PASS/BLOCKED, `None` on REPAIR), the failure fingerprint tuple, and a
`consecutive` counter for fatigue tracking. `GateDefinition` SHALL carry a
`route_map: dict[PhaseVerdict, str]` (or a `route_resolver` callable for phases
with multiple repair targets) and a `default_budget: int` for lazy budget
initialization.

The evaluate function SHALL run every registered rule, collect all failures in
registration order, and derive the verdict as: `blocked` if any hard failure exists
or the budget is exhausted for repairable failures; `repair` if only
repairable/semantic failures exist and budget remains; `pass` otherwise (including
when only degradable failures exist, which SHALL set `degraded=True` on the
`GateResult`). `PhaseVerdict.NEEDS_HUMAN` is reserved for future use — no
`FailureCode` classification produces it in this change, and no fixture rule
triggers it. The `route_map` (or `route_resolver`) SHALL translate the verdict to
the route string written to `state["route"]`; a `degraded_pass` SHALL map to the
same route label as `pass`.

#### Scenario: All rules pass produces pass verdict
- **WHEN** `evaluate_gate` runs all rules and none returns a Failure
- **THEN** `GateResult.verdict` is `PhaseVerdict.PASS`, `failures` is empty, and `inspect` summarizes no issues

#### Scenario: Single repairable failure with budget produces repair verdict
- **WHEN** one rule returns a repairable `Failure` and `remaining_budget` is at least 1
- **THEN** `GateResult.verdict` is `PhaseVerdict.REPAIR`, `failures` contains that one failure, and `advice` describes the failure for the repair agent

#### Scenario: Hard failure produces blocked verdict regardless of budget
- **WHEN** one rule returns a hard `Failure` even when budget remains
- **THEN** `GateResult.verdict` is `PhaseVerdict.BLOCKED`, no repair is attempted, and `advice` states the hard failure cannot be repaired

#### Scenario: Budget exhaustion with repairable failures escalates to blocked
- **WHEN** repairable failures exist but `remaining_budget` is 0
- **THEN** `GateResult.verdict` is `PhaseVerdict.BLOCKED` with `REPAIR_BUDGET_EXHAUSTED` in the failure list

#### Scenario: Degradable-only failures produce degraded pass
- **WHEN** all failures are classified `degradable` and no hard, semantic, or repairable failures exist
- **THEN** `GateResult.verdict` is `PhaseVerdict.PASS` with `degraded=True`, and routing uses the same route label as a clean pass

#### Scenario: Multiple repairable failures produce repair with combined fingerprint
- **WHEN** rule A and rule B both return repairable `Failure` values with different codes
- **THEN** `GateResult.verdict` is `PhaseVerdict.REPAIR`, `failures` lists both in registration order, `failed_refs` collects refs from both, and the fingerprint is `((code_A, rule_A), (code_B, rule_B))`

#### Scenario: Collect-all runs every rule even after a hard failure
- **WHEN** rule 1 returns a hard failure and rule 2 returns a repairable failure
- **THEN** both failures appear in `GateResult.failures` in registration order, and the verdict is `PhaseVerdict.BLOCKED`

#### Scenario: Route map translates verdict to topology edge label
- **WHEN** the gate produces `PhaseVerdict.BLOCKED` for wave0 with `route_map[BLOCKED] = "exhausted"`
- **THEN** the state update writes `route = "exhausted"`, matching the topology edge `TopologyEdge("wave0", "exhausted", "blocked")`

#### Scenario: Route map key missing for reachable verdict fails construction
- **WHEN** a `GateDefinition` is constructed with a `route_map` that is missing a key for a reachable verdict (one that the registered rules could produce)
- **THEN** construction fails with a typed error before any gate evaluation

#### Scenario: Route map value not in topology edge labels fails construction
- **WHEN** a `GateDefinition` is constructed with a `route_map` whose value is not a known topology route label (e.g. `"unknown_edge"`)
- **THEN** construction fails with a typed error before any gate evaluation

#### Scenario: Needs-human verdict is reserved
- **WHEN** the `PhaseVerdict` enum is inspected
- **THEN** `NEEDS_HUMAN` is defined but no `FailureCode` classification produces it, and no fixture rule in change 03 triggers it; it is reserved for future quality/critic phases

### Requirement: Failure codes are a closed typed registry

The system SHALL define failure codes as a closed `StrEnum` (`FailureCode`) with
stable values. Each code SHALL carry a fixed classification (`hard | semantic |
repairable | degradable`) resolved through a module-level classification map.
Models, workers, and repair agents SHALL NOT emit new or free-form failure codes.
Phase gate definitions SHALL register only codes from the closed enum. The code set
SHALL initially include at minimum: `MISSING_WORK_SPEC`, `WORK_TIMED_OUT`,
`WORK_FAILED`, `WORK_CANCELLED`, `BUDGET_EXHAUSTED`, `INVALID_OUTPUT_SCHEMA`,
`CONTENT_HASH_MISMATCH`, `MISSING_EVIDENCE`, `UNTRUSTED_SOURCE`,
`IDENTITY_MISMATCH`, `SCHEMA_VERSION_UNSUPPORTED`, `REPAIR_BUDGET_EXHAUSTED`,
`FATIGUE_ESCALATION`, `DEGRADED_EVIDENCE_QUALITY`, `INCOMPLETE_TOPIC_COVERAGE`,
`REPAIR_TARGETED`, `REPAIR_SYNTHESIS`, `REPAIR_HITL2`, `EVIDENCE_INSUFFICIENT`.

#### Scenario: Unknown failure code is rejected at rule registration
- **WHEN** a gate definition attempts to register a rule referencing a value not in `FailureCode`
- **THEN** registration fails with a typed error before any gate evaluation

#### Scenario: Worker cannot emit a failure code
- **WHEN** a worker agent or repair agent returns a result containing a free-form failure code string
- **THEN** the gate ignores it as a gate decision and the code is not added to `GateResult.failures`

#### Scenario: Every code has a stable classification
- **WHEN** the `FailureCode` enum is inspected
- **THEN** each member resolves to an explicit classification in `{hard, semantic, repairable, degradable}` via the classification map

### Requirement: Gate is the sole writer of phase transition routing and feedback

The gate kernel SHALL be the only code path that writes `latest_gate_feedback`,
`gate_attempts_by_phase`, `repair_budget_by_phase`, and the `route` field for gated
phases. The gate SHALL write these fields through the existing reducer
`apply_research_update` with `writer=WriterRole.GATE`, which accepts gate-authored
updates (REG-007). Worker agents, repair agents, planners, and HITL nodes SHALL NOT
write gate fields or `accepted_submission_refs`. Phase nodes SHALL NOT write `route`
for gated phases — the gate writes `route` via the `route_map` translation.

The gate SHALL increment `gate_attempts_by_phase` for the current phase on every
evaluation, set `new_generation` to `state["generation"] + 1` only on `pass` or
`blocked` verdicts, and decrement `repair_budget_by_phase` for the current phase
only on `repair` verdicts. Budget SHALL be lazily initialized: when
`repair_budget_by_phase[phase]` is absent on first evaluation, the gate SHALL use
`GateDefinition.default_budget` as the starting value. The current `phase` field
SHALL continue to be written by each phase node when it runs (recording which phase
last executed), not by the gate. Phase nodes SHALL NOT write `generation` — only
the gate and the non-gated rerun node may increment it.

#### Scenario: Gate writes are accepted by reducers
- **WHEN** the gate kernel writes `latest_gate_feedback`, `gate_attempts_by_phase`, and `route` with `writer=WriterRole.GATE`
- **THEN** `apply_research_update` accepts the write and the checkpoint reflects the new values

#### Scenario: Worker write to gate field is rejected
- **WHEN** a worker agent attempts to set `latest_gate_feedback`, `gate_attempts_by_phase`, `repair_budget_by_phase`, or `route`
- **THEN** `apply_research_update` rejects the write and the prior gate-authored value is preserved

#### Scenario: Generation is not incremented on repair
- **WHEN** the gate returns `PhaseVerdict.REPAIR`
- **THEN** `generation` is not incremented; only `gate_attempts_by_phase` and `repair_budget_by_phase` are updated

#### Scenario: Pass verdict writes pass route and increments generation
- **WHEN** the gate returns `PhaseVerdict.PASS`
- **THEN** `route` is set to the mapped pass label and `generation` is incremented

#### Scenario: Budget is lazily initialized on first gate evaluation
- **WHEN** `evaluate_gate` runs for a phase whose `repair_budget_by_phase[phase]` is absent
- **THEN** the gate uses `GateDefinition.default_budget` as the starting budget for that phase

#### Scenario: Non-gated nodes still write route directly
- **WHEN** bootstrap, hitl1, or hitl2 runs (no GateDefinition registered)
- **THEN** the node writes `route` directly with `writer=WriterRole.CONTROLLER` and the gate is not invoked

### Requirement: Bounded repair loop with fatigue escalation

The repair loop SHALL be driven by the graph topology: when the gate returns
`PhaseVerdict.REPAIR`, the `route_map` SHALL produce the repair route label, and
the conditional edge SHALL route to the repair target (which may be the same phase
for self-repair, or a different node). The repair target node on re-entry SHALL
read `latest_gate_feedback` to obtain the structured `inspect` and `advice` for the
repair agent. After the repair agent completes, the gate SHALL evaluate again.

The gate SHALL track the failure fingerprint (stable-ordered tuple of
`(failure_code, rule_name)` for all failures in a single evaluation) and store it
in `GateResult.fingerprint`. `GateResult.consecutive` SHALL count how many
consecutive evaluations of the **same phase** produced the same fingerprint: the
gate SHALL read the previous `GateResult` from `latest_gate_feedback`; if
`previous.phase == current_phase` and the previous fingerprint matches the current
one, `consecutive = previous.consecutive + 1`; otherwise `consecutive = 1`. If
`consecutive >= 3`, the gate SHALL escalate to `PhaseVerdict.BLOCKED` with
`FATIGUE_ESCALATION` regardless of remaining budget. No new state fields are
required — `latest_gate_feedback` stores the serialized `GateResult` including the
phase, fingerprint, and consecutive count.

The default repair budget SHALL be 3 per phase; `final_delivery` self-repair SHALL
default to 1. Maximum budget SHALL be 10 per phase.

#### Scenario: Successful repair after one retry
- **WHEN** the first gate evaluation returns `REPAIR`, the repair agent runs, and the second gate evaluation returns `PASS`
- **THEN** the phase advances with `gate_attempts_by_phase[phase] == 2` and `repair_budget_by_phase[phase]` decremented by 1

#### Scenario: Budget exhaustion blocks the phase
- **WHEN** the gate returns `REPAIR` for the same phase until `remaining_budget` reaches 0
- **THEN** the next evaluation returns `BLOCKED` with `REPAIR_BUDGET_EXHAUSTED` and the phase does not advance

#### Scenario: Fatigue escalation blocks despite remaining budget
- **WHEN** the same failure fingerprint appears for 3 consecutive gate evaluations on the same phase, even with budget remaining
- **THEN** the gate returns `BLOCKED` with `FATIGUE_ESCALATION` and the failure list includes the stable fingerprint

#### Scenario: Different fingerprint resets fatigue counter
- **WHEN** a repair attempt produces a different failure fingerprint from the previous attempt
- **THEN** the fatigue counter resets to 1 for the new fingerprint and budget continues to decrement normally

#### Scenario: First evaluation starts consecutive at 1
- **WHEN** `evaluate_gate` runs for the first time on a phase and `latest_gate_feedback` is `None` or its `phase` field differs from the current phase
- **THEN** `GateResult.consecutive` is 1 regardless of the failure fingerprint

#### Scenario: Different phase feedback does not affect fatigue
- **WHEN** wave0 gate evaluation stores its `GateResult` (phase="wave0") in `latest_gate_feedback`, then wave1 gate evaluates for the first time
- **THEN** wave1 gate sees `previous.phase == "wave0" != "wave1"`, resets `consecutive = 1`, and does not compare fingerprints across phases

#### Scenario: Repair agent receives full gate feedback
- **WHEN** the repair target node re-enters after a `REPAIR` verdict
- **THEN** the repair agent's context includes `GateResult.inspect`, `GateResult.advice`, and `GateResult.failed_refs` from the most recent evaluation

### Requirement: Fixture rules preserve all fake graph paths

The system SHALL provide `FixtureSequenceRule` as a `GateRule` subclass that reads
the change-01 `fixture_plan` and produces deterministic outcomes. For a given
phase, the rule SHALL index into `fixture_plan[phase]` using
`completed_visits(state, phase)` and return `None` (pass) when the fixture value is
the phase's pass-equivalent, or a `Failure` with `classification=repairable` when
the fixture value is a non-pass outcome. Each phase's `GateDefinition` SHALL
contain this single fixture rule and a `route_map` that translates the resulting
verdict to the identical route label the change-01 fixture would have produced.

The `choose_fixture()` and `bounded_repair_update()` helpers in
`engine/fake_control.py` SHALL be removed. The gate's own budget tracking and
fatigue detection SHALL replace `bounded_repair_update`'s attempt counting and
exhaustion logic. The topology snapshot SHALL be regenerated and SHALL remain
identical in node/edge structure.

#### Scenario: Fixture pass routes identically to old fixture pass
- **WHEN** the fake graph runs with fixture gate rules producing `PASS`
- **THEN** the graph follows the same `pass` conditional edge as the change-01 fixture did

#### Scenario: Fixture repair loop exercises gate evaluation
- **WHEN** a fixture gate definition's `route_map` maps `REPAIR → "repair"` for wave0
- **THEN** the gate evaluates twice (first `REPAIR`, second `PASS`), `gate_attempts_by_phase["wave0"]` is 2, and the phase advances after the second evaluation

#### Scenario: Fixture exhausted matches gate blocked
- **WHEN** a fixture gate definition sequences `repair` for a phase whose default budget is 3
- **THEN** after 3 repairs the gate returns `BLOCKED`, `route_map[BLOCKED]` produces `"exhausted"`, matching the old `exhausted` route

#### Scenario: Topology snapshot unchanged
- **WHEN** the topology snapshot is regenerated after gate kernel integration
- **THEN** every node, edge, and route label matches the change-01 snapshot exactly

### Requirement: Rule evaluation is stable-ordered and deterministic

Rule evaluation SHALL be stable: rules SHALL execute in the order they are
registered in the `GateDefinition`, and the same `ResearchState` input SHALL
produce the same `GateResult` (identical verdict, identical failure list order,
identical failure fingerprint). Rule evaluation SHALL be pure: it SHALL NOT perform
I/O, call a model, mutate state, or access external services. The failure
fingerprint SHALL be the tuple `((failure_code_1, rule_name_1), ...)` in
registration order, used for fatigue detection.

#### Scenario: Same input produces same output
- **WHEN** `evaluate_gate` is called twice with identical `ResearchState` and the same `GateDefinition`
- **THEN** both `GateResult` values are equal, including verdict, failure list order, and fingerprint

#### Scenario: Rule order determines failure list order
- **WHEN** rule A (registered first) and rule B (registered second) both produce failures
- **THEN** `GateResult.failures` lists rule A's failure first and rule B's failure second

#### Scenario: Rule evaluation does not mutate state
- **WHEN** `evaluate_gate` runs with a `ResearchState` snapshot
- **THEN** the snapshot is unchanged after evaluation

#### Scenario: Rule evaluation has no side effects
- **WHEN** `evaluate_gate` runs under spies for filesystem, network, model, and subprocess access
- **THEN** every spy remains unused
