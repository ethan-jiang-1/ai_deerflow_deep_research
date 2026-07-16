## Why

Final delivery is the terminal graph node. It transforms the readiness-approved report plan into publishable artifacts. The fake returns a terminal COMPLETED fixture. With readiness (change 15) now real, final delivery must consume the report plan, produce report.md + claim-citation-map, verify integrity via a gate, and publish.

## What Changes

- Replace fake final delivery with real: deterministic writer, integrity gate, terminal lifecycle.
- Writer: deterministic formatter projecting the report plan into report.md + claim-citation-map.json. LLM writer agent deferred (follows change 09 critic pattern).
- Integrity gate: checks report artifacts exist and evidence is present. Self-repair loop (repair → final_delivery) for missing artifacts. Evidence blocked (evidence_blocked → readiness) for missing evidence.
- Completed lifecycle idempotent after gate pass.
- Publish to outputs path deferred to sandbox write capability.

## Capabilities

### New Capabilities

- `final-delivery-node`: Real final writer, integrity gate, and terminal lifecycle. Requirement IDs: FID-001 through FID-005.

## Impact

- **Source**: extend `graph/nodes/final_delivery/node.py`, new `graph/nodes/final_delivery/writer.py`, new `graph/nodes/final_delivery/gate.py`.
- **Typed state**: writes `report_refs` (ContentRef tuple). Reads `readiness_report_plan`, `accepted_submission_refs`.
- **Graph**: real final delivery gate wired in builder. Topology unchanged.
- **Non-goals**: no web tools on writer. No `backend`/`frontend` changes. Publish to outputs deferred.
