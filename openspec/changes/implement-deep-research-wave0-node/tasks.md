## 1. Domain: source-intake result contract and validation registry

- [x] 1.1 Add red tests for a frozen `Wave0SourceIntakeResult` result-contract model (canonical source URLs, source metadata, baseline facts, fetch/cache refs, limitations, `schema_version=1`): reject unknown fields, oversized text, non-canonical URLs, missing required fields; canonical JSON serialization. @impl WAN-003
- [x] 1.2 Implement the result-contract model inside the wave0 package (extend `contracts.py` or add a bounded module) until 1.1 is green. @impl WAN-003
- [x] 1.3 Add red tests that `engine/work_units/validation.py` dispatches through a registry keyed by `(result_contract, result_schema_version)`, still accepts the existing `fixture.work-unit` v1 contract, and accepts the new `wave0.source-intake` v1 contract with the real model; an unregistered contract fails with `result_contract_unsupported`. @impl WAN-003
- [x] 1.4 Generalize the hard-coded result-contract check into the registry and register both contracts until 1.3 is green; existing fixture submit tests stay green. @impl WAN-003

## 2. Source canonicalization and submit-validation checks

- [x] 2.1 Add red tests that submit validation for `wave0.source-intake` canonicalizes each source URL via `canonicalize_source_url`, rejects non-canonical input, snippet-as-cache, cross-attempt/out-of-containment writes, and hash mismatch against fetched bytes, and deduplicates sources that canonicalize to the same URL per topic. @impl WAN-003
- [x] 2.2 Implement the wave0 source-intake validator (pure) wired into the registry until 2.1 is green. @impl WAN-003

## 3. Topic-to-work materialization and worker prompt

- [x] 3.1 Add red tests for `materialize_wave0_intents(topic_registry)` producing one `WorkIntent` per topic (scope binding topic id + must-answer questions, required outputs declaring source-intake artifacts) and rejecting an empty registry. @impl WAN-001
- [x] 3.2 Implement the intent materializer under the wave0 package until 3.1 is green. @impl WAN-001
- [x] 3.3 Add red tests for `build_wave0_worker_prompt(work_spec, topic)` producing a bounded `NodeExecutionRequest` whose objective carries the topic scope and whose instructions keep fetched content as untrusted data; verify the trusted policy prompt is never overridden by source text. @impl WAN-002
- [x] 3.4 Implement `graph/nodes/wave0/prompts.py` until 3.3 is green. @impl WAN-002

## 4. Real Wave0 node, subgraph, and worker

- [x] 4.1 Add red tests for the real `wave0/node.py` factory: it reads `topic_registry`, drives the shared work-unit component with real intents and a real worker, and returns `node_update` + parent work-block update + `WorkUnitGateView`; empty registry fails closed. @impl WAN-001
- [x] 4.2 Implement the real factory (replace `UNAVAILABLE_REAL_FACTORY`); extend `wave0/subgraph.py` to accept real intents + a real worker callable; keep `fake.py` unchanged. Until 4.1 is green. @impl WAN-001
- [x] 4.3 Add red tests for the real worker callable: it calls `capabilities.run_agent()` once per attempt under the worker policy, writes its result via the attempt artifact writer, writes only under its `attempt_root`, and routes fetched content through the untrusted-data path. Use fake capabilities returning a `NodeExecutionResult`, not `FakeToolCallingModel` directly. @impl WAN-002
- [x] 4.4 Implement the real worker until 4.3 is green. @impl WAN-002

## 5. Worker bridge policy and recipe wiring

- [x] 5.1 Add red tests in `tests/unit/test_research_runtime_capabilities.py` that `ResearchGraphRecipe` detects `wave0=real`, rejects it unless `topic_planning=real` (which requires `hitl1=real` + `bootstrap=real`), constructs a real `RuntimeNodeAgentBridge` for the wave0 worker with a non-empty `allowed_tool_names` web set and attempt-scoped read/write roots, and does not attach request-bundle/bootstrap for wave0. @impl WAN-002, WAN-005, NOA-001, NOA-002
- [x] 5.2 Wire `runtime/research.py` with a real wave0 worker `ExecutionPolicy` (web tool names, per-tool `ToolPolicySpec`, attempt-scoped roots) using `_default_tools_resolver`, and the `wave0=real` recipe dependency guard. Until 5.1 is green. @impl WAN-002, WAN-005, NOA-001, NOA-002

## 6. Real Wave0 gate with source floor and degraded capture

- [x] 6.1 Add red tests for the real wave0 gate (`graph/nodes/wave0/gate.py`): it drops `FixtureSequenceRule`, keeps `WorkUnitCompletionRule`, and routes `repair`/`pass`/`exhausted`; a topic below the independent-source floor routes `repair` (then `exhausted`); a covering plan routes `pass`; gate rules stay pure (no I/O). @impl WAN-004
- [x] 6.2 Add red tests that source-floor coverage is enforced at submit-validation time (insufficient independent sources reject the candidate) and that a degraded capture is accepted only when the floor is otherwise met. @impl WAN-004
- [x] 6.3 Implement the real wave0 gate definition and register it for real wave0 while keeping the fixture gate for fake wave0; until 6.1/6.2 are green. @impl WAN-004

## 7. Implementation map, lifecycle E2E, and regression

- [ ] 7.1 Add red implementation-map tests that mixed mode (`bootstrap=real`, `hitl1=real`, `topic_planning=real`, `wave0=real`, every other phase `fake`) selects all four real factories and compiles; `wave0=real` without `topic_planning=real` fails closed; full-fake map is unchanged. @impl WAN-005, PRS-003
- [ ] 7.2 Add a red mixed-graph lifecycle E2E through handlers that runs the real chain into real Wave0 with replay/fake web tools, then fake Wave1 onward to completion; assert accepted `SubmissionRecord`s/`accepted_submission_refs`, source refs, `implementation_mode=full_fake`, and no synthesis/report side effects. @impl WAN-001, WAN-003, WAN-005
- [ ] 7.3 Add red E2E coverage for prompt-injected source (only limitation/rejection), unreachable-source degraded capture, duplicate-URL dedup, and repeated floor failure -> terminal `blocked`. @impl WAN-002, WAN-003, WAN-004, REG-005
- [ ] 7.4 Add a full-fake regression test proving fake Wave0 and existing lifecycle E2E remain unchanged and do not construct `RuntimeNodeAgentBridge`. @impl WAN-005, REG-002

## 8. Structure, documentation, and governance

- [ ] 8.1 Verify the active delta specs for `wave0-node` and `project-structure` still own the real result contract, worker/gate paths, and the result-contract registry permission after implementation edits. @impl WAN-001..005, PRS-001, PRS-002, PRS-003, PRS-004
- [ ] 8.2 Add exact new production paths (`graph/nodes/wave0/prompts.py` and `graph/nodes/wave0/gate.py`) to `openspec/governance/project-structure.toml`; render the generated `agent/AGENTS.md` block with `python3 openspec/governance/check_project_architecture.py --render-guide`; pass `check_project_architecture.py`. @impl PRS-001, PRS-002, PRS-003, PRS-004
- [ ] 8.3 Update human-authored `agent/AGENTS.md` (Current Status / Node Packages / state authority), `agent/README.md`, and `_backlog/plans/deep-research-08-wave0-node.md` with real Wave0, the source-intake result contract, the real source-floor gate, the untrusted-data worker, the real-topic-chain dependency, and the unchanged `backend/`/`frontend/` boundary. @impl WAN-001..005
- [ ] 8.4 Verify `openspec/governance/req-registry.yaml` contains the `WAN` prefix and WAN-001 through WAN-005 descriptions, and that active delta specs own all WAN ids plus the modified PRS ids with no duplicate/unregistered/orphan/reused-retired requirements. @impl WAN-001..005, PRS-004
- [ ] 8.5 Run configure/doctor contract tests and project doctor; verify real Wave0 adds no `extensions_config.json` key, public/custom skill, Agent/SOUL, mount, dependency, startup-only field, `backend/`, or `frontend/` change, and that doctor surfaces the web-tool provisioning prerequisite without adding a provider. @impl DEC-005

## 9. Verification and hard done conditions

- [ ] 9.1 Run focused domain/work-unit/graph/wave0 tests, then `cd agent && make test-unit && make test-contract`; fix all failures.
- [ ] 9.2 Run `cd agent && make test-viability && make test-durability && make test-blocking-io`; verify mixed real-Wave0 E2E and blocked paths use existing infrastructure boundaries.
- [ ] 9.3 Run `cd agent && make test` and verify the complete agent-owned suite, including full-fake, mixed-Wave0, blocked, injection, degraded, and restart lifecycle paths, is green.
- [ ] 9.4 Run `cd agent && make format && make lint && make lock-check`; fix formatting, lint, or lock drift without adding unused dependencies.
- [ ] 9.5 Run `python3 openspec/governance/check_project_architecture.py`, `python3 openspec/governance/check_project_reqs.py`, and `python3 openspec/governance/check_project_specs.py`; all three must pass.
- [ ] 9.6 Run `openspec validate implement-deep-research-wave0-node --strict`; fix any artifact/schema issue.
- [ ] 9.7 Inspect `git diff -- backend frontend config.example.yaml extensions_config.example.json` and verify it is empty; inspect the final diff for one wave0 worker authority, one result-contract registry, untrusted-data handling, no LLM-authored ledger, no fabricated sources, and complete `@impl` traceability before archive.
