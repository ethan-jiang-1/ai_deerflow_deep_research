## Why

The HITL2 node already supports a `rerun` user decision with the graph edge `hitl2 -> rerun -> topic_planning`, and the fake rerun node mechanically bumps generation by 1. But the fake has no concept of rerun scope (what to redo vs retain), no invalidation of derived projections from the old generation, no integration with the work-unit kernel to spawn revised WorkSpecs, and no lineage tracking. With wave0 through targeted-evidence and HITL2 all real, users can now make an informed rerun decision — the rerun node must honour it with scoped, traceable re-execution rather than a blind full restart.

## What Changes

- Replace the fake rerun node with a real implementation that parses the HITL2 rerun decision payload, extracts typed scope (full rerun, per-topic, per-finding), and produces a deterministic `RerunPlan`.
- `generation += 1` monotonic update; the old submission ledger and raw evidence artifacts remain append-only — only derived projections (synthesis, decision brief, report plan) are invalidated.
- The rerun planner materializes new or revised `WorkSpec`s through the existing work-unit kernel for scoped rework; topics/findings outside the rerun scope retain their accepted evidence and are not re-executed.
- Back edges are a closed set determined by rerun scope: `full` routes to `topic_planning` (re-plan from scratch); `topic` routes to `wave0` (scoped source intake, bypassing the topic planner); `finding` routes to `wave0` (if source intake is stale) or `wave1` (if only deep evidence is affected).
- New generation must re-pass all affected wave gates and a fresh HITL2; the old generation's HITL2 `proceed` decision is not inherited.
- `MAX_FAKE_RERUN_GENERATIONS` constraint is lifted for real mode (replaced by a configurable `max_rerun_generations` budget in graph policy); `ResearchCheckpoint.__post_init__` validation is updated accordingly.
- Generation lineage (`parent_generation`, `rerun_reason`, `rerun_scope`) is written to checkpoint state and traceable in final diagnostics.

## Capabilities

### New Capabilities

- `rerun-node`: Real rerun planner with scoped invalidation, generation increment, WorkSpec materialization via work-unit kernel, and closed-set back edges. Requirement IDs: REN-001 through REN-007.

### Modified Capabilities

None. Existing specs are unchanged — the HITL2 spec already defines the `rerun` decision route and the research-graph-lifecycle spec already defines the rerun node's existence in the topology. This change swaps the implementation from fake to real without altering those contracts.

## Impact

- **Source**: extend `graph/nodes/rerun/node.py` (real factory currently `UNAVAILABLE_REAL_FACTORY`), new `graph/nodes/rerun/planner.py` (deterministic rerun planner), extend `graph/nodes/rerun/contracts.py` (new typed `RerunScope`, `RerunPlan`), update `graph/nodes/rerun/__init__.py` (revised `NODE_SPEC` contracts).
- **Typed state/checkpoint data**: rerun node reads `generation`, `hitl2_rerun_payload` (scope metadata from HITL2; defaults to FULL when absent), `accepted_submission_refs`, `topic_registry`; writes `generation` (incremented), `rerun_scope`, `rerun_reason`, `parent_generation`, `active_topic_filter` (scoped rerun only), `pending_work_ids` (new/revised WorkSpecs for TOPIC/FINDING only), invalidates `synthesis_ref`, `decision_brief_ref`, `report_refs`, `repair_counts` (cleared for backward compat). `RESEARCH_STATE_SCHEMA_VERSION` not bumped — new fields are additive with safe defaults.
- **Graph nodes/components**: `rerun` swaps from fake to real. `wave0` and `wave1` planners receive an optional `topic_filter` parameter (backward-compatible: `None` means all topics). Topology unchanged.
- **Node-agent roles**: none. Rerun planner is code-only — no `capabilities.run_agent()`.
- **Sandbox artifacts**: none written by this node. Rerun plan is checkpointed control state only; derived artifact invalidation is a state operation (clearing refs), not file deletion.
- **DeerFlow extension surfaces**: none added, none modified.
- **Non-goals**: no files under `backend/` or `frontend/` are modified. No multi-generation branching or parallel active generations. No late-submit cross-generation acceptance. No rerun budget policy beyond a hard `max_rerun_generations` ceiling — fatigue/heuristic escalation belongs to the HITL2 decision brief, not the rerun node.
