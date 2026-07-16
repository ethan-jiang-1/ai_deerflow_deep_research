## 1. Brief builder

- [x] 1.1 Add red tests for `build_hitl2_brief(state)` producing a structured brief dict with confirmed findings summary, unresolved gaps, and available actions from checkpoint state (`accepted_submission_refs`, `synthesis_gaps`). Empty state produces honest "no findings" brief. @impl HIT-001
- [x] 1.2 Implement `graph/nodes/hitl2/prompts.py` (or embed in node.py if simple enough) with the brief builder until 1.1 is green. @impl HIT-001

## 2. Real factory with interrupt/resume pipeline

- [x] 2.1 Add red tests for the real `hitl2/node.py` factory: builds brief, creates `PendingResearchInterrupt` with `HumanInputRequest(CHOICE, options=Hitl2Decision)`, calls `interrupt()`, validates `AcceptedHumanResponse`, handles `InternalCancelDecision`, routes all five `Hitl2Decision` values. @impl HIT-002
- [x] 2.2 Add red tests for stale resume detection: generation changes after interrupt → request_id mismatch → `ValueError`. @impl HIT-002
- [x] 2.3 Implement the real factory (enhance existing `build_real` stub) until 2.1 and 2.2 are green. Reuse the same domain models and interrupt pipeline as the fake. @impl HIT-001, HIT-002

## 3. Recipe wiring

- [ ] 3.1 Add red tests in `test_research_runtime_capabilities.py` that recipe detects `hitl2=real`, rejects it unless `wave2_synthesis=real`. @impl HIT-003
- [ ] 3.2 Wire `runtime/research.py` with the dependency guard. @impl HIT-003

## 4. Implementation map and E2E tests

- [ ] 4.1 Update contract test for real hitl2 in `test_research_node_packages.py`. @impl HIT-003
- [ ] 4.2 Add implementation-map test for full chain including hitl2. @impl HIT-003
- [ ] 4.3 Add full-fake regression test proving fake HITL2 interrupt path unchanged. @impl HIT-003

## 5. Documentation and governance

- [ ] 5.1 Add new production paths to `project-structure.toml`; render AGENTS.md; pass architecture check. @impl PRS-001..004
- [ ] 5.2 Update `agent/AGENTS.md` and `agent/README.md` with real HITL2. @impl HIT-001..003

## 6. Verification

- [ ] 6.1 Run `cd agent && make test-unit && make test-contract`; fix all failures.
- [ ] 6.2 Run `cd agent && make test`; verify complete suite green.
- [ ] 6.3 Run `cd agent && make format && make lint && make lock-check`.
- [ ] 6.4 Run governance checks; all three must pass.
- [ ] 6.5 Run `openspec validate implement-deep-research-hitl2-node --strict`.
- [ ] 6.6 Verify no `backend/` or `frontend/` changes.
