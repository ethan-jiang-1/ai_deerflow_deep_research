## 1. Domain: Wave1 result contracts and worker output schema

- [ ] 1.1 Add red tests for a frozen `Wave1WorkerOutput` model (`schema_version=1`, `claims` with claim_id/statement/support_refs/counter_refs, `open_questions` with resolution states, per-source `is_new_vs_wave0`) with unknown-field rejection, empty claims allowed, and canonical JSON serialization. @impl WON-002
- [ ] 1.2 Implement `domain/wave1.py` with `Wave1WorkerOutput`, `ClaimDraft`, `OpenQuestion` models until 1.1 is green. @impl WON-002

## 2. Worker prompt and structured-output specification

- [ ] 2.1 Add red tests for `build_wave1_worker_prompt(spec, topic, wave0_urls)` producing a bounded `NodeExecutionRequest` with objective carrying search dimensions and must-answer bindings, Wave0 URL set for dedup, and untrusted-data wrapping. @impl WON-002
- [ ] 2.2 Add red tests for `parse_wave1_worker_output(text)` parsing JSON into `Wave1WorkerOutput`, rejecting invalid JSON, missing required keys, and invalid claim/ref references. @impl WON-002
- [ ] 2.3 Implement `graph/nodes/wave1/prompts.py` until 2.1 and 2.2 are green. @impl WON-002

## 3. Wave1 intent materializer

- [ ] 3.1 Add red tests for `materialize_wave1_intents(topic_registry, wave0_urls, critic_verdicts)` producing one `WorkIntent` per topic with search dimensions covering Wave0 gaps, and rejecting an empty topic registry. @impl WON-001
- [ ] 3.2 Implement the intent materializer under the wave1 package until 3.1 is green. @impl WON-001

## 4. Submit validation: new-source floor and critic invocation

- [ ] 4.1 Add red tests that submit validation for `wave1.source-intake` candidate rejects when `is_new_vs_wave0` count falls below floor, canonicalizes and deduplicates URLs, and accepts valid new evidence. @impl WON-003
- [ ] 4.2 Add red tests for `invoke_critics_on_submission(capabilities, record, workspace_root)` calling SourceDiagnostic and ClaimVerifier, writing verdict artifacts. @impl WON-003
- [ ] 4.3 Implement new-source floor and critic invocation in `engine/work_units/validation.py` until 4.1 and 4.2 are green; existing submit tests stay green. @impl WON-003

## 5. Real Wave1 node, subgraph, and worker

- [ ] 5.1 Add red tests for the real `wave1/node.py` factory: reads topic_registry and wave0 source URLs, drives shared work-unit component with real intents and a real worker, returns `node_update` + parent work-block update + `WorkUnitGateView`. @impl WON-001
- [ ] 5.2 Add red tests for the real worker callable: calls `capabilities.run_agent()` under web-tool policy, parses output, writes result via attempt artifact writer, marks is_new_vs_wave0. Use fake capabilities. @impl WON-002
- [ ] 5.3 Implement `graph/nodes/wave1/subgraph.py` and `graph/nodes/wave1/node.py` (replace `UNAVAILABLE_REAL_FACTORY`) until 5.1 and 5.2 are green. @impl WON-001, WON-002

## 6. Wave1 gate with provenance, coverage, and critic verdicts

- [ ] 6.1 Add red tests for the real Wave1 gate: drops `FixtureSequenceRule`, keeps `WorkUnitCompletionRule`, enforces new-source floor per topic, checks critic verdict presence, checks open-question resolution. Routes repair/exhausted correctly. @impl WON-004
- [ ] 6.2 Add red tests that gate routes repair when critic verdicts missing and exhausts when repair budget consumed. @impl WON-004
- [ ] 6.3 Implement `engine/gate_fixtures.py` with `build_wave1_real_gate_def()` and register for real wave1; fixture gate unchanged for fake wave1. Until 6.1/6.2 are green. @impl WON-004

## 7. Recipe wiring and mixed-graph integration

- [ ] 7.1 Add red tests in `test_research_runtime_capabilities.py` that `ResearchGraphRecipe` detects `wave1=real`, rejects it unless full chain is real, constructs a real `RuntimeNodeAgentBridge` for the wave1 worker with web tools and attempt-scoped roots. @impl WON-005
- [ ] 7.2 Wire `runtime/research.py` with real wave1 worker `ExecutionPolicy` and dependency guard. Until 7.1 is green. @impl WON-005

## 8. Implementation map and E2E tests

- [ ] 8.1 Add implementation-map tests that mixed mode with full real chain including wave1 selects all six real factories and compiles; incomplete chain fails; full-fake map unchanged. @impl WON-005
- [ ] 8.2 Add red mixed-graph lifecycle E2E through handlers running real chain into real Wave1 with replay web tools, then fake Wave2 onward to completion; assert accepted submissions, critic verdicts, `implementation_mode=full_fake`. @impl WON-001, WON-003, WON-005
- [ ] 8.3 Add E2E coverage for Wave0-duplicate URL rejection, insufficient new-source floor → repair → exhausted, and missing critic verdict → repair. @impl WON-003, WON-004
- [ ] 8.4 Add full-fake regression test proving fake Wave1 and existing lifecycle E2E remain unchanged. @impl WON-005

## 9. Documentation and governance

- [ ] 9.1 Verify delta specs for `wave1-node` and `work-unit-kernel` own all WON ids and the modified WOU-003 requirement. @impl WON-001..006
- [ ] 9.2 Add new production paths to `project-structure.toml`; render AGENTS.md; pass architecture check. @impl PRS-001..004
- [ ] 9.3 Update `agent/AGENTS.md` and `agent/README.md` with real Wave1. @impl WON-001..006
- [ ] 9.4 Verify `req-registry.yaml` contains WON-001 through WON-006; verify no duplicate/unregistered/orphan requirements. @impl WON-001..006

## 10. Verification

- [ ] 10.1 Run `cd agent && make test-unit && make test-contract`; fix all failures.
- [ ] 10.2 Run `cd agent && make test-viability && make test-durability && make test-blocking-io`.
- [ ] 10.3 Run `cd agent && make test`; verify complete suite green.
- [ ] 10.4 Run `cd agent && make format && make lint && make lock-check`.
- [ ] 10.5 Run governance checks; all three must pass.
- [ ] 10.6 Run `openspec validate implement-deep-research-wave1-node --strict`.
- [ ] 10.7 Verify `git diff -- backend frontend config.example.yaml extensions_config.example.json` is empty.
