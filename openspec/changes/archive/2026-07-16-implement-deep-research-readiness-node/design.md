## Context

The readiness node is a quality phase at `graph/nodes/readiness/`. It sits between HITL2(proceed) and final_delivery. The **fake** returns `node_update("readiness")` with no route; a fixture gate reads `fixture_plan` from state and provides the route. The **real** node is non-gated (like hitl2, rerun): it writes its own `route`. The contracts are `ReadinessRequest(generation)` and `ReadinessResult(route: ReadinessVerdict)`.

The topology edges are: `pass → final_delivery`, `repair_targeted → targeted_evidence`, `repair_synthesis → wave2_synthesis`, `repair_hitl2 → hitl2`, `exhausted → END`.

Critical architecture constraint: the `_node_wrapper` in `builder.py:101` passes `state` (pre-node state) to `evaluate_gate_for_node`, NOT the node's result. For non-work-unit nodes, the gate cannot read the node's output. The real readiness node therefore bypasses the gate mechanism entirely and writes `route` directly.

## Goals / Non-Goals

**Goals:**
- Hard checks: citation availability (accepted submissions non-empty), provenance (valid `ref:` prefix), HITL2 consumption (consumed_request_ids non-empty).
- Semantic critic: bounded read-only agent loop assessing answerability per must-answer question. Initial: deterministic fallback. Target: real agent loop via bridge (change 09 pattern).
- Report plan materializer: deterministic projection of writable conclusions, mandatory uncertainties, and prohibited claim upgrades. ContentRef checkpointed.
- The node determines its own route based on hard-rule results + critic verdicts.
- `repair_targeted` → targeted_evidence (evidence gaps). `pass` → final_delivery. `exhausted` → END (structural preconditions fail).

**Non-Goals:**
- No gate definition. No gate budget/fatigue tracking (node handles its own routing).
- No final report writing. No web tools on critic. No `backend`/`frontend` changes. Topology unchanged.

## Decisions

### Decision 1: Readiness is a non-gated node that determines its own route

The `_node_wrapper` passes pre-node state to gates, so a gate cannot read the node's computed output (`readiness_hard_failures`, `readiness_blocked_count`). Rather than work around this limitation, readiness follows the same pattern as hitl2, rerun, and topic_planning: the node writes `route` directly. The fixture gate is removed when the real node is active (the builder already supports per-phase gate overrides; we simply don't provide a real gate for readiness).

### Decision 2: Hard checks run inside the node, not in gate rules

Three deterministic checks on pre-existing state:
- `check_citation_availability`: `accepted_submission_refs` is non-empty → failure code `citation_no_accepted_evidence`
- `check_provenance`: every ref in `accepted_submission_refs` starts with `ref:` → failure code `provenance_invalid_ref`
- `check_hitl2_consumption`: `consumed_request_ids` is non-empty → failure code `hitl2_not_consumed`

These are structural checks only. Full claim → source → cache chain verification requires sandbox access and is deferred.

### Decision 3: HardRuleFailure is a typed contract in contracts.py

```python
class HardRuleFailure(FrozenContract):
    code: str
    detail: str = ""
    refs: tuple[str, ...] = ()
```

The node serializes these to plain dicts when writing `readiness_hard_failures` to checkpoint state. Both producer (node) and consumer (future diagnostics) agree on this format.

### Decision 4: Critic uses deterministic fallback; real agent loop is deferred

The initial critic (`critic.py`) marks all must-answer questions as `ready_substantive` with a note that the assessment is deterministic. This allows the hard rules, materializer, and routing to be fully exercised and tested. The real bounded agent loop — using the bridge pattern from evidence critics (change 09) — is a targeted follow-up.

The critic's contract is `ReadinessCriticOutput` containing per-question `PerQuestionVerdict` entries and overall limitation/synthesis-flaw lists.

### Decision 5: Report plan is an immutable machine-readable contract

The report plan (`ReadinessReportPlan`) is checkpointed as a `ContentRef` with:
- `sandbox_path`: `workspace/deep-research/{research_id}/review/report-plan.json`
- `content_hash`: base64url-encoded SHA-256 of the serialized plan JSON (43 chars)
- `schema_version`: 1

The plan contains writable conclusions (from `ready_substantive` verdicts), mandatory uncertainties (from `ready_insufficient_judgment`), and prohibited upgrades. The final writer (change 16) reads this plan via its ContentRef and is prohibited from introducing facts outside it.

### Decision 6: Route determination prioritizes structural failures over critic verdicts

```
if any structural hard-rule failure → "exhausted" (terminal_status=BLOCKED)
elif blocked questions > 0 → "repair_targeted"
else → "pass"
```

Structural failures (no evidence, bad provenance, no HITL2 consumption) are terminal — they indicate a graph-level precondition that repair won't fix. Blocked questions → repair_targeted goes back to targeted_evidence for gap-filling. `repair_synthesis` and `repair_hitl2` routes exist in the topology but are deferred.

### Decision 7: New state fields are additive with safe defaults

`readiness_hard_failures` (tuple of dicts, default `()`), `readiness_critic_summary` (dict, default `{}`), `readiness_blocked_count` (int, default `0`), `readiness_report_plan` (ContentRef | None, default `None`). `RESEARCH_STATE_SCHEMA_VERSION` not bumped.

## Risks / Trade-offs

- **[Risk] Non-gated means no budget/fatigue tracking.** → Mitigation: readiness is a single-pass assessment. If it routes to repair_targeted, the graph cycles through targeted_evidence → wave2_synthesis → HITL2 → readiness again. The rerun node handles generation tracking; readiness itself doesn't need multi-attempt repair.
- **[Risk] Critic fallback marks all questions as answerable.** → Mitigation: the fallback is explicitly flagged. Hard rules still catch structural failures. The real agent loop replaces the fallback before production use.
- **[Risk] `exhausted` route for structural failures may be confusing alongside repair budget exhaustion.** → Mitigation: the node uses `exhausted` for terminal structural failures (no evidence, no HITL2). This is semantically distinct from gate budget exhaustion and is documented in the route comments.

## Open Questions

- When to replace the deterministic critic fallback with the real agent loop (bridge integration).
- Whether `repair_synthesis` and `repair_hitl2` routes should be activated before or after the real critic agent.
