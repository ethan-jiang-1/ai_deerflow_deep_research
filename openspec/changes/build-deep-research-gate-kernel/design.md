## Context

Change 01's fake graph uses a `route` string in state updates to drive conditional
edges. The `choose_fixture()` and `bounded_repair_update()` helpers in
`engine/fake_control.py` provide deterministic outcome selection and a basic retry
counter. This works for the skeleton but is not a gate: there is no rule collection,
no failure classification, no inspect/advice projection, and no shared repair loop.
The topology's conditional edges already encode the full verdict space, so the
routing infrastructure is ready — only the evaluation kernel is missing.

Change 02 defined the state slots (`latest_gate_feedback`, `gate_attempts_by_phase`,
`repair_budget_by_phase`) with sole-writer reducers, and the `WriterRole.GATE` enum
value already exists in `domain/state.py`. This change fills those slots with a real
gate evaluation engine and replaces the ad-hoc `route` selection with typed
`GateResult` verdicts while keeping the `_route()` function and topology unchanged.

The gate kernel is purely deterministic Python — no model, no agent loop, no I/O.
Its only job is to run every registered rule, collect failures, classify them, and
emit a typed verdict. Rule evaluation functions are synchronous (`(ResearchState) ->
Failure | None`) — the gate's purity constraint forbids I/O, so there is no reason
for async rules. The repair agent (which IS model-driven, but uses
`ReplayChatModel` or `FakeToolCallingModel` in tests) receives the gate's
structured feedback but does not participate in the gate decision.

`inspect` and `advice` strings on `GateResult` are template-generated from the
failure list. `inspect` is a one-line summary (e.g. "2 failures: missing work spec
for work_1, budget exhausted"), bounded to 512 chars. `advice` is a short directive
for the repair agent (e.g. "Define a work spec for work_1 before re-running the
phase"), bounded to 2048 chars. Real phases may override with rule-specific advice;
the fake graph uses code-to-string templates.

Each `Failure` carries an optional `ref: str | None` (a work/attempt id or sandbox
path). The gate collects all non-None refs across all failures into
`GateResult.failed_refs`. This lets the repair agent know which specific work units
or artifacts need attention.

## Goals / Non-Goals

**Goals:**
- Define `GateDefinition`, `GateRule`, `Failure`, `GateResult`, `PhaseVerdict`, and
  `FailureCode` as the shared gate domain types.
- Implement deterministic collect-all rule evaluation with stable failure
  fingerprint ordering.
- Classify every failure as `hard | semantic | repairable | degradable`; provenance,
  schema, and identity rules are never degradable-pass.
- Gate kernel is the sole writer of `latest_gate_feedback`,
  `gate_attempts_by_phase`, `repair_budget_by_phase`, and `route`; phase nodes and
  workers SHALL NOT write these fields.
- Implement a bounded repair loop: project full `GateResult` feedback into the
  repair agent's context, re-enter the same gate, escalate to `blocked` on budget
  exhaustion or fatigue.
- Replace the skeleton's direct fixture-outcome switch with fixture `GateRule`
  instances producing identical routing outcomes; the topology snapshot is unchanged.
- Stable failure codes in a closed registry — no free-form strings from models or
  workers.

**Non-Goals:**
- No real phase-specific gate rules (Wave0/Wave1/Wave2/readiness) — those arrive
  with their owning changes 08/10/11/15.
- No LLM critic as hard gate authority — the gate kernel is deterministic;
  model-based critique is a semantic rule registered by a phase, not a gate bypass.
- No submission-ledger integration — the gate validates work status and phase
  completion, not evidence quality (that is the evidence critic, change 09).
- No files under `backend/` or `frontend/` are modified.

## Decisions

### Decision 1: Gate evaluation as a pure function invoked from the node wrapper

The gate kernel is a pure synchronous function `evaluate_gate(state, phase,
gate_def) -> GateResult`. Rules are sync (no I/O), so the gate is sync. It is
invoked from the graph's `_node_wrapper` after each phase agent completes, when a
`GateDefinition` is registered for that phase. It is NOT a separate LangGraph node
in the topology.

The `_node_wrapper` closure already captures `logical_name`. After the phase node
returns its work result, the wrapper checks whether a `GateDefinition` exists for
`logical_name`. If yes, it calls `evaluate_gate()` and then converts the
`GateResult` to a state update dict via `gate_result_to_state_update()`. This dict
is merged with the node's return value (gate keys after node keys, so gate-owned
fields win on conflict). If no gate definition exists (bootstrap, hitl1, hitl2,
rerun), the node writes `route` directly as before. The existing `_route()`
function — `state.get("route")` — is unchanged.

`evaluate_gate` receives `state` and can read `state["generation"]`, so it computes the
new generation value during evaluation and stores it in `GateResult.new_generation:
int | None` (set to `state["generation"] + 1` on PASS/BLOCKED, `None` on REPAIR).
`GateResult.attempt` is `(gate_attempts_by_phase[phase] or 0) + 1` — the
post-increment count for this evaluation. `GateResult.remaining_budget` is the
budget AFTER decrement (or the initial default on first evaluation).

`GateResult` is a plain dataclass with `model_dump(mode="json")` or equivalent
JSON-serializable form so it can be stored in `latest_gate_feedback` (an `Any` field
on `ResearchState` that undergoes LangGraph's JSON checkpoint serialization).

The `gate_result_to_state_update(gate_result, phase, state)` function reads current
`gate_attempts_by_phase` and `repair_budget_by_phase` from `state`, updates the
current phase's entry, and writes back the **full dict** (not just the current
phase's key). This is required because `ResearchState` defines these fields as plain
`dict[str, int]` without `Annotated` reducers — LangGraph's default `LastValue`
channel replaces the entire dict on each write rather than shallow-merging.

```python
{
    "route": <str from route_map/resolver>,
    "latest_gate_feedback": <GateResult as JSON-serializable dict>,
    "gate_attempts_by_phase": {**current, phase: gate_result.attempt},
    "repair_budget_by_phase": {**current, phase: gate_result.remaining_budget},
    # Only if gate_result.new_generation is not None:
    "generation": gate_result.new_generation,
    # Only on BLOCKED:
    "terminal_reason": "gate_blocked",
    "terminal_status": "blocked",
    "phase_status": "terminal",
}
```
All keys are already defined in `ResearchState` (change 02). Phase nodes SHALL NOT
write `generation` — only the gate and the rerun node (non-gated) may increment it.

**Rationale:** The topology has 11 nodes with distinct conditional edges. Inserting
a separate gate node would require restructuring from `phase → route` to `phase →
gate → route`, doubling the edge count and breaking the topology snapshot. The plan
explicitly says "保留全图路径" and "graph topology 不因 gate kernel 引入隐藏
transition." The wrapper approach enforces sole-writer through the existing reducers
(`apply_research_update` with `WriterRole.GATE`) — REG-007 already rejects worker
writes to gate fields.

### Decision 2: PhaseVerdict → route string via per-phase route_map

The gate produces a typed `PhaseVerdict` (`pass | repair | blocked | needs_human`).
Each `GateDefinition` carries a `route_map: dict[PhaseVerdict, str]` that translates
the verdict to the concrete route label the topology's conditional edges expect.
Examples:

| Phase | Verdict | Route |
|-------|---------|-------|
| wave0, wave1 | `PASS` | `"pass"` |
| wave0, wave1 | `REPAIR` | `"repair"` |
| wave0, wave1 | `BLOCKED` | `"exhausted"` |
| wave2_synthesis | `PASS` | `"pass"` |
| wave2_synthesis | `REPAIR` | `"evidence_needed"` |
| readiness | `REPAIR` | `"repair_targeted"` / `"repair_synthesis"` / `"repair_hitl2"` |
| readiness | `BLOCKED` | `"exhausted"` |
| final_delivery | `PASS` | `"pass"` |
| final_delivery | `REPAIR` | `"repair"` / `"evidence_blocked"` |
| final_delivery | `BLOCKED` | `"exhausted"` |

Phases with a single repair target (wave0, wave1, wave2_synthesis) use a static
`route_map: dict[PhaseVerdict, str]`. Phases with multiple repair targets
(readiness: 3 targets, final_delivery: 2 targets) use a `route_resolver` callable
`(verdict, failures) -> str` that inspects failure codes to select the correct
route label. The `route_map`/`route_resolver` preserves the exact topology edge
labels from change 01. The topology snapshot regenerates with identical node/edge
structure.

### Decision 3: Fixture GateRules wrap the existing fixture_plan

For the fake graph, each phase's `GateDefinition` contains a single
`FixtureSequenceRule`. This rule reads `fixture_plan[phase][index]` where `index =
completed_visits(state, phase)`, and:
- If the fixture value is the phase's pass-equivalent → returns `None` (rule passes,
  verdict = `PASS`).
- If the fixture value is a non-pass variant → returns a `Failure` with
  `classification=repairable` and the appropriate `FailureCode`.

The pass-equivalent and variant mapping is phase-specific because each phase uses a
different fixture enum type in `FakeFixturePlan`:

| Phase | Fixture enum | Pass value | Non-pass → FailureCode |
|-------|-------------|------------|------------------------|
| wave0, wave1 | `lifecycle.GateVerdict` | `PASS` | `REPAIR` → `WORK_FAILED` |
| wave2_synthesis | `SynthesisVerdict` | `PASS` | `EVIDENCE_NEEDED` → `MISSING_EVIDENCE` |
| readiness | `ReadinessVerdict` | `PASS` | `REPAIR_TARGETED` → `REPAIR_TARGETED`; `REPAIR_SYNTHESIS` → `REPAIR_SYNTHESIS`; `REPAIR_HITL2` → `REPAIR_HITL2` |
| final_delivery | `FinalVerdict` | `PASS` | `REPAIR` → `WORK_FAILED`; `EVIDENCE_BLOCKED` → `EVIDENCE_INSUFFICIENT` |

`FixtureSequenceRule` is constructed with a `pass_values: frozenset[str]` and a
`failure_code_map: dict[str, FailureCode]` so it works generically across all
fixture enum types. The `fixture_plan` continues to use the existing change-01 enum
types — they are NOT replaced by `PhaseVerdict`.

The `bounded_repair_update()` logic (attempt counting, exhaustion) is replaced by
the gate's own budget tracking and fatigue detection. The `choose_fixture()`
function is removed — fixture sequence indexing moves into `FixtureSequenceRule`.

**Rationale:** The change-01 `fixture_plan` uses 4 different phase-specific enum
types. A single `FixtureSequenceRule` implementation with configurable
pass-values and failure-code mapping handles all of them without per-phase
subclasses. The full evaluation path (collect-all, classify, verdict, fatigue
tracking) is exercised even with fixtures.

### Decision 4: Failure codes are a closed StrEnum with classification attribute

`FailureCode` is a `StrEnum` in `domain/failure_codes.py`. Each member carries a
`classification` in `{hard, semantic, repairable, degradable}` via a `_classification_map`
lookup. Models and workers cannot emit new codes; phase definitions register codes
they produce.

Initial code set (expandable by later changes):
- Hard: `MISSING_WORK_SPEC`, `WORK_CANCELLED`, `IDENTITY_MISMATCH`, `SCHEMA_VERSION_UNSUPPORTED`
- Semantic: `INCOMPLETE_TOPIC_COVERAGE`, `MISSING_EVIDENCE`, `DEGRADED_EVIDENCE_QUALITY`, `EVIDENCE_INSUFFICIENT`
- Repairable: `WORK_TIMED_OUT`, `WORK_FAILED`, `BUDGET_EXHAUSTED`, `INVALID_OUTPUT_SCHEMA`, `CONTENT_HASH_MISMATCH`, `REPAIR_TARGETED`, `REPAIR_SYNTHESIS`, `REPAIR_HITL2`
- Degradable: `UNTRUSTED_SOURCE`
- System (gate-internal): `REPAIR_BUDGET_EXHAUSTED`, `FATIGUE_ESCALATION`

**Rationale:** Free-form failure strings from LLM critics would make routing
brittle and fatigue tracking unreliable. Closed codes guarantee stable repair
strategies and escalation paths.

`PhaseVerdict.NEEDS_HUMAN` is reserved for future use. No `FailureCode`
classification produces it in change 03; no fixture rule triggers it. It exists in
the enum so that later changes (e.g. a quality critic that detects an unfixable
issue requiring user judgment) can add rules that produce this verdict without
breaking the `PhaseVerdict` type. Fixture `GateDefinition` route_maps omit
`NEEDS_HUMAN` — it is not a reachable verdict for the fake graph.

### Decision 5: Repair budget is per-phase, initialized lazily, fatigue stored in GateResult

`repair_budget_by_phase` maps `phase_name → remaining_budget`. Default budget: 3
for most phases, 1 for `final_delivery` self-repair. Maximum: 10. Budget is
initialized lazily: when `evaluate_gate` reads `repair_budget_by_phase[phase]` and
finds it missing, it initializes to the phase's default (carried on
`GateDefinition.default_budget`). Budget is decremented on each `repair` verdict.

Fatigue detection compares the current evaluation's failure fingerprint (a
stable-ordered tuple of `(failure_code, rule_name)`) against the previous
fingerprint stored in `latest_gate_feedback`. `GateResult` carries a `phase: str`
field and a `consecutive` counter: the gate reads the previous `GateResult` from
`latest_gate_feedback`; if `previous.phase == current_phase` AND the fingerprints
match, `consecutive = previous.consecutive + 1`; otherwise `consecutive = 1`. The
phase check prevents cross-phase fatigue — wave0's feedback is never compared
against wave1's fingerprint. If `consecutive >= 3`, the gate escalates to
`BLOCKED` with `FATIGUE_ESCALATION` regardless of remaining budget.

**Rationale:** Per-phase budgets prevent early phases from starving later ones.
Lazy initialization avoids an explicit "init all phases" step and lets each phase's
gate definition own its default budget. Fingerprint-based fatigue catches cases
where repair keeps producing the same failures (repair is not making progress) even
though budget remains. Storing fatigue in `GateResult` avoids adding a new state
field — the previous evaluation's `GateResult` in `latest_gate_feedback` is the
only persistence needed.

### Decision 6: Repair loop is graph-topology-driven

When the gate returns `REPAIR`, the `route_map` produces the repair route label
(e.g. `"repair"`, `"evidence_needed"`, `"repair_targeted"`). The graph's
conditional edge routes to the repair target: for wave0/wave1/final_delivery this
is self-repair (same node); for wave2_synthesis it goes to `targeted_evidence`
(which returns to wave2_synthesis); for readiness it goes to one of
`targeted_evidence`/`wave2_synthesis`/`hitl2`. The repair agent runs inside the
target node on re-entry, reading `latest_gate_feedback` for `inspect`/`advice`.
The gate evaluates again after the repair agent completes.

**Rationale:** LangGraph's edge routing IS the repair loop. Each attempt is a
checkpoint. The gate does not own an inner while-loop. This makes the repair
loop visible in the execution trace and keeps checkpoint granularity correct.

### Decision 7: `route` field ownership moves to GATE; `repair_counts` frozen

The `route` field in `ResearchState` currently has `WriterRole.CONTROLLER`. After
this change, its writer becomes `WriterRole.GATE` — only the gate kernel writes
the routing decision for gated phases. Non-gated nodes (bootstrap, hitl1, hitl2,
rerun) still write `route` directly with `WriterRole.CONTROLLER` (the node wrapper
chooses the writer based on whether a gate definition exists).

`repair_counts` is superseded by `gate_attempts_by_phase` and
`repair_budget_by_phase`. It is kept in the schema for backward compatibility with
existing checkpoints but no longer written. `TerminalReason` gains
`GATE_BLOCKED = "gate_blocked"`; the old `REPAIR_EXHAUSTED` is retained but no
longer produced (change-01 fixtures now produce `GATE_BLOCKED` via gate budget
exhaustion).

**Rationale:** The ownership table (REG-006) requires every field to declare its
writer. Moving `route` to GATE aligns with the gate's role as phase-transition
authority. Removing `repair_counts` from the schema would break checkpoint
deserialization (ResearchCheckpoint is a frozen dataclass), so it stays as a
vestigial field.

## Risks / Trade-offs

- **Risk: Gate evaluation inside the phase wrapper means the wrapper writes gate
  fields.** → Mitigation: The wrapper is trusted graph infrastructure. The reducer
  (`apply_research_update` with `WriterRole`) already rejects worker writes to gate
  fields. The wrapper uses `WriterRole.GATE` when invoking gate evaluation and
  `WriterRole.CONTROLLER` for non-gated nodes.

- **Risk: `PhaseVerdict` name collision with `GateVerdict` (branch verdict) in
  `lifecycle.py`.** → Mitigation: These are distinct types in separate modules
  (`domain/gate.py` vs `domain/lifecycle.py`). `GateVerdict` (pass|repair) is the
  branch-level verdict. `PhaseVerdict` (pass|repair|blocked|needs_human) is the
  phase-gate verdict. No code imports both at the same call site.

- **Risk: Fixture rules might not catch all real-gate edge cases.** → Mitigation:
  Fixture rules exercise the full evaluation pipeline. Property tests cover rule
  ordering stability, duplicate failure dedup, budget exhaustion, and fatigue
  escalation. Real rules are tested in their owning changes.

- **Risk: `route_map` misconfiguration could produce a route label not in the
  topology's conditional edges.** → Mitigation: `GateDefinition.__post_init__`
  validates that every value in `route_map` appears in a closed set of known
  topology route labels. The topology snapshot test catches drift.

## Open Questions

- None at design time. The plan is well-specified and the dependency chain (00→01→02)
  provides all needed infrastructure.
