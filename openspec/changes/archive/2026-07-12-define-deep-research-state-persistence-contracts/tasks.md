Execution order is a hard dependency chain: groups 1 -> 2 -> ... -> 9. Each behavior
task pairs a red deterministic test with its green implementation. Requirement IDs
covered appear in parentheses; annotate the owning implementation surface with
`@impl REG-xxx`. No files under `backend/` or `frontend/` are modified.

## 1. Red State-Contract Tests

- [x] 1.1 Add red unit tests asserting a typed `ResearchState` exists in `domain/state.py` with `identity`/`request`/`control`/`planning`/`work`/`quality`/`delivery` blocks (control carrying `gate_attempts_by_phase`/`repair_budget_by_phase`; work carrying `work_status_by_id` closed to the `WorkStatus` enum), that identity is reducer-rejected from nodes/workers, and that at most one `phase` and `waiting_for` hold at once. (`REG-006`)
- [x] 1.2 Add red reducer tests: terminal `work_status` monotonicity, `generation` monotonic non-decrease, exactly-one terminal winner, same-hash idempotency, different-hash `conflict`, `accepted_submission_refs` dedupe-append, and rejection of worker/planner/repair writes to `latest_gate_feedback`, `gate_attempts_by_phase`, `repair_budget_by_phase`, `phase`, or `accepted_submission_refs`. (`REG-007`)
- [x] 1.3 Add red tests that oversized serialized state is rejected and that large content is represented only as a `ContentRef` (path/hash/schema-version/summary). (`REG-008`)
- [x] 1.4 Add red tests that an unsupported `ResearchState.schema_version` returns `schema_unsupported` and that no silent reset or auto-migration occurs. (`REG-011`)

## 2. Typed ResearchState And Reducers

- [x] 2.1 Implement `domain/state.py`: `ResearchState` `TypedDict` with `Annotated` reducers, `ResearchCheckpoint` frozen validator, `WorkStatus` enum, `ContentRef`, `RESEARCH_STATE_SCHEMA_VERSION = 2`, and `MAX_CHECKPOINT_STATE_BYTES`; reuse `LogicalPhase` and `TerminalReason` from `domain/lifecycle.py`. (`REG-006`, `REG-011`) `@impl REG-006` `@impl REG-011`
- [x] 2.2 Implement reducers: terminal monotonicity, `generation` monotonic non-decrease, one-terminal-winner, same-hash idempotency, different-hash conflict, ref dedupe-append, gate-feedback/gate-attempt/repair-budget/phase/accepted-refs sole-writer, and identity-write rejection. (`REG-007`) `@impl REG-007`
- [x] 2.3 Implement the hard checkpoint-size bound rejecting oversized serialized state and the `ContentRef`-only rule for large content. (`REG-008`) `@impl REG-008`
- [x] 2.4 Make tasks 1.1-1.4 green. (`REG-006`, `REG-007`, `REG-008`, `REG-011`)
- [x] 2.5 Add a module-level writer/reader/reducer ownership table in `domain/state.py` covering every `ResearchState` field, and a contract test asserting the table covers every declared field. (`REG-006`) `@impl REG-006`

## 3. Bundle Layout, Path Containment, And Three-Authority Boundary

- [x] 3.1 Add red tests that `domain/bundle.py` declares the minimal `<research_id>`-rooted layout, rejects out-of-root worker writes, and treats `diagnostics/gate-attempts.jsonl` as audit-only. (`REG-010`)
- [x] 3.2 Implement `domain/bundle.py`: bundle layout constants, path-containment helper, canonical-URL dedupe, audit-only diagnostics contract. (`REG-010`) `@impl REG-010`
- [x] 3.3 Add red tests asserting the three-authority boundary: no second phase-cursor file, and file existence / worker text / `running` status do not count as a validated submission. (`REG-009`)
- [x] 3.4 Declare the three-authority boundary and the `accepted_submission_refs` dedupe-append slot with sole-writer ownership; define the slot only, no ledger storage. (`REG-009`) `@impl REG-009`

## 4. Migrate Fake Graph And Runtime Off Skeleton State

- [x] 4.1 Add red tests that `StateGraph` binds `ResearchState` and that `graph/skeleton_state.py` is removed. (`REG-006`)
- [x] 4.2 Migrate `graph/builder.py` to bind `ResearchState`; update `engine/fake_control.py` `node_update` and `bounded_repair_update` to write typed state. (`REG-006`) `@impl REG-006`
- [x] 4.3 Update `runtime/research.py` `_checkpoint` projection and initial-state write to `ResearchState` / `ResearchCheckpoint`; preserve `derive_research_id`, `derive_research_thread_key`, start/resume idempotency, `THREAD_RESEARCH_EXISTS`, and the `schema_unsupported` mapping. (`REG-006`, `REG-011`) `@impl REG-006` `@impl REG-011`
- [x] 4.4 Remove `graph/skeleton_state.py`; rename `tests/unit/test_skeleton_contracts.py` to `test_state_contracts.py` and update assertions to the typed state. (`REG-006`)
- [x] 4.5 Verify every change-01 fake route, HITL interrupt, terminal marker, and restart-resume path is unchanged via `tests/graph/test_research_graph.py` and `tests/integration/test_public_entry_replay.py`. (`REG-001`, `REG-002`, `REG-003`, `REG-004`, `REG-005`)

## 5. Per-Backend Namespace And Isolation Contract Tests

- [x] 5.1 Add `tests/integration/test_state_persistence.py` reusing `test_provider_durability.py` fixtures (`_sqlite_config`, `_memory_config`, `_envelope`, subprocess fixtures): typed-state checkpoint write/read for memory, file-SQLite, and Postgres (`@pytest.mark.postgres` deferred). (`REG-005`, `REG-006`)
- [x] 5.2 Assert research / infra-probe namespace isolation, cross-scope isolation, and Postgres multi-worker namespace/isolation hold for the typed state across providers (Postgres cases under `@pytest.mark.postgres`, deferred when the profile is absent). (`REG-005`, `RUI-003`)

## 6. Restart, Resume, Duplicate, And Parallel Reducer Property Tests

- [x] 6.1 Add cross-restart property tests: file-SQLite restart resumes the same `ResearchState` via `tests/fixtures/sqlite_research_subprocess.py`; run `make test-durability`. (`REG-005`, `REG-006`)
- [x] 6.2 Add duplicate-update and parallel-reducer property tests (parametrized pytest) covering restart, resume, duplicate update, and concurrent-reducer order independence. (`REG-007`)

## 7. Documentation Sync

- [x] 7.1 Update `agent/AGENTS.md` to record that `domain/state.py` is the canonical state authority, `graph/skeleton_state.py` is removed, and the writer/reader/reducer declaration rule applies to future field additions. (`REG-006`)
- [x] 7.2 Update `agent/README.md` and `_backlog/plans/deep-research-02-state-persistence-contracts.md` status to reflect the frozen contracts. (`REG-006`, `REG-007`, `REG-008`, `REG-009`, `REG-010`, `REG-011`)

## 8. Format, Lint, Test, Config Surface, And Infra Probe

- [x] 8.1 Confirm no `config.yaml`, `extensions_config.json`, public/custom skill, per-user Agent, MCP, ACP, or `task` subagent surface is changed; `make doctor` startup inputs are unaffected. (`REG-006`..`REG-011`)
- [x] 8.2 Run `cd agent && make format` and `make lint` (ruff); resolve all findings. (`REG-006`..`REG-011`)
- [x] 8.3 Run `cd agent && make test` (unit + contract + graph + integration + blocking_io); all green, no skipped-required tests. (`REG-006`..`REG-011`)
- [x] 8.4 Run an environment-appropriate end-to-end research lifecycle (start -> suspend -> resume -> terminal) through the reflected `deep_research` tool, confirming the typed `ResearchState` checkpoint write/read path; the independent `infra_probe` remains an unchanged diagnostic. (`REG-003`, `REG-004`, `REG-005`, `REG-006`)

## 9. Final Verification And Archive Gates

- [x] 9.1 Run `python3 openspec/governance/check_project_reqs.py` — PASS with no duplicate, unregistered, orphan, or reused-retired IDs. (`REG-006`..`REG-011`)
- [x] 9.2 Run `python3 openspec/governance/check_project_specs.py` — PASS with no delta headers in main specs and no missing purpose, requirements, or requirement-ID header. (`REG-006`..`REG-011`)
- [x] 9.3 Run `openspec validate define-deep-research-state-persistence-contracts --type change --strict`. (`REG-006`..`REG-011`)
