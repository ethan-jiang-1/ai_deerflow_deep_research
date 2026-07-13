## 1. Domain types — failure codes, verdicts, and gate contracts

- [x] 1.1 Define `FailureCode` closed `StrEnum` with stable values and `_classification_map` lookup (`hard | semantic | repairable | degradable`) — `domain/failure_codes.py` @impl GAK-002
- [x] 1.2 Define `PhaseVerdict` enum (`pass | repair | blocked | needs_human`), distinct from existing `lifecycle.GateVerdict` (branch verdict: `pass | repair`) — `domain/gate.py` @impl GAK-001
- [x] 1.3 Define `Failure` (with optional `ref: str | None`), `GateResult` (with `phase: str`, `degraded: bool`, `fingerprint`, `consecutive`, `new_generation: int | None`; JSON-serializable for `latest_gate_feedback` storage), `GateRule` (sync callable `(ResearchState) -> Failure | None`), `GateDefinition` (with `default_budget: int`, `route_map` or `route_resolver`, validated at construction) — `domain/gate.py` @impl GAK-001
- [x] 1.4 Add `TerminalReason.GATE_BLOCKED = "gate_blocked"` to `domain/lifecycle.py`; retain `REPAIR_EXHAUSTED` in enum but it is no longer produced by gate logic @impl REG-004

## 2. State ownership and schema updates

- [x] 2.1 Update `route` field ownership in `domain/state.py` OWNERSHIP_TABLE: writer changes from `CONTROLLER` to `GATE`, readers add `GATE` — `domain/state.py` @impl GAK-003
- [x] 2.2 Freeze `repair_counts` field: keep in ResearchState/ResearchCheckpoint for backward compat, but remove all writes to it; superseded by `gate_attempts_by_phase` + `repair_budget_by_phase` — `domain/state.py` @impl GAK-003
- [x] 2.3 Verify `AUTHORITY_WRITERS` already includes `WriterRole.GATE` and `GATED_FIELDS` already includes `route`; add `route` to `GATED_FIELDS` if not present — `domain/state.py`

## 3. Gate evaluation engine

- [x] 3.1 Implement `evaluate_gate(state, phase, gate_def) -> GateResult` pure synchronous function: collect-all rules, classify failures, derive verdict, compute `attempt = (gate_attempts_by_phase.get(phase) or 0) + 1`, `new_generation = state.get("generation", 0) + 1` (on PASS/BLOCKED only), build failure fingerprint, compute `consecutive` by comparing against previous `GateResult` in `latest_gate_feedback` (checking `previous.phase == phase` before comparing fingerprints to avoid cross-phase fatigue) — `engine/gate_kernel.py` @impl GAK-001, GAK-006
- [x] 3.2 Implement verdict derivation logic: hard failure → `BLOCKED`; repairable/semantic with budget → `REPAIR`; no failures or only degradable → `PASS` (with `degraded=True` for degradable); budget exhausted → `BLOCKED` with `REPAIR_BUDGET_EXHAUSTED` — `engine/gate_kernel.py` @impl GAK-001
- [x] 3.3 Implement fatigue detection: track `(failure_code, rule_name)` fingerprint per phase; same fingerprint 3× consecutively → `BLOCKED` with `FATIGUE_ESCALATION` regardless of budget; different fingerprint → reset counter — `engine/gate_kernel.py` @impl GAK-004
- [x] 3.4 Implement budget tracking: read full `repair_budget_by_phase` dict from state (default `{}`), lazily initialize `repair_budget_by_phase[phase]` from `GateDefinition.default_budget` if absent; build updated dict `{**current, phase: new_value}` (include ALL keys — LangGraph TypedDict fields without `Annotated` use `LastValue`, which replaces the entire dict rather than shallow-merging). Decrement on `REPAIR`; block on exhaustion — `engine/gate_kernel.py` @impl GAK-004
- [x] 3.5 Implement `gate_result_to_state_update(gate_result, phase) -> dict` function: builds partial update dict with `route`, `latest_gate_feedback` (`GateResult` serialized via `model_dump(mode="json")` or equivalent), full `gate_attempts_by_phase` dict (read current + set `phase: gate_result.attempt`), full `repair_budget_by_phase` dict (read current + set `phase: gate_result.remaining_budget`), `generation: gate_result.new_generation` (only if not None), `terminal_reason`/`terminal_status`/`phase_status` (on BLOCKED); pass through `apply_research_update` with `writer=WriterRole.GATE` — `engine/gate_kernel.py` @impl GAK-003

## 4. Fixture gate rules

- [x] 4.1 Implement `FixtureSequenceRule`: constructed with `pass_values: frozenset[str]` and `failure_code_map: dict[str, FailureCode]`; reads `fixture_plan[phase][completed_visits(state, phase)]` (a **string** from the checkpoint, not an enum member — `fixture_plan_to_checkpoint` serializes enum values to strings), returns `None` if value is in `pass_values`, otherwise returns `Failure(code=failure_code_map[value], classification=repairable)`. Handles index out of bounds by clamping to last element. Generic across all fixture enum types (`GateVerdict`, `SynthesisVerdict`, `ReadinessVerdict`, `FinalVerdict`) — `engine/gate_fixtures.py` @impl GAK-005
- [x] 4.2 Define per-phase `GateDefinition` with `FixtureSequenceRule` and `route_map` for every gated phase: wave0, wave1, wave2_synthesis, readiness, final_delivery — `engine/gate_fixtures.py` @impl GAK-005
- [x] 4.3 Define route resolution per phase matching existing topology edges. Static `route_map` for single-target phases: wave0/wave1 `{PASS: "pass", REPAIR: "repair", BLOCKED: "exhausted"}`; wave2_synthesis `{PASS: "pass", REPAIR: "evidence_needed"}`. `route_resolver` callable for multi-target phases: readiness maps `REPAIR` to `"repair_targeted"`/`"repair_synthesis"`/`"repair_hitl2"` based on fixture value, `BLOCKED` to `"exhausted"`, `PASS` to `"pass"`; final_delivery maps `REPAIR` to `"repair"` or `"evidence_blocked"` based on fixture value, `BLOCKED` to `"exhausted"`, `PASS` to `"pass"` — `engine/gate_fixtures.py` @impl GAK-005

## 5. Graph integration — wire gate evaluation into node wrapper

- [x] 5.1 Update `_node_wrapper()` in `graph/builder.py`: after phase node returns, check if `GateDefinition` exists for `logical_name`; if yes, call `evaluate_gate()` (sync) and merge its state update into the return dict; if no, pass node return directly. The wrapper uses the gate-produced update as-is — authority enforcement happens via `apply_research_update` at the handler layer. Nodes without a gate definition (bootstrap, hitl1, hitl2, rerun, topic_planning, targeted_evidence) are unchanged — `graph/builder.py` @impl GAK-003
- [x] 5.2 Pass `gate_defs: dict[str, GateDefinition]` into `build_research_graph()` and make available to `_node_wrapper` closures — `graph/builder.py` @impl GAK-005
- [x] 5.3 Remove `bounded_repair_update()` from `engine/fake_control.py`. Stop using `choose_fixture()` in gated phases (wave0, wave1, wave2_synthesis, readiness, final_delivery) — gate evaluation replaces it. Retain `choose_fixture()` for non-gated fixture-driven nodes (bootstrap). Retain `completed_visits`, `make_attempt_id`, `fixture_sequence`, `node_update`, `text_only_content` for use by fake nodes and fixture rules — `engine/fake_control.py` @impl GAK-005
- [x] 5.4 Update fake nodes (wave0, wave1, wave2_synthesis, readiness, final_delivery) to NOT write `route` directly — they return only their work result; route is now written by gate evaluation. Also update `engine/fake_control.py` `node_update()` to not require `route` — `graph/nodes/*/fake.py`, `engine/fake_control.py` @impl GAK-005
- [x] 5.5 `graph/routing.py` unchanged — `_route()` still reads `state["route"]` — but verify `route_typed()` works with route strings produced by gate @impl GAK-001

## 6. Requirement ID registry

- [x] 6.1 Add `GAK: gate-kernel` prefix mapping to `openspec/governance/req-registry.yaml`
- [x] 6.2 Register GAK-001 through GAK-006 requirements in `openspec/governance/req-registry.yaml` with descriptions matching the spec

## 7. Tests — gate domain types

- [x] 7.1 Test `FailureCode` enum: every code has a classification, no duplicate values, no unregistered codes — `agent/tests/domain/test_failure_codes.py` @impl GAK-002
- [x] 7.2 Test `GateDefinition` construction: valid `route_map` accepted, missing verdict key rejected, unknown route label rejected — `agent/tests/domain/test_gate.py` @impl GAK-001
- [x] 7.3 Test `PhaseVerdict` is distinct from `lifecycle.GateVerdict` and values don't collide in gate vs branch contexts — `agent/tests/domain/test_gate.py`

## 8. Tests — gate evaluation logic

- [x] 8.1 Test all rules pass → `PASS` verdict, empty failures — `agent/tests/engine/test_gate_kernel.py` @impl GAK-001
- [x] 8.2 Test single repairable failure with budget → `REPAIR` verdict — @impl GAK-001
- [x] 8.3 Test hard failure → `BLOCKED` regardless of budget — @impl GAK-001
- [x] 8.4 Test budget exhaustion: repairable failures + remaining_budget=0 → `BLOCKED` with `REPAIR_BUDGET_EXHAUSTED` — @impl GAK-004
- [x] 8.5 Test degradable-only failures → `PASS` with `degraded=True` — @impl GAK-001
- [x] 8.6 Test collect-all: hard failure + repairable failure → both in failures list, verdict `BLOCKED` — @impl GAK-001, GAK-006
- [x] 8.7 Test stable ordering: same input twice → identical GateResult; rule registration order = failure list order — @impl GAK-006
- [x] 8.8 Test purity: gate evaluation has no I/O, no model calls, no state mutation — @impl GAK-006
- [x] 8.9 Test route_map translation: `BLOCKED → "exhausted"`, `REPAIR → "repair"`, `PASS → "pass"` for wave0 — @impl GAK-001
- [x] 8.10 Test lazy budget initialization: first evaluation for a phase with no entry in `repair_budget_by_phase` uses `GateDefinition.default_budget` — @impl GAK-004
- [x] 8.11 Test `PhaseVerdict.NEEDS_HUMAN` exists in the enum but no rule produces it in the fake graph — @impl GAK-001
- [x] 8.12 Test `route_resolver` for multi-target phases: readiness `REPAIR` with `REPAIR_TARGETED` code → `"repair_targeted"`; final_delivery `REPAIR` with `EVIDENCE_INSUFFICIENT` code → `"evidence_blocked"` — @impl GAK-001

## 9. Tests — repair loop and fatigue

- [x] 9.1 Test successful repair: repair → pass, gate_attempts=2, budget decremented — `agent/tests/engine/test_gate_kernel.py` @impl GAK-004
- [x] 9.2 Test budget exhaustion: N repairs with budget N → blocked — @impl GAK-004
- [x] 9.3 Test fatigue escalation: same fingerprint 3× → blocked with `FATIGUE_ESCALATION` despite remaining budget — @impl GAK-004
- [x] 9.4 Test different fingerprint resets fatigue counter — @impl GAK-004
- [x] 9.5 Test fatigue counter is per-phase (wave0 fatigue doesn't affect wave1) — @impl GAK-004
- [x] 9.6 Test `GateResult.consecutive` is stored in `latest_gate_feedback` and read back on next evaluation; consecutive=1 on first eval, increments on same fingerprint, resets on different fingerprint — @impl GAK-004
- [x] 9.7 Test cross-phase fatigue isolation: wave0 feedback in `latest_gate_feedback` does not affect wave1 fatigue counter (different `phase` field → reset to 1) — @impl GAK-004

## 10. Tests — gate sole-writer authority

- [x] 10.1 Test gate writes (route, latest_gate_feedback, gate_attempts_by_phase, repair_budget_by_phase) accepted by `apply_research_update` with `writer=GATE` — `agent/tests/domain/test_state.py` @impl GAK-003
- [x] 10.2 Test worker write to gate field rejected by reducer — @impl GAK-003
- [x] 10.3 Test generation increments only on PASS/BLOCKED, not on REPAIR — @impl GAK-003
- [x] 10.4 Test `route` field ownership is GATE after change — @impl GAK-003

## 11. Tests — fixture rule integration and graph E2E

- [x] 11.1 Test fixture gate rules produce identical route outcomes to change-01 fixture plan for every phase — `agent/tests/graph/test_gate_integration.py` @impl GAK-005
- [x] 11.2 Test every change-01 E2E path works through gate evaluation: happy completion, wave0 repair→pass, wave1 repair→pass, target evidence loop, rerun, stop, cancel — @impl GAK-005
- [x] 11.3 Test fixture repair exhaustion now produces `GATE_BLOCKED` terminal reason via gate budget exhaustion — @impl REG-004
- [x] 11.4 Test topology snapshot regeneration yields identical node/edge structure (same source, route labels, targets) — @impl GAK-005

## 12. Cleanup and governance

- [x] 12.1 Regenerate topology snapshot (`topology_snapshot.py`) and verify identity with change-01 snapshot
- [x] 12.2 Verify that `gate_attempts_by_phase` and `repair_budget_by_phase` use `LastValue` channel (entire-dict replacement) — confirm the implementation writes the full dict with all keys (not per-key updates). Add contract test that cross-phase data is preserved (wave0 gate write doesn't erase wave1 data from a prior lifecycle pass)
- [x] 12.3 Run `python3 openspec/governance/check_project_reqs.py` and fix any issues (GAK-* must be registered, REG-002/REG-004 must be in delta)
- [x] 12.4 Run `python3 openspec/governance/check_project_specs.py` and fix any issues (no delta headers in main specs, no missing requirement IDs)
- [x] 12.5 Run `cd agent && make test` — full test suite green
- [x] 12.6 Run `cd agent && make format && make lint` — format and lint clean
- [x] 12.7 Update `agent/AGENTS.md` with gate kernel module descriptions (`domain/gate.py`, `domain/failure_codes.py`, `engine/gate_kernel.py`, `engine/gate_fixtures.py`)
