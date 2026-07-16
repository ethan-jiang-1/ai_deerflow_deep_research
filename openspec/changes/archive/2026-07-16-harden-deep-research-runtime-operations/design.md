## Context

Change 17 is cross-cutting runtime hardening. It modifies the tool entry point, HITL nodes, and the graph wrapper — but does not change graph topology or add new phases.

Current state:
- `tool.py:141-148`: non-interactive start/resume is hard-denied with `INTERACTIVE_REQUIRED`
- `runtime/events.py`: `build_progress_event` and `ProgressEmitter` exist but are only wired for agent-level events (bridge), not graph-level phase transitions
- Work-unit replay: the ledger reconciliation handles idempotent replay but doesn't explicitly detect orphaned in-flight attempts

## Goals / Non-Goals

**Goals:**
- Non-interactive policy: allow scheduled runs with auto-profile + auto-proceed; deny without policy
- HITL1: auto-generate default profile when `auto_profile=True`
- HITL2: auto-proceed with limitations when `auto_proceed=True`
- Orphan detection: on crash recovery, mark stale in-flight attempts as failed
- Note: progress events are already emitted by `node_update()` in `fake_control.py` — every real node calls this, appending `logical_name` to `execution_trace`. No additional work needed.

**Non-Goals:**
- No Postgres multi-worker. No backend/frontend changes. No topology changes.

## Decisions

### Decision 1: Non-interactive policy flows from tool context → action input → initial state

The policy is passed from the runtime context dict (tool.py) into `ResearchActionInput.non_interactive_policy`, then injected into the initial graph state by `StartResearchHandler._invoke_graph` at line 494. Once in state, it's visible to all nodes via checkpoint, including HITL nodes. Format: `{"auto_profile": bool, "auto_proceed": bool, "reason": str}`.

Flow: `runtime.context["non_interactive_policy"]` → `ResearchActionInput` → `values["non_interactive_policy"]` → checkpoint state.

Why state vs runtime flag: runtime flags are ephemeral and lost on restart. State fields survive checkpoint/recovery, so a scheduled run that crashes at HITL1 can resume and still auto-respond.

### Decision 2: HITL1 auto-profile generates default profile values

When `non_interactive_policy.auto_profile` is True, HITL1 skips `interrupt()` and writes default profile values (`research_depth="standard"`, `target_audience="practitioner"`, etc.) plus `degraded_profile=True` and a note in `execution_trace`. The profile is valid but marked as auto-generated.

### Decision 3: HITL2 auto-proceed routes to proceed with limitations

When `non_interactive_policy.auto_proceed` is True, HITL2 skips `interrupt()` and routes to `proceed`, writing a note that the decision was automated. The `readiness` node (which follows HITL2) will apply its normal quality checks — auto-proceed does not bypass readiness.

### Decision 4: Orphan detection is a work-unit store concern

The `WorkUnitStore` replay path already handles idempotent replay. Orphan detection adds one check: on recovery (replay), any attempt in `running` status whose owning work_spec was created in a prior graph incarnation is transitioned to `failed` with `orphaned` reason. This is a deterministic safety net.

## Risks

- **[Risk] Auto-generated profile may produce low-quality research.** → Mitigation: `degraded_profile=True` is set, visible in audit. The profile uses conservative defaults.
- **[Risk] Auto-proceed may publish low-quality reports.** → Mitigation: readiness (change 15) still runs quality checks after HITL2. Auto-proceed does not bypass readiness gate.
- **[Risk] Orphan detection may mark legitimate in-flight work as orphaned.** → Mitigation: only attempts whose work_spec generation is lower than the current graph generation are considered orphaned.

## Open Questions

- Whether `non_interactive_policy` should be per-research or global. Start as per-research (passed at start time).
