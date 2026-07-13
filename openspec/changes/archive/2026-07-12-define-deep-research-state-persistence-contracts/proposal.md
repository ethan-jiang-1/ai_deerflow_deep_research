## Why

Change 01 delivered the fake graph skeleton with a temporary `SkeletonState` /
`SkeletonCheckpoint` payload whose module self-documents as a stand-in that must
never coexist as an authority with the real state. Changes 03 (gate kernel) and 04
(work-unit kernel) and every real node depend on a frozen state-ownership model:
typed fields, who writes and reads them, which reducers guard them, and where large
content may not live. Without that contract now, downstream work would either fork
the skeleton's ad-hoc `dict` / `TypedDict` shape or silently place large evidence
into the checkpoint. This change freezes the one canonical `ResearchState` authority
and its persistence contracts while reusing the change-00/01 checkpoint pipeline
(versioned namespace isolation, per-action provider lifecycle, fail-closed schema
gate) unchanged.

## What Changes

- Add `domain/state.py` defining one versioned typed `ResearchState` as the canonical
  checkpointed control authority, with `identity`, `request`, `control`, `planning`,
  `work`, `quality`, and `delivery` blocks, and a `schema_version` field governed by a
  fail-closed migration policy.
- Define phase / terminal / waiting / work status enums (including the closed
  `WorkStatus` set `pending | running | submitted | failed | timed_out | cancelled`) and
  the `phase_status`, `waiting_for`, `terminal_status` control model carrying
  `gate_attempts_by_phase` and `repair_budget_by_phase`, reconciling the change-01 single
  `LifecycleStatus` with the three-field control truth while leaving the wire status
  projection unchanged.
- Implement state reducers that enforce: work terminal monotonicity (a terminal status
  cannot be downgraded by a late `running` or stale value); `generation` monotonic
  non-decreasing; exactly one terminal winner per work/attempt; same work/attempt plus
  same content hash = idempotent replay, different hash = conflict (not last-write-wins);
  `accepted_submission_refs` dedupe-append; `latest_gate_feedback`,
  `gate_attempts_by_phase`, and `repair_budget_by_phase` sole-writer (gate node only);
  workers cannot write gate feedback, gate attempts or repair budgets, phase, or accepted
  submissions.
- Codify the content-ref rule: web page bodies, PDFs, full evidence summaries, full
  reports, screenshots, and large tool output never enter the checkpoint — only sandbox
  path, content hash, schema version, and a short summary ref; a hard checkpoint-size
  bound rejects oversized content.
- Declare the three-authority boundary: checkpointed `ResearchState` (control truth),
  the append-only validated submission ledger (evidence truth), and sandbox artifact
  files (content truth); the graph checkpoint is the sole legal execution path with no
  second phase-cursor file; file existence, worker text, or a run event is not a
  validated submission.
- Define the minimal research bundle layout under
  `workspace/deep-research/<research_id>/` and a path-containment contract that scopes
  every worker write to its own attempt directory and controlled cache regions;
  `diagnostics/gate-attempts.jsonl` is audit-only, not a phase cursor.
- Establish the writer/reader/reducer declaration rule: any future `ResearchState`
  field addition MUST explicitly declare its writer, reader, and reducer.
- Migrate the fake graph builder from `graph/skeleton_state.py` to `domain/state.py`
  and remove the skeleton module; fake graph paths and behavior remain unchanged.
- Add per-backend (memory / SQLite / Postgres) namespace/isolation contract tests for
  the typed state, reusing 00/01 provider tests; add reducer property tests (restart,
  resume, duplicate update, parallel reducer) and a hard checkpoint-size test.

No real gate rules, `WorkSpec` content, submission-ledger storage, or real bundle
artifacts are implemented — only the slots, ownership contracts, and fail-closed
version policy they require.

## Capabilities

### New Capabilities

None. The state authority is an extension of the existing `research-graph-lifecycle`
capability, which already owns checkpointed control state via REG-005.

### Modified Capabilities

- `research-graph-lifecycle`: adds the typed `ResearchState` authority, reducer
  invariants, content-ref rule, three-authority boundary, minimal bundle and
  path-containment contract, and versioned fail-closed schema policy
  (REG-006 through REG-011); updates REG-003 and REG-005 to replace stale `skeleton state`
  references with the typed `ResearchState`. REG-005's schema-fail-closed scenario is retained
  (ResearchState wording); REG-011 adds the comprehensive versioned-schema policy.

## Impact

- **Source:** additive under `agent/src/deerflow_deep_research/domain/state.py` (new)
  with reducers colocated there; `graph/builder.py` migrated off `graph/skeleton_state.py`,
  which is removed; `runtime/research.py` checkpoint projection updated to the typed
  state. `backend/` and `frontend/` are not modified.
- **Typed state/checkpoint data affected:** the checkpointed payload changes from the
  change-01 `SkeletonState` / `SkeletonCheckpoint` to `ResearchState`. Existing control
  fields (`research_id`, `start_message_id`, `request_digest`, `phase`, `generation`,
  `execution_trace`, consumed ids, `terminal_reason`, branch summaries, and the fake-specific
  `fixture_plan`, `route`, `terminal_fixture_marker`, `repair_counts`) are preserved in typed
  form so fake-graph paths are unchanged; the skeleton's single `status` field is
  reconciled into the three-field control model (`phase_status` / `waiting_for` /
  `terminal_status`) with the wire status projection unchanged. New slots
  (`work_specs_by_id`, `work_status_by_id`, `accepted_submission_refs`,
  `latest_gate_feedback`, `gate_attempts_by_phase`, `repair_budget_by_phase`, delivery
  refs) are defined with ownership but left unpopulated by the fake graph.
- **Graph nodes/components affected:** no node behavior change; node update helpers in
  `engine/fake_control.py` write the typed state instead of the skeleton dict; the
  topology and typed routers are unchanged.
- **Node-agent roles used:** none new. The runtime-owned bridge and
  `TrustedRuntimeEnvelope` are unchanged; raw binding data remains outside checkpoint
  state and is never model input.
- **Sandbox artifacts read/written:** none by the fake graph. The bundle layout and
  path-containment contract are defined as contracts only; real artifact writes arrive
  with later changes.
- **DeerFlow extension surfaces used:** none new and none modified. The reflected
  `deep_research` tool, `deep-research-control` tool group,
  `deep-research-controller` public skill, and dedicated Agent template are unchanged;
  no `config.yaml`, `extensions_config.json`, MCP, ACP, or DeerFlow `task` subagent
  surface is touched.
- **Reload boundary:** source-only change under `agent/src/`; takes effect on the next
  agent build. No `config.yaml` / `extensions_config.json` / skill / Agent / database /
  checkpointer / sandbox change, so no `STARTUP_ONLY_FIELDS` impact and no Gateway
  restart is required.
- **Dependencies:** no new runtime dependency. Reducer property tests use parametrized
  pytest (the existing pattern); `hypothesis` is not added.
- **Non-goals:** no real gate rules, `WorkSpec` content, submission-ledger storage, or
  real bundle artifact writes; no business state migration — only the version field and
  fail-closed contract; no files under `backend/` or `frontend/` are modified.

The new requirement IDs are REG-006, REG-007, REG-008, REG-009, REG-010, and REG-011;
REG-003 and REG-005 are modified.
