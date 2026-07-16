## Why

HITL2 is the final human decision gate before delivery. The existing fake already
implements a complete interrupt/resume pipeline with `PendingResearchInterrupt`,
`Hitl2Decision` routing, `AcceptedHumanResponse` validation, and cancellation
handling — but it presents fixture text ("no real research findings exist"). With
Wave0 through targeted-evidence now real, HITL2 must present actual accepted
findings to the user and route based on their informed decision.

## What Changes

- Replace the fixture briefing text in HITL2 with a deterministic brief builder that
  reads accepted findings, synthesis gaps, and critic verdicts from checkpoint state.
- The existing interrupt/resume/validation pipeline (`PendingResearchInterrupt`,
  `HumanInputRequest` in CHOICE mode, `Hitl2Decision` enum, `AcceptedHumanResponse`,
  `InternalCancelDecision`) is reused unchanged — the fake IS the real pattern.
  The `request_id` (encoding generation) already provides stale-resume detection.
- Recipe dependency: `hitl2=real` requires `wave2_synthesis=real` (transitively the
  full chain through wave0/wave1/targeted_evidence).
- No LLM call, no sandbox writes, no new tools or capabilities. Topology unchanged.

## Capabilities

### New Capabilities
- `hitl2-node`: Real human decision node with deterministic brief builder and
  interrupt/resume lifecycle. Requirement IDs: HIT-001 through HIT-003.

### Modified Capabilities
None. Existing specs are unchanged.

## Impact

- **Source**: extend `graph/nodes/hitl2/node.py` (real factory already has scaffolding;
  enhance to use the brief builder + proper state management). No new files.
- **Typed state/checkpoint data**: HITL2 reads `accepted_submission_refs`,
  `synthesis_gaps`; writes `consumed_request_ids`, `consumed_message_ids`,
  `terminal_status`, `phase_status` on terminal decisions. No new checkpoint fields;
  `RESEARCH_STATE_SCHEMA_VERSION` not bumped.
- **Graph nodes/components**: only `hitl2` swaps from fake to real in mixed graph;
  topology unchanged.
- **Node-agent roles**: none. HITL2 is code-only — no `capabilities.run_agent()`.
- **Sandbox artifacts**: none written by this node.
- **DeerFlow extension surfaces**: none added.
- **Non-goals**: no rerun invalidation, readiness gate, or final delivery. No files
  under `backend/` or `frontend/` are modified.
