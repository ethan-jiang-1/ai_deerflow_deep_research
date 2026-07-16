## Why

Wave0 collects breadth-first sources per topic, and change 09 provides independent critic assessment. But no node performs *deep* per-topic evidence extraction — gathering claims, counterevidence, and open questions that go beyond the initial source intake. Wave1 is the deep-research workhorse: it searches for new sources beyond Wave0's baseline, extracts structured claims with provenance, runs critics on the new evidence, and enforces a higher coverage floor. Without real Wave1, the pipeline has breadth but no depth.

## What Changes

- Replace the fake Wave1 planner/worker/submit/gate subgraph with a real implementation: a planner that materializes evidence WorkSpecs from profile constraints and Wave0 background, a bounded web worker that searches for new sources and extracts structured claims, a submit validator that enforces `is_new_vs_wave0`, and a gate that consumes both hard provenance and critic verdicts.
- The worker outputs versioned structured documents: claims with support/counter refs, open questions with resolution states, and explicit new-vs-wave0 marking. Wave0-duplicate URLs do not count toward the new-source floor.
- Submit validation runs SourceDiagnostic and ClaimVerifier critics on accepted Wave1 evidence, producing independent verdict artifacts that the gate consumes.
- The Wave1 gate enforces: all planned work drained, per-topic new-source floor met, critic verdicts present, and open questions resolved or explicitly deferred. Repair re-fetches missing topics or downgrades claims; it cannot alter critic verdicts.
- Real Wave1 requires `bootstrap=real`, `hitl1=real`, `topic_planning=real`, `wave0=real`, and `targeted_evidence=real`. Full-fake Wave1 remains unchanged. Topology is unchanged.

## Capabilities

### New Capabilities
- `wave1-node`: Deep per-topic evidence extraction with new-source floor, structured claims, critic integration, and provenance-aware gate. Requirement IDs: WON-001 through WON-006.

### Modified Capabilities
- `work-unit-kernel`: submit validation extended with `is_new_vs_wave0` check and critic invocation hook. Delta spec required.

## Impact

- **Source**: new `graph/nodes/wave1/prompts.py`, replace `graph/nodes/wave1/node.py` real factory, extend `graph/nodes/wave1/subgraph.py` with real worker/integration. Extend `engine/work_units/validation.py` with WON-specific checks. New files registered via PRS-004.
- **Typed state/checkpoint data**: Wave1 writes work-unit state fields already defined (work_specs_by_id, attempts_by_id, etc.). No new checkpoint fields. `RESEARCH_STATE_SCHEMA_VERSION` not bumped.
- **Graph nodes/components**: only `wave1` swaps from fake to real in mixed graph; topology unchanged (`repair`/`pass`/`exhausted`).
- **Node-agent roles**: one bounded web worker agent per in-flight attempt through `capabilities.run_agent()` under real `ExecutionPolicy` with web search/fetch tools and attempt-scoped roots.
- **Sandbox artifacts**: worker writes `result.json` + outputs + fetched/cache content under `work/<work_id>/<attempt_id>/`.
- **DeerFlow extension surfaces**: none added. No new config/skills/Agent/SOUL/MCP/ACP.
- **Dependencies**: no new third-party deps. Tests use `ReplayChatModel`.
- **Non-goals**: no cross-topic synthesis or targeted Wave2 search; no final report. No files under `backend/` or `frontend/`.
