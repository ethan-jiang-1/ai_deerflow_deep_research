## Context

The HITL2 node (change 13) already routes the `rerun` decision to the rerun node, and the graph topology already has the back edge `rerun -> topic_planning` (line 195 of `graph/builder.py`). The fake rerun node at `graph/nodes/rerun/fake.py` mechanically bumps `generation += 1` and checks against `MAX_FAKE_RERUN_GENERATIONS` (hardcoded to 2 in `domain/lifecycle.py:22`). The contracts (`RerunRequest`, `RerunResult`) are minimal placeholders.

The real implementation must replace this with scoped invalidation: parse the HITL2 rerun decision payload to determine *what* to redo (full run, specific topics, specific findings), invalidate only the derived projections from the old generation (synthesis, decision brief, report plan) while preserving the append-only submission ledger and raw evidence, materialize new/revised WorkSpecs through the work-unit kernel, and route to the correct re-entry point via a closed set of back edges.

The rerun node is a code-only orchestration node (no LLM, no sandbox writes). It reads HITL2's decision payload and current checkpoint state, and writes updated control state only.

Relevant files:
- `graph/nodes/rerun/contracts.py` — current `RerunRequest(generation)` and `RerunResult(route)` placeholders
- `graph/nodes/rerun/node.py` — `build_real = UNAVAILABLE_REAL_FACTORY`
- `graph/nodes/rerun/fake.py` — `generation >= MAX_FAKE_RERUN_GENERATIONS → exhausted`, else `generation += 1, route = next`
- `graph/nodes/rerun/__init__.py` — `NODE_SPEC` with `logical_name="rerun"`, `phase=NodePhase.ORCHESTRATION`
- `graph/builder.py:183-195` — HITL2 edge `"rerun": "rerun"`, rerun edge `"next": "topic_planning", "exhausted": END`
- `domain/state.py:642` — `generation: int = 0`, validated `0 ≤ generation ≤ MAX_FAKE_RERUN_GENERATIONS`
- `domain/lifecycle.py:22` — `MAX_FAKE_RERUN_GENERATIONS = 2`

## Goals / Non-Goals

**Goals:**
- Parse the HITL2 rerun decision payload to extract typed `RerunScope` (full, per-topic, per-finding) and reason.
- Monotonically increment `generation`; preserve old ledger and raw evidence artifacts as append-only.
- Deterministically invalidate derived projections from the old generation (synthesis ref, decision brief ref, report refs) by clearing their checkpoint refs — never deleting sandbox files.
- Materialize new or revised `WorkSpec`s via the existing work-unit kernel for scoped rework; topics/findings outside the rerun scope retain their accepted evidence.
- Route to a closed set of back edges determined by scope: `full` → `topic_planning` (re-plan from scratch); `topic` → `wave0` (scoped source intake, bypass topic planner); `finding` → `wave0` (stale sources) or `wave1` (deep evidence only).
- Write generation lineage (`parent_generation`, `rerun_reason`, `rerun_scope`) to checkpoint state for final diagnostics.
- Lift `MAX_FAKE_RERUN_GENERATIONS` to a configurable graph policy ceiling; remove the hardcoded validation in `ResearchCheckpoint.__post_init__`.

**Non-Goals:**
- No LLM call — rerun planner is code-only.
- No sandbox file writes — invalidation is a checkpoint state operation.
- No multi-generation branching or parallel active generations.
- No late-submit cross-generation acceptance.
- No modification to `backend/` or `frontend/`.
- No change to graph topology — existing edges are preserved; only the set of legal `route` values from the rerun node expands from `{next, exhausted}` to `{topic_planning, wave0, wave1, exhausted}`. The `topic_planning` edge is the existing `next` edge renamed for clarity.

## Decisions

### Decision 1: Rerun scope is extracted from the HITL2 decision payload, not inferred; RerunPlan is the final assembled output

The HITL2 brief presents findings grouped by topic. When the user chooses `rerun`, the brief builder includes metadata about which topics/findings the user flagged. This metadata is stored in the checkpoint state field `hitl2_rerun_payload: dict | None`:

```python
# Written by HITL2 when user selects "rerun" (future enhancement).
# When None or absent, the rerun node defaults to FULL scope.
hitl2_rerun_payload: dict | None = None
# Shape when present:
# {
#     "scope": "full" | "topic" | "finding",
#     "reason": "<user-provided reason text>",
#     "target_topic_ids": ["topic-a", "topic-b"],    # topic/finding only
#     "target_finding_ids": ["F-003", "F-007"],       # finding only
# }
```

The rerun node reads this payload and derives a typed `RerunScope`:

```python
class RerunScope(FrozenContract):
    scope: Literal["full", "topic", "finding"]
    reason: str                        # user-provided reason from HITL2 response
    target_topic_ids: tuple[str, ...]   # empty for FULL
    target_finding_ids: tuple[str, ...] # empty for FULL and TOPIC
    retain_topic_ids: tuple[str, ...]   # topics NOT to re-execute
```

`build_rerun_scope` is the first step in the pipeline — it reads `hitl2_rerun_payload` from state, validates it, and produces a `RerunScope`. Generation has not yet been incremented at this point; scope extraction is pure input parsing.

**Edge case — invalid IDs in payload:** If `target_topic_ids` or `target_finding_ids` reference IDs not present in `topic_registry` or accepted submissions, the node SHALL default to `FULL` scope and log a diagnostic. The user's intent cannot be honored if the targets don't exist; failing open (skipping unknown IDs) could silently omit work.

After generation increment and route determination, the final `RerunPlan` assembles scope + computed outputs:

```python
class RerunPlan(FrozenContract):
    generation: int          # new generation number (computed)
    parent_generation: int   # generation being superseded
    scope: RerunScope
    route: str               # topic_planning | wave0 | wave1 | exhausted
```

Why not let the rerun node infer scope from gaps: the user's intent ("I want to redo the methodology topic") is more precise than gap inference ("there are gaps in methodology, so redo it"). The HITL2 brief already presents gap information; the user's decision encodes which to act on.

Why split RerunScope from RerunPlan: generation increment is a separate step that happens after scope extraction. Putting the new generation number in the scope-extraction output would require it to be known before it's computed.

**Current HITL2 limitation:** The HITL2 brief builder (change 13) does not yet populate `hitl2_rerun_payload`. Until it does, all reruns default to `FULL` scope. TOPIC and FINDING scopes are implemented and testable (via direct state setup in tests) but not exercisable through the real HITL2 UI path.

### Decision 2: Invalidation is ref-clearing, not file deletion

Derived artifacts (synthesis, decision brief, report plan) are invalidated by setting their checkpoint refs to `None`/empty. The sandbox files themselves are preserved for diagnostic traceability. Raw evidence (submission ledger, source caches) is never touched.

Why: deletion is irreversible and risks data loss on crash. Clearing refs is checkpoint-atomic and reversible (old generation content remains in sandbox for diagnostics).

### Decision 3: Closed-set back edges, scope-determined

| Scope | Route | Rationale |
|-------|-------|-----------|
| `FULL` | `topic_planning` | Re-planning may produce different topics — let the LLM re-decompose from the HITL1 profile |
| `TOPIC` | `wave0` | Don't re-plan topics; do fresh source intake for the target topics. Retained topics' evidence stays in the ledger. Rerun node creates scoped WorkSpecs for target topics only. |
| `FINDING` (stale sources) | `wave0` | Source intake must be redone for these findings |
| `FINDING` (deep evidence only) | `wave1` | Wave0 evidence is still valid; only deep extraction needs redo |

The edge map in the builder expands from `{"next": "topic_planning", "exhausted": END}` to include the new semantic keys **alongside** the existing `"next"` key for backward compatibility with the unchanged fake node:

```python
{
    "next": "topic_planning",           # fake backward compat (unchanged)
    "topic_planning": "topic_planning",  # real FULL
    "wave0": "wave0",                   # real TOPIC / FINDING (stale sources)
    "wave1": "wave1",                   # real FINDING (deep evidence only)
    "exhausted": END,                   # both fake and real
}
```

The fake node is not modified; it continues to return `route = "next"` or `route = "exhausted"`. The real node returns `"topic_planning"`, `"wave0"`, `"wave1"`, or `"exhausted"`.

Why TOPIC goes to wave0, not topic_planning: the topic planner always generates topics from the full HITL1 profile — it has no "retain some topics, re-plan others" mode. Routing TOPIC through topic_planning would cause it to regenerate all topics, overwriting the retained set. Instead, the rerun node creates scoped WorkSpecs for the target topics and routes directly to wave0, bypassing the topic planner entirely. Only FULL rerun goes through topic_planning (the user wants to rethink the topic decomposition itself).

Why closed set: the architecture plan (master line 281) requires all bounded repair/rerun budget exhaustion to enter a `BLOCKED` terminal state. No open-ended "let the model decide where to go" — the rerun node is a deterministic router.

### Decision 4: Work-unit kernel reuse for scoped WorkSpecs (TOPIC and FINDING only)

For `TOPIC` and `FINDING` scopes, the rerun planner generates `WorkSpec` entries through the same shared work-unit controller used by wave0 and wave1 planners. Topics/findings outside the rerun scope retain their existing accepted submissions. The planner sets `pending_work_ids` on checkpoint state; the graph's fan-out/fan-in component picks them up on the next superstep.

For `FULL` scope, the rerun node does NOT generate WorkSpecs — it routes to `topic_planning`, which regenerates the topic registry and creates WorkSpecs through its normal path. The rerun node only clears derived projections and increments generation for FULL.

**Downstream planner impact:** For TOPIC scope, the rerun node writes an `active_topic_filter` field to checkpoint state before routing to `wave0`. For FINDING scope with stale sources (route `wave0`), the filter contains the parent topic IDs of the target findings. For FULL scope, the filter is set to empty tuple `()`. The wave0 planner (`materialize_wave0_intents`) accepts an optional `topic_filter` parameter: when non-empty, it only creates `WorkIntent`s for matching topic IDs. The wave1 planner receives the same filter. This is a minimal, backward-compatible addition — when `topic_filter` is `None`/empty, both planners behave exactly as before. The rerun node's spec and tasks cover these planner changes.

**Filter lifecycle:** `active_topic_filter` is set by the rerun node and read by wave0/wave1 planners. After wave1 gate passes, the field is no longer consulted (wave2_synthesis reads all accepted submissions regardless). On a subsequent rerun, the rerun node overwrites it. Stale filter values from a previous rerun cycle are harmless — the rerun node always sets a fresh value before routing.

Why: the work-unit kernel (change 04) already provides immutable WorkSpec creation, bounded Send fan-out, deterministic submit, and ledger append. The rerun node should not create a second work dispatch path for FULL reruns, and for TOPIC/FINDING it should reuse the existing kernel rather than inventing a new mechanism.

### Decision 5: Generation ceiling moves from lifecycle constant to graph policy; validation happens in the rerun node, not __post_init__

`MAX_FAKE_RERUN_GENERATIONS = 2` is replaced by a `max_rerun_generations` field in the graph execution policy, threaded through `NodeBuildDependencies` to the rerun node factory. The ceiling check moves from `ResearchCheckpoint.__post_init__` (which has no access to policy context at construction time) to the rerun node itself: if `generation >= max_rerun_generations`, the node routes to `exhausted`.

`ResearchCheckpoint.__post_init__` retains the `generation >= 0` lower-bound check but removes the hardcoded `<= MAX_FAKE_RERUN_GENERATIONS` upper bound. The fake continues to use the existing constant for its own ceiling check inside `fake.py`.

Why: a frozen dataclass's `__post_init__` runs at object construction, which happens inside checkpoint deserialization — well before any node factory receives `NodeBuildDependencies`. Pushing the policy-dependent ceiling check into the rerun node keeps validation where the policy context is available, while the structural invariant (`generation >= 0`) stays at the data layer.

### Decision 6: New state fields are additive with safe defaults

New fields (`rerun_scope`, `rerun_reason`, `parent_generation`) are added to `ResearchCheckpoint` with default values (`None`, `""`, `-1`). `RESEARCH_STATE_SCHEMA_VERSION` is not bumped because all new fields have backward-compatible defaults and no existing field semantics change.

Why: schema version bumps force migration. Additive fields with safe defaults preserve existing checkpoints and tests without forced migration logic.

## Risks / Trade-offs

- **[Risk] HITL2 response may not contain enough structured data to derive RerunScope.** → Mitigation: if the HITL2 rerun payload is missing scope metadata, default to `FULL` scope (safest, most conservative).
- **[Risk] Retained topics may reference synthesis/findings that were invalidated.** → Mitigation: the topic registry and accepted submission refs are NOT invalidated — only the synthesis projection is cleared. Retained topics' evidence remains in the ledger.
- **[Risk] `finding`-scope rerun may bounce between wave0 and wave1 incorrectly.** → Mitigation: the rerun planner checks whether the target finding's sources are from wave0 or wave1 and routes accordingly. If ambiguous, route to `wave0` (more conservative — re-verify sources first).
- **[Trade-off] Full rerun is expensive.** → This is the user's explicit decision at HITL2. The brief must communicate the cost before the user chooses rerun.
- **[Risk] In-flight workers from old generation may complete after rerun.** → Mitigation: the work-unit kernel (change 04) rejects submissions whose work_id isn't in the current generation's `pending_work_ids`. Old-generation workers will fail to submit, producing orphaned attempt records that are harmless. Explicit cancellation of old-generation workers is deferred to change 17 (runtime operations).
- **[Risk] TOPIC rerun gate reset loses per-topic attempt history.** → When gate state is reset for a TOPIC-scoped rerun, the granular per-topic attempt history from the previous generation is cleared. The gate re-evaluates the target topic from attempt 0 alongside the retained topics' pre-existing accepted submissions. If the target topic's new sources are weak, the gate may exhaust repair budget faster than in a fresh run. Mitigation: the gate's `repair_budget_by_phase` is reset to its configured default (not zero), giving the rerun the same repair budget as a fresh run. The loss of fine-grained history is acceptable because the rerun is a deliberate fresh start for the target topics.
- **[Risk] `repair_counts` is a fake-era field; real gate uses `gate_attempts_by_phase`.** → The rerun node's invalidation step clears `repair_counts` (for backward compatibility with mixed-graph tests that still touch the fake code path) in addition to the real gate state fields. This is a no-op in pure-real mode but prevents stale data in mixed-mode tests.

## Open Questions

- **TOPIC and FINDING scopes depend on HITL2 brief enhancement.** The current HITL2 brief builder (change 13) produces a flat summary without structured scope metadata (which topics/findings to rerun). Until the brief is enhanced to expose per-topic/per-finding rerun options, all reruns will default to `FULL` scope. The rerun node's scope-extraction logic and the downstream `topic_filter` mechanism are implemented in change 14; they become exercisable when HITL2 is updated.
- Whether the HITL2 brief should include per-topic rerun cost estimates. Deferred to change 15 (readiness) which owns the decision-brief format.
- Whether `max_rerun_generations` should be per-research or global. Start with a global policy default; per-research override deferred.
