## 1. Domain contracts, state authority, and bundle paths

- [ ] 1.1 Add red deterministic tests in `agent/tests/domain/test_work_units.py` for frozen extra-forbid `WorkSpec`, `Attempt`, `CandidateResult`, and `SubmissionRecord` schemas, canonical JSON/hash stability, controller identity allocation, and worker identity/spec mutation denial. @impl WOU-001
- [ ] 1.2 Implement `agent/src/deerflow_deep_research/domain/work_units.py` with versioned bounded models, closed work/attempt/validation enums, source/output refs, domain-separated object hashes, and pure work-unit capability protocols until task 1.1 is green. @impl WOU-001, WOU-003, WOU-004
- [ ] 1.3 Add red state tests for compatible version-2 old-checkpoint loading, defaulted parent spec/status/cursor/accepted-ref fields, separate bounded transient child pending/in-flight/candidate state, field-specific controller/worker/submit/gate ownership, terminal monotonicity, unknown-version denial, and checkpoint size bounds. @impl WOU-001, WOU-002, WOU-004, WOU-007, REG-007, REG-011
- [ ] 1.4 Compatibly extend version-2 `domain/state.py` with optional/defaulted small parent-state projections and field-specific writer enforcement; keep candidate bodies out of the parent checkpoint and preserve fail-closed rejection of unknown/incompatible versions. @impl WOU-002, WOU-004, WOU-007, REG-006, REG-007, REG-008, REG-011
- [ ] 1.5 Add red bundle tests for canonical spec/result/output/ledger/lock/staging paths, research/attempt containment, symlink escape denial, and audit-vs-authority classification. @impl WOU-003, WOU-004, REG-010
- [ ] 1.6 Extend `domain/bundle.py` with the work-unit and evidence-ledger paths used by the design, preserving the minimal bundle and rejecting DPT queue/index/status files. @impl WOU-003, WOU-004, REG-010
- [ ] 1.7 Add red projection tests for a controller-only per-work dependency resolver whose `NodeAgentContext.attempt_root` is `<research_root>/work/<work_id>/<attempt_id>`, while caller/worker-selected roots and mismatched ids are rejected. @impl WOU-001, WOU-003, NOA-001, REG-010
- [ ] 1.8 Implement the work-unit projection/resolver in `domain/invocation.py`, `runtime/projection.py`, and `runtime/research.py`, retaining the existing phase-level projection until task 1.7 is green. @impl WOU-001, WOU-003, NOA-001, REG-010

## 2. Canonical ledger and runtime-owned atomic store

- [ ] 2.1 Add red domain tests in `agent/tests/domain/test_submission_ledger.py` for bounded canonical newline-terminated JSONL parsing, schema validation, full hash-chain verification, stable candidate replay comparison, duplicate identity detection, partial-tail/oversize denial, and staging non-authority. @impl WOU-004, WOU-005
- [ ] 2.2 Complete the pure ledger codec and replay comparison in `domain/work_units.py`; runtime code SHALL import these domain functions directly and SHALL NOT import `engine/`. @impl WOU-004, WOU-005
- [ ] 2.3 Add red runtime/doctor tests classifying LocalSandbox and local-container AIO as eligible only when workspace aliasing is proven, and E2B, BoxLite, provisioner-backed AIO, custom/unverified providers, or unsupported filesystems as work-unit-storage not ready. @impl WOU-006, DEC-005
- [ ] 2.4 Implement one shared provider/workspace transaction-capability classifier used by runtime store construction and diagnostics, with redacted failures before every work/ledger mutation. @impl WOU-006, DEC-005
- [ ] 2.5 Add red reflected-tool tests proving unsupported storage and lock-deadline exhaustion return distinct typed infrastructure results without graph checkpoint mutation or resource leakage. @impl WOU-006, RUI-006
- [ ] 2.6 Implement `InfrastructureResultCode.WORK_UNIT_STORAGE_UNAVAILABLE`, `WORK_UNIT_STORE_BUSY`, `WorkUnitStoreError`, and tool projection until task 2.5 is green. @impl WOU-006, RUI-006
- [ ] 2.7 Add red runtime-store tests for trusted host-root derivation, verified sandbox/host aliasing, per-research lock keys, bounded nonblocking lock timeout, ledger size/count bounds, mode-0600 staging, file/directory fsync, same-directory atomic replace, lock release on every failure, and no host-path leakage. @impl WOU-004, WOU-006
- [ ] 2.8 Implement `runtime/work_unit_store.py` using the verified `TrustedRuntimeEnvelope.workspace_host_path`, `LOCK_NB` deadline retries, `asyncio.to_thread`, atomic whole-file publication, staging cleanup, and injected clock/fault hooks until task 2.7 is green, without exposing the store to model-facing capabilities. @impl WOU-004, WOU-006
- [ ] 2.9 Add blocking-I/O and cancellation tests proving ledger reads/hashes/locks/commits do not block the event loop, lock acquisition terminates at its deadline, cancellation waits only for a size-bounded acquired commit, and a committed-ledger/missing-checkpoint outcome remains replayable. @impl WOU-005, WOU-006, WOU-007

## 3. Deterministic submit validation

- [ ] 3.1 Add red table-driven tests in `agent/tests/engine/test_work_unit_validation.py` for valid fixtures and denial of wrong research/generation/phase/work/attempt/role ids, spec mutation, unsupported schemas, missing/empty files, path traversal, absolute paths, symlink escape/path swap, result/output hash mismatch, and invalid source refs. @impl WOU-001, WOU-003
- [ ] 3.2 Implement `engine/work_units/validation.py` as an ordered collect-all validator with closed stable failure codes, pure validation plans, canonical source URLs, result/output/source schema checks, and no success inference from summaries, finish reasons, file names, or run events. @impl WOU-003
- [ ] 3.3 Add red runtime read tests for descriptor/no-follow containment, symlink/path-swap denial, stat verification, byte bounds, hashing, virtual-ref projection, and host-path redaction. @impl WOU-003, REG-009, REG-010
- [ ] 3.4 Extend the runtime store with the contained read plan until task 3.3 is green; keep all host path and blocking file access inside `runtime/`. @impl WOU-003, REG-009, REG-010
- [ ] 3.5 Add red role-ownership fixtures proving controller alone writes canonical `work-spec.json`, the assigned worker can write only `result.json`/declared `outputs`/bounded fixture source refs, and submit alone writes ledger mechanics. @impl WOU-001, WOU-003, REG-002, REG-010
- [ ] 3.6 Implement deterministic fixture artifact helpers until task 3.5 is green, with no model, web, MCP, ACP, DeerFlow `task`, or sandbox research-tool call. @impl WOU-001, WOU-003, REG-002, REG-010

## 4. Work-unit allocation, reducers, retry, and drain kernel

- [ ] 4.1 Add red engine tests for stable work/attempt ordinals, retry with a new attempt id and unchanged spec hash, bounded batch selection, batch cursor progression, same-hash candidate idempotency, different-hash conflict, terminal downgrade denial, accepted-ref dedupe, cancellation/expiry/late-submit denial, and structural drain behavior. @impl WOU-001, WOU-002, WOU-007, WOU-008
- [ ] 4.2 Implement `engine/work_units/ids.py`, `reducers.py`, and `kernel.py` for controller allocation, typed pending/in-flight/terminal transitions, construction-time concurrency policy, candidate reduction, retry/replay decisions, and generic phase drain. @impl WOU-001, WOU-002, WOU-007, WOU-008
- [ ] 4.3 Add sole-writer tests proving planner/worker/repair/gate updates cannot allocate ids, mutate specs, set submitted status, append accepted refs, or access ledger commit capability, while deterministic submit and gate retain only their declared fields. @impl WOU-001, WOU-004, REG-007, REG-009

## 5. Reusable LangGraph component and Wave integration

- [ ] 5.1 Add red graph tests in `agent/tests/graph/test_work_unit_component.py` for at least three concurrent `Send` workers, arbitrary completion order, exact candidate retention, no double winner, bounded refill, explicit whole-Wave replay from the last parent checkpoint, and gate invocation only after drain. @impl WOU-002, WOU-005, WOU-008, REG-002
- [ ] 5.2 Implement `graph/components/work_units.py` as the reusable load-ledger -> deterministic materialize/allocate -> reconcile -> bounded Send -> reduce -> submit -> drain child graph with typed bounded child state and explicit `checkpointer=False`; do not claim inherited child durability under manual invocation. @impl WOU-002, WOU-005, WOU-008
- [ ] 5.3 Extend `GraphInvocationContext`/runtime dependency resolution so controller graph code receives the store protocol and each work-unit worker receives a freshly projected `work/<work>/<attempt>` dependency; add contract tests that host/store authority never enters `NodeAgentContext`, prompts, tool schemas, or checkpoint state. @impl WOU-001, WOU-004, NOA-001, REG-009, REG-010
- [ ] 5.4 Add a red Wave0 integration test requiring three controller specs/attempts, fixture candidates, validated records/accepted refs, replay, and drain through the shared component. @impl WOU-001, WOU-002, WOU-003, WOU-004, REG-002
- [ ] 5.5 Replace Wave0's fixed `BranchResult` join with the shared component until task 5.4 is green. @impl WOU-001, WOU-002, WOU-003, WOU-004, REG-002
- [ ] 5.6 Add a red Wave1 integration test with distinct deterministic fixture scope/content and an assertion that no second kernel, store, reducer, or submit path exists. @impl WOU-001, WOU-002, WOU-003, WOU-004, REG-002
- [ ] 5.7 Replace Wave1's fixed join with the same shared component until task 5.6 is green. @impl WOU-001, WOU-002, WOU-003, WOU-004, REG-002
- [ ] 5.8 Add red wrapper tests proving gate evaluation receives a pure allowlisted reducer-preview with current work status, accepted refs, and terminal failures, while phase/route/trace/gate-owned fields and the input checkpoint remain untouched; assert `FixtureSequenceRule` keeps the prior current-visit index. @impl WOU-004, WOU-008, GAK-003, GAK-005, REG-002
- [ ] 5.9 Implement the shared reducer-preview path in `domain/state.py`/`graph/builder.py`, then add topology/gate regressions proving internal nodes never enter `LOGICAL_NODES`, the snapshot/route labels remain identical, and `_route()` is unchanged. @impl WOU-008, GAK-003, REG-001, REG-002

## 6. Crash replay, process races, lifecycle, and E2E coverage

- [ ] 6.1 Add red fault-injection tests for every named boundary: from the last parent checkpoint before accepted-ref publication, before staging write, after staging fsync, after atomic ledger replace, after directory fsync, before submit-node return, and after returned state update. @impl WOU-005, WOU-006
- [ ] 6.2 Add red reconcile-matrix tests: regenerated attempt/no record executes and appends once; matching ledger/no ref skips worker and catches up; matching ledger/ref skips; divergent replay conflicts; checkpoint-ahead/missing-ledger fails closed; staging-only state is ignored and cleaned. @impl WOU-005
- [ ] 6.3 Complete kernel/store replay orchestration until tasks 6.1 and 6.2 are green, without adding a second checkpoint or evidence authority. @impl WOU-005, REG-009
- [ ] 6.4 Add a real multiprocessing/shared-temp-workspace contract test where independent store instances race the same candidate and then divergent candidates, proving one accepted winner, one valid hash chain, and no partial ledger line. @impl WOU-006
- [ ] 6.5 Add restart/cancel/expiry tests proving accepted attempts are skipped, unaccepted non-terminal work may replay, explicit terminal attempts require a fresh retry id, expired attempts reject late results, and cancellation is never projected as completion. @impl WOU-005, WOU-007
- [ ] 6.6 Update full-fake and mixed-graph tests to cover happy completion, repair, rerun, stop, cancel, stale-response denial, controlled Wave0/Wave1 fixture files, and absence of model/web/subagent/cache/synthesis/report side effects. @impl REG-002, REG-005, WOU-004
- [ ] 6.7 Add a worker-completion-without-result integration fixture plus wrong-id, out-of-root path, hash-mismatch, same-hash replay, and different-hash conflict paths through the real component and submit boundary. @impl WOU-003, WOU-005

## 7. Structure, documentation, and configuration invariants

- [ ] 7.1 Add the exact new required source packages/files (not every individual test file) to `openspec/governance/project-structure.toml`, update architecture contract fixtures, render the generated `agent/AGENTS.md` block, and pass `check_project_architecture.py`. @impl PRS-001, PRS-002, PRS-004
- [ ] 7.2 Update human-authored `agent/AGENTS.md`, `agent/README.md`, and the numbered/master backlog plan status with the work-unit authority chain, JSONL/lock decision, compatible version-2 state extension, whole-Wave replay unit, mounted-workspace limitation, controlled fixture side effects, and later-node reuse rule. @impl WOU-004, WOU-005, WOU-006, REG-009
- [ ] 7.3 Verify `openspec/governance/req-registry.yaml` contains the `WOU` prefix and WOU-001 through WOU-008 descriptions, and that active delta req headers own WOU-001..008 plus modified REG-002/009/010 and DEC-005, with every modified requirement copied in full. @impl WOU-001, WOU-002, WOU-003, WOU-004, WOU-005, WOU-006, WOU-007, WOU-008, REG-002, REG-009, REG-010, DEC-005
- [ ] 7.4 Run the existing configure/doctor contract tests and a read-only project doctor in the configured environment; add the work-unit storage readiness result while confirming no `config.yaml`, `extensions_config.json`, skill, Agent/SOUL, mount, dependency, startup-only field, `backend/`, or `frontend/` edit is needed. @impl DEC-002, DEC-005

## 8. Verification and hard done conditions

- [ ] 8.1 Run focused domain/engine/graph/runtime work-unit tests, then `cd agent && make test-unit && make test-contract`; fix all failures.
- [ ] 8.2 Run `cd agent && make test-viability && make test-durability && make test-blocking-io`; include the reflected `infra_probe` provider-reopen/subprocess-restart path as the environment-appropriate end-to-end infrastructure check. @impl RUI-001, RUI-005, WOU-005, WOU-006
- [ ] 8.3 Run `cd agent && make test` and verify the complete agent-owned suite, including full-fake and mixed lifecycle paths, is green.
- [ ] 8.4 Run `cd agent && make format && make lint && make lock-check`; fix formatting, lint, or lock drift without adding an unused dependency.
- [ ] 8.5 Run `python3 openspec/governance/check_project_architecture.py`, `python3 openspec/governance/check_project_reqs.py`, and `python3 openspec/governance/check_project_specs.py`; all three must pass with no structural drift, duplicate/unregistered/orphan/reused-retired requirement IDs, delta headers in main specs, or missing purpose/requirements/req headers.
- [ ] 8.6 Inspect `git diff -- backend frontend config.example.yaml extensions_config.example.json` and verify it is empty; inspect the final change diff for one submit authority, one ledger path, one retry path, and complete `@impl` traceability before archive.
