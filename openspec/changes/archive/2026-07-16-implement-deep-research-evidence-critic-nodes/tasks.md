## 1. Domain: critic result contracts and validation

- [x] 1.1 Add red tests for a frozen `SourceDiagnosticResult` model (`schema_version=1`, per-source `trust_tier` enum `high`/`medium`/`low`/`untrusted`, `materiality` enum `primary`/`secondary`/`peripheral`, `marketing_risk` bool, `cross_verification_need` bool) with unknown-field rejection, missing required fields, canonical JSON serialization, and source-id validation against assigned evidence. @impl EVC-001
- [x] 1.2 Add red tests for a frozen `ClaimVerifierResult` model (`schema_version=1`, per-claim verdict enum with `supported`/`weakened`/`contradicted`/`uncertain`, `support_refs`, `counter_refs`, `reason`) with dangling-ref rejection, empty evidence, and canonical JSON serialization. @impl EVC-002
- [x] 1.3 Implement both result-contract models under `domain/` (e.g., `domain/critics.py`) until 1.1 and 1.2 are green. @impl EVC-001, EVC-002

## 2. Agent prompts and structured-output contracts

- [x] 2.1 Add red tests for `build_source_diagnostic_prompt(assigned_sources, source_content)` producing a bounded `NodeExecutionRequest` with objective carrying source count and trust/materiality dimensions, and untrusted-source-data wrapping for all external content. @impl EVC-001
- [x] 2.2 Add red tests for `build_claim_verifier_prompt(claims, assigned_refs)` producing a bounded `NodeExecutionRequest` with objective carrying claim count and verdict taxonomy, and untrusted-source-data wrapping. @impl EVC-002
- [x] 2.3 Implement `agents/critic_prompts.py` (flat module, consistent with existing `agents/prompts.py`) with both prompt builders until 2.1 and 2.2 are green. @impl EVC-001, EVC-002

## 3. Deterministic materializer and artifact writing

- [x] 3.1 Add red tests for `materialize_source_diagnostic(result, node_attempt_id, workspace_root)` writing canonical JSON to `<workspace_root>/critic/<node_attempt_id>/source-diagnostic.json`, rejecting invalid results, and failing on non-assigned source refs. The workspace root comes from the node's graph context. @impl EVC-004
- [x] 3.2 Add red tests for `materialize_claim_verifier(result, node_attempt_id, workspace_root)` writing canonical JSON to `<workspace_root>/critic/<node_attempt_id>/claim-verifier.json`, rejecting dangling refs and invalid verdicts. @impl EVC-004
- [x] 3.3 Implement `agents/critic_materializer.py` until 3.1 and 3.2 are green. @impl EVC-004

## 4. Critic agent factory and read-only policy

- [x] 4.1 Add red tests for `run_source_diagnostic(capabilities, node_attempt_id, research_id, source_refs, workspace_root)` where `capabilities` is a `RuntimeNodeAgentBridge` protocol. Calls `capabilities.run_agent()` once under a read-only `ExecutionPolicy` (`allowed_tool_names=frozenset()`, `write_roots=()`, `read_roots` including the virtual bundle path `/mnt/user-data/workspace/deep-research/<research_id>/`), returns `SourceDiagnosticResult`, and fails on tool-call attempts. The `workspace_root` host path is used by the materializer only, not the policy. @impl EVC-001, EVC-003
- [x] 4.2 Add red tests for `run_claim_verifier(capabilities, node_attempt_id, research_id, claims, evidence_refs, workspace_root)` with the same read-only policy, returning `ClaimVerifierResult`. Claims are tuples of `(claim_id, claim_text)`. @impl EVC-002, EVC-003
- [x] 4.3 Implement `agents/critic_factory.py` with both critic runners until 4.1 and 4.2 are green. @impl EVC-001, EVC-002, EVC-003

## 5. Critic dispatcher and real targeted_evidence node factory

- [x] 5.1 Add red tests for `dispatch_critic(work_items, capabilities, node_attempt_id, research_id, workspace_root)` where each work item is a typed dict (`{"type": "source_diagnostic", "source_refs": [...]}` or `{"type": "claim_verifier", "claims": [...], "evidence_refs": [...]}`). Routes to the correct runner, validates type, and rejects unknown types. @impl EVC-001, EVC-002
- [x] 5.2 Implement `agents/critic_dispatcher.py` until 5.1 is green. @impl EVC-001, EVC-002
- [x] 5.3 Add red tests for the real `targeted_evidence/node.py` factory: it reads work items from `ResearchState.critic_work_items` (a list of typed dicts), invokes `dispatch_critic`, writes artifacts via materializers, and returns `node_update` with `route="next"`. Empty or absent `critic_work_items` is a no-op pass-through. @impl EVC-001, EVC-002, EVC-003
- [x] 5.4 Implement the real factory (replace `UNAVAILABLE_REAL_FACTORY`); keep `fake.py` unchanged. Until 5.3 is green. @impl EVC-001, EVC-002, EVC-003

## 6. Integration: critic node unit integration tests

- [x] 6.1 Add red test for the real `targeted_evidence` node driven directly via `build_real(dependencies)` with fixture work items: inject `critic_work_items` into state containing `source_diagnostic` items, invoke the node, assert `SourceDiagnosticResult` written to sandbox, assert `route="next"` returned. Does not require full graph E2E. @impl EVC-001, EVC-003, EVC-004
- [x] 6.2 Add red test for the real node with `claim_verifier` work items against fixture claims + evidence refs, assert `ClaimVerifierResult` written to sandbox. @impl EVC-002, EVC-003, EVC-004
- [x] 6.3 Add full-fake regression test proving fake targeted_evidence and existing lifecycle E2E remain unchanged and do not construct `RuntimeNodeAgentBridge` for critics. @impl EVC-005
- [x] 6.4 Note: full lifecycle E2E through wave2_synthesis→targeted_evidence requires change 11 (real wave2_synthesis) because the fixture gate only routes `pass`, not `evidence_needed`. This change's integration coverage is node-level unit integration, not full-graph E2E.

## 7. Test coverage: edge cases and adversarial

- [x] 7.1 Add tests for SourceDiagnostic with empty source set, prompt-injected source content, and marketing-heavy source (all should produce honest assessments without escalation). @impl EVC-001, EVC-005
- [x] 7.2 Add tests for ClaimVerifier with dangling refs, conflicting evidence (supported + contradicted), and empty claim set. @impl EVC-002, EVC-005
- [x] 7.3 Add tests for author-critic isolation: separate model/session instances, no shared state between Wave0 worker and critic agents. @impl EVC-005

## 8. Documentation and governance

- [x] 8.1 Verify the active delta spec for `evidence-critic-nodes` owns all EVC-001 through EVC-005 requirements after implementation. @impl EVC-001..005
- [x] 8.2 Add new production paths (`domain/critics.py`, `domain/untrusted.py`, `graph/nodes/targeted_evidence/prompts.py`, `graph/nodes/targeted_evidence/materializer.py`, `graph/nodes/targeted_evidence/subgraph.py`) to `openspec/governance/project-structure.toml`; render the `agent/AGENTS.md` block; pass `check_project_architecture.py`. @impl PRS-001, PRS-002, PRS-003, PRS-004
- [x] 8.3 Update human-authored `agent/AGENTS.md` (Current Status) and `agent/README.md` with real evidence critic nodes and the unchanged `backend/`/`frontend/` boundary. @impl EVC-001..005
- [x] 8.4 Verify `openspec/governance/req-registry.yaml` contains the `EVC` prefix and EVC-001 through EVC-005 descriptions. @impl EVC-001..005, PRS-004
- [x] 8.5 Run configure/doctor contract tests; verify no `extensions_config.json` key, public/custom skill, Agent/SOUL, `backend/`, or `frontend/` change. @impl DEC-005

## 9. Verification and hard done conditions

- [x] 9.1 Run focused domain/agents/graph/targeted_evidence tests, then `cd agent && make test-unit && make test-contract`; fix all failures.
- [x] 9.2 Run `cd agent && make test-viability && make test-durability && make test-blocking-io`; verify critic agents use existing infrastructure boundaries.
- [x] 9.3 Run `cd agent && make test` and verify the complete agent-owned suite, including full-fake, mixed-critic, and adversarial paths, is green.
- [x] 9.4 Run `cd agent && make format && make lint && make lock-check`; fix formatting, lint, or lock drift without adding unused dependencies.
- [x] 9.5 Run `python3 openspec/governance/check_project_architecture.py`, `python3 openspec/governance/check_project_reqs.py`, and `python3 openspec/governance/check_project_specs.py`; all three must pass.
- [x] 9.6 Run `openspec validate implement-deep-research-evidence-critic-nodes --strict`; fix any artifact/schema issue.
- [x] 9.7 Inspect `git diff -- backend frontend config.example.yaml extensions_config.example.json` and verify it is empty; inspect the final diff for critic authority isolation, no LLM-authored ledger, and complete `@impl` traceability before archive.
