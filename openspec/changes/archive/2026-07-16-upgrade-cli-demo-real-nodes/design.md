## Context

`agent/scripts/demo.py` runs the full-fake graph lifecycle without Gateway. It uses `DemoAdapter` (in-process adapter, no server) and `ResearchGraphRecipe.create()` (all nodes fake). The demo flow: start → HITL1 interrupt → resume → HITL2 interrupt → resume → terminal.

The `--scripted` flag provides deterministic HITL answers so the demo can run unattended.

## Goals / Non-Goals

**Goals:** add `--real` flag to run hitl2, rerun, readiness, final_delivery in real mode. Full-fake mode unchanged.

**Non-Goals:** no Gateway-dependent agent nodes. No TUI changes. No new graph capabilities.

## Decisions

### Decision 1: Only four nodes run real — hitl2, rerun, readiness, final_delivery

These are code-only nodes that don't call `capabilities.run_agent()`. Verified by grepping their `node.py` files. hitl1 and topic_planning DO call `run_agent()` and stay fake. bootstrap needs `bootstrap_bundle` infrastructure and stays fake.

### Decision 2: Bypass ResearchGraphRecipe.create() dependency checks

`ResearchGraphRecipe.create()` enforces transitive real-mode dependencies (hitl2 real requires wave2_synthesis real, etc.). For the demo, we construct the graph directly via `build_research_graph()` and wrap it in a minimal `ResearchGraphRecipe(requires_work_units=True, work_unit_store_factory=adapter.create_work_unit_store)`. The `work_unit_store_factory` is required — without it, the handler falls back to `WorkUnitStore.create()` which needs Gateway infrastructure and fails in the demo.

### Decision 3: Build a complete modes dict — all 11 nodes must have a mode

`build_research_graph:141` uses `implementation_modes or {name: "fake" for name in LOGICAL_NODES}` — the `or` only triggers when `implementation_modes` is `None`/falsy. Passing a partial dict with only 4 entries causes `resolve_implementations` to fail with `implementation_map_incomplete`.

The demo constructs a complete dict: all nodes default to `"fake"`, then the four real-capable nodes are overridden to `"real"`. This matches the builder's intent — full mode coverage, partial real override.

```python
from deerflow_deep_research.graph.topology import LOGICAL_NODES
modes = {name: "fake" for name in LOGICAL_NODES}
if real:
    modes.update({"hitl2": "real", "rerun": "real", "readiness": "real", "final_delivery": "real"})
```

## Risks

- **[Risk] `build_research_graph` with partial mode dict fails.** → Mitigation: construct a complete 11-entry dict (Decision 3).
- **[Risk] Full-fake regression.** → Mitigation: without `--real`, pass `implementation_modes=None`, triggering the existing default-all-fake path. Test both modes.
