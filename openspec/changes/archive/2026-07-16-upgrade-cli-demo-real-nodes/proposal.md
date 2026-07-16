## Why

The existing `agent/scripts/demo.py` (change 01) runs the full-fake graph end-to-end via CLI without Gateway or model APIs. With changes 00–18 complete, four non-agent nodes can run in real mode without the Gateway agent bridge: hitl2, rerun, readiness, and final_delivery. The demo should support a `--real` flag so users can see the complete pipeline with real control-flow nodes running alongside fake agent nodes — providing a visible, end-to-end demonstration that the graph is wired correctly and the real implementations work.

## What Changes

- Add `--real` flag to `agent/scripts/demo.py`. When set, hitl2, rerun, readiness, and final_delivery run in real mode. All other nodes (bootstrap, hitl1, topic_planning, wave/critic/synthesis/targeted_evidence) remain fake.
- hitl1 and topic_planning cannot run real in the demo — they need the Gateway agent bridge (`capabilities.run_agent()`). bootstrap cannot run real — it needs `bootstrap_bundle` infrastructure. These stay fake, which is acceptable: the demo goal is showing the control-flow pipeline, not exercising agent-internal logic.
- The demo bypasses `ResearchGraphRecipe.create()` dependency checks, using `build_research_graph()` directly with a complete 11-entry implementation_modes dict (all nodes default to "fake", four overridden to "real"). A minimal `ResearchGraphRecipe(requires_work_units=True)` wraps the graph. This avoids the transitive real-mode requirement chain.
- Add `demo-real` target to agent Makefile.

## Capabilities

None — this is a demo/UX change, not a graph capability change. No new requirement IDs.

## Impact

- **Source**: modify `agent/scripts/demo.py` (~20 lines), `agent/Makefile` (~3 lines).
- **Graph**: no topology or node changes.
- **Non-goals**: no backend/frontend changes. TUI demo is a separate change. Agent nodes stay fake.
