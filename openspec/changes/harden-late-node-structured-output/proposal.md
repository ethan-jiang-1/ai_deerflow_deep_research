## Why

The new focused live canaries exposed two production-contract mismatches below the full pipeline: Wave2 is prompted to mark missing evidence for follow-up, but canonical gaps cannot carry the `search_required` field consumed by the targeted router; and a targeted worker that completes tool use with a prose or otherwise schema-invalid answer has no bounded structured-output repair path. Both failures correctly stop publication today, but together they prevent the late-node real chain from completing against an observed provider while leaving the existing deterministic suites green.

## What Changes

- Make `search_required` an explicit canonical `GapRecord` field and align the Wave2 initial/repair prompts, provider-shape normalization, persisted synthesis artifact, typed gate preview, gate-owned searchable-gap-id projection, and targeted gap routing around that authority chain.
- Replace the real Wave2 pass-through gate rule with a deterministic rule that routes `evidence_needed` exactly when the validated node output contains searchable gaps, while keeping complete gap bodies out of checkpoint state.
- Add the missing Wave2 `exhausted -> blocked/END` terminal edge so repeated unresolved semantic gaps follow the existing gate budget/fatigue contract instead of producing an unmapped blocked verdict.
- Add one node-owned, zero-tool structured-output repair attempt for a targeted worker whose first successful agent result cannot be parsed, validated as `TargetedWorkerOutput`, or bound to the assigned gap id.
- Keep repair bounded by the existing node-agent budget, preserve the assigned gap identity, exclude untrusted draft prose from instruction authority, and fail closed after one unsuccessful repair without publishing result artifacts, source artifacts, or ledger records.
- Add deterministic regression coverage for the two observed provider shapes, authority non-publication, call/tool bounds, and the existing valid-first-response path.
- Align the focused Wave2 live assertion with the real two-route gate contract: current validated searchable gaps require `evidence_needed`; no searchable gap requires `pass`.
- Re-run the six focused live cases with fresh identities after deterministic gates pass; restore nightly scheduling only if the complete lane passes within the already approved aggregate deadline and five-minute job margin.
- Do not add another full-pipeline E2E or change the public Deep Research entry, graph topology, checkpoint ownership, DeerFlow backend, or frontend.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `wave2-synthesis-node` (`WSN-001`, `WSN-002`, `WSN-003`): make follow-up intent a canonical gap field and require prompt, normalization, persistence, typed gate preview, real gate routing, and downstream projection to preserve it consistently.
- `targeted-evidence-loop` (`TEL-001`, `TEL-002`): add exactly one bounded structured-output repair attempt after an otherwise successful targeted worker response fails parsing or schema validation, with fail-closed publication semantics.
- `research-graph-lifecycle` (`REG-001`): add the missing Wave2 exhausted terminal route required by the existing gate kernel when targeted-evidence convergence does not clear a searchable gap.

## Impact

- Production code changes are limited to project-owned Deep Research surfaces under `agent/src/deerflow_deep_research/domain/`, `agent/src/deerflow_deep_research/engine/`, and `agent/src/deerflow_deep_research/graph/` for the Wave2 gate and targeted worker path.
- Focused deterministic tests under `agent/tests/{domain,graph,integration}/` will cover schema compatibility, repair behavior, budgets, and authority publication. Existing provider-shape assets and live canaries may be extended only as needed to bind the observed failures to those production seams.
- The active `rebalance-deep-research-test-assets` change remains the owner of live-reporting and nightly-lane governance. This change supplies the production fixes; its six-case pass, scheduling decision, and final completion remain recorded there.
- `backend/`, `frontend/`, release/public-entry code, runtime configuration, dependencies, database/checkpoint schemas, and sandbox layout are unchanged. The normalized topology gains only `wave2_synthesis --exhausted--> blocked`; existing nodes and all other edges remain unchanged. Existing synthesis JSON remains schema version 1; adding a defaulted boolean is backward-compatible for readers and old artifacts.
