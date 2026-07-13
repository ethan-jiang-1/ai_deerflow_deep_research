## Why

Change 01's fake gate routes hardcoded fixture outcomes through deterministic routers.
Changes 04 (work-unit kernel) and every real phase node (05-16) need a shared gate that
collects every rule failure, distinguishes hard from repairable, tracks attempt fatigue,
and feeds structured `inspect`/`advice` into a generic repair loop. Without that kernel
now, each phase would reinvent its own gate, retry loop, and failure model — fracturing
the invariant that gate is the single phase-transition authority and creating
inconsistent repair semantics the graph topology already expects.

## What Changes

- Define `GateDefinition`, `GateRule`, `Failure`, `GateResult`, and `PhaseVerdict`
  (`pass | repair | blocked | needs_human`) in a new `domain/gate.py` module, and a
  closed `FailureCode` enum with stable classifications (`hard | semantic | repairable
  | degradable`) in `domain/failure_codes.py`.
- Implement deterministic rule evaluation (`evaluate_gate`) as a pure async function:
  collect-all over every registered rule, produce a stable-ordered failure fingerprint,
  classify each failure, and derive a typed verdict. Provenance, schema, and identity
  rules are never degradable-pass; hard failures are never repairable.
- Each `GateDefinition` carries a phase-specific `route_map: dict[PhaseVerdict, str]`
  that translates the typed verdict to the concrete route string the topology's
  conditional edges expect (e.g. `BLOCKED → "exhausted"`, `REPAIR → "repair"`). The
  existing `_route()` function in `graph/builder.py` is unchanged — it still reads
  `state["route"]`, which is now written by the gate instead of the phase node.
- The gate kernel is the **sole writer** of `latest_gate_feedback`,
  `gate_attempts_by_phase`, `repair_budget_by_phase`, and the `route` field (ownership
  moves from CONTROLLER to GATE in the ownership table). Worker and repair agents SHALL
  NOT write these fields.
- Implement a generic bounded repair loop driven by graph topology: when the gate
  returns `repair`, the conditional edge routes to the repair target (same phase for
  wave0/wave1/final_delivery self-repair, or a different node for readiness/targeted
  evidence). The repair agent reads `latest_gate_feedback` for context. Fatigue
  escalation (same failure fingerprint 3× consecutively) drives `blocked` even if
  budget remains.
- Replace the skeleton's `choose_fixture()` and `bounded_repair_update()` helpers with
  fixture `GateRule` instances that produce identical routing outcomes, preserving all
  change-01 graph paths and the topology snapshot.
- Add `TerminalReason.GATE_BLOCKED` to the lifecycle enum; deprecate `repair_counts`
  (superseded by `gate_attempts_by_phase` + `repair_budget_by_phase`).
- `backend/` and `frontend/` are not modified.

## Capabilities

### New Capabilities

- `gate-kernel`: Shared deterministic gate evaluation, failure classification, repair
  loop, and attempt/fatigue tracking that every phase consumes through one gate-rule
  registry without owning its own transition authority.

### Modified Capabilities

- `research-graph-lifecycle`: gate verdicts (`pass | repair | blocked | needs_human`)
  replace the fixture outcome switch as the routing authority for every phase
  transition; the topology, typed routers, and `_route()` function are unchanged. Fake
  gate behavior is preserved through fixture rules producing identical outcomes.

## Impact

- **Source:** additive under `agent/src/deerflow_deep_research/domain/gate.py` (new),
  `domain/failure_codes.py` (new), `engine/gate_kernel.py` (new gate evaluation
  engine), `engine/gate_fixtures.py` (new fixture rules replacing the fake outcome
  switch). `graph/builder.py` integrates gate evaluation into the node wrapper and
  wires per-phase gate definitions; `graph/routing.py` is unchanged. `domain/state.py`
  updates the `route` field ownership from CONTROLLER to GATE and freezes
  `repair_counts`. `domain/lifecycle.py` adds `TerminalReason.GATE_BLOCKED`.
  `engine/fake_control.py` removes `choose_fixture()` and `bounded_repair_update()`.
  `backend/` and `frontend/` are not modified.
- **Typed state/checkpoint data affected:** the gate kernel becomes the sole writer of
  `latest_gate_feedback`, `gate_attempts_by_phase`, `repair_budget_by_phase`, and
  `route` (slots already defined in `ResearchState` by change 02; `route` ownership
  changes from CONTROLLER to GATE). No new state fields are added. `repair_counts` is
  frozen (no longer written). `TerminalReason` gains `GATE_BLOCKED`.
- **Graph nodes/components affected:** gate evaluation is invoked from the existing
  `_node_wrapper` when a `GateDefinition` is registered for the phase; nodes without a
  gate definition (bootstrap, hitl1, hitl2, rerun) write `route` directly as before.
  All other fake nodes are unchanged. The topology snapshot is regenerated with
  identical node/edge structure.
- **Node-agent roles used:** the repair agent is the only new node-agent role. It
  receives structured `GateResult` feedback (not raw gate internals) through the
  existing runtime-owned bridge (NOA-001). The gate kernel is deterministic Python —
  no model or agent loop.
- **Sandbox artifacts read/written:** `diagnostics/gate-attempts.jsonl` for audit-only
  gate attempt logging (already defined in bundle layout by change 02). No new artifact
  categories.
- **DeerFlow extension surfaces used:** none new and none modified.
- **Reload boundary:** source-only change under `agent/src/`; next agent build. No
  Gateway restart required.
- **Dependencies:** no new runtime dependency.
- **Non-goals:** no real phase-specific gate rules (Wave0/Wave1/Wave2/readiness) —
  those arrive with their owning changes 08/10/11/15. No LLM critic as hard gate
  authority. No files under `backend/` or `frontend/` are modified.

The new requirement IDs are GAK-001 through GAK-006 (new capability `gate-kernel`);
REG-002 and REG-004 are modified (capability `research-graph-lifecycle`).
