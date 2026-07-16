## Why

The readiness node is the last quality gate before report writing. It sits between HITL2(proceed) and final_delivery in the graph topology. The fake returns a no-op update; a fixture gate provides the route. With wave0 through rerun all real, the system has accepted evidence, critic verdicts, synthesis findings, and a valid HITL2 decision — readiness must now verify answerability, check citation closure, and produce an immutable report plan so the final writer only receives deliverable evidence.

## What Changes

- Replace the fake readiness node with a real implementation that runs hard (deterministic) and semantic (agentic) quality checks, then writes its own route — like hitl2 and rerun, readiness is a non-gated node that determines its own routing.
- Hard checks: citation availability (accepted submissions non-empty), provenance (valid ref format), HITL2 consumption (at least one HITL request consumed).
- Semantic check: a bounded read-only agent loop — the "readiness critic" — assessing answerability per must-answer question. Initial implementation uses a deterministic fallback; the real agent loop follows the evidence critic pattern (change 09).
- A deterministic report plan materializer projects critic verdicts + hard-rule results into an immutable contract: writable conclusions, mandatory uncertainties, and prohibited claim upgrades. The plan is checkpointed as a ContentRef.
- The node determines the route: `pass` when the report plan is viable, `repair_targeted` when evidence gaps block answerability, `exhausted` when structural preconditions fail (no evidence, no HITL2).

## Capabilities

### New Capabilities

- `readiness-node`: Real readiness assessment with hard structural checks, semantic answerability critic, and immutable report plan generation. Requirement IDs: REA-001 through REA-007.

### Modified Capabilities

None. The topology edges and ReadinessVerdict enum are unchanged.

## Impact

- **Source**: extend `graph/nodes/readiness/node.py`, new `graph/nodes/readiness/hard_rules.py`, new `graph/nodes/readiness/critic.py`, new `graph/nodes/readiness/materializer.py`, extend `graph/nodes/readiness/contracts.py`.
- **Typed state**: readiness reads `must_answer_questions`, `accepted_submission_refs`, `generation`, `consumed_request_ids`; writes `readiness_hard_failures` (tuple of dicts), `readiness_critic_summary` (dict), `readiness_blocked_count` (int), `readiness_report_plan` (ContentRef), `route` (self-determined, like hitl2/rerun). `RESEARCH_STATE_SCHEMA_VERSION` not bumped.
- **Graph**: no gate definition for readiness in builder (non-gated node). Topology edges unchanged; the `repair_synthesis` and `repair_hitl2` edge keys exist in the topology but are deferred — initial implementation routes all repair to `repair_targeted`.
- **Node-agent roles**: readiness critic — bounded read-only agent loop, no web tools. Pattern matches evidence critics (change 09).
- **DeerFlow extension surfaces**: none.
- **Non-goals**: no final report writing. No `backend` or `frontend` changes.
