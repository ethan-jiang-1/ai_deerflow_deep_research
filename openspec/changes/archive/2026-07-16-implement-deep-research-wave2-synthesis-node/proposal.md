## Why

Wave0 collects sources, wave1 extracts deep evidence and claims, critics assess quality. But no node synthesises findings across topics — connecting related evidence, identifying contradictions, and surfacing gaps that need targeted follow-up. Wave2 synthesis is the integrative layer: it reads all accepted evidence and critic verdicts, produces structured findings, and declares what's missing.

## What Changes

- Replace the fake wave2_synthesis node with a real read-only synthesis agent: reads accepted claims/verdicts/limitations from prior phases, produces structured findings with cross-topic relations and candidate gaps.
- The synthesis agent runs under a zero-tool read-only ExecutionPolicy. It cannot fetch new sources — gaps are recorded, not auto-resolved.
- Structured output: finding index (priority, affected topics, backing refs, confidence, search_required), cross-topic relations, contradictions, resolutions.
- Deterministic materializer writes synthesis.md, finding-index.json, and cross-topic ledger to sandbox.
- Hard gate validates references and structure; real gate replaces fixture gate.
- Real synthesis requires full real chain through wave1. Topology and full-fake path unchanged.

## Capabilities

### New Capabilities
- `wave2-synthesis-node`: Cross-topic synthesis agent with read-only policy, structured findings, and gap detection. Requirement IDs: WSN-001 through WSN-004.

### Modified Capabilities
None.

## Impact

- **Source**: extend `graph/nodes/wave2_synthesis/` with prompts and real factory. New files: `domain/synthesis.py` (output models), `graph/nodes/wave2_synthesis/prompts.py`. New files registered via PRS-004.
- **DeerFlow extension surfaces**: none added.
- **Non-goals**: no targeted evidence execution, no HITL2 decision, no report prose. No files under backend/ or frontend/.
