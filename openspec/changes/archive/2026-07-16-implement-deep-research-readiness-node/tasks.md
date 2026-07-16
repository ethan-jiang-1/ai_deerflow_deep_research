## 1. Contracts

- [x] 1.1 Add red tests for new types: `HardRuleFailure`, `PerQuestionVerdict`, `ReadinessCriticOutput`, `ReadinessReportPlan`, `ReportPlanConclusion`, `ReportPlanUncertainty`, `ReportPlanProhibitedUpgrade`. @impl REA-001, REA-002, REA-003
- [x] 1.2 Update `graph/nodes/readiness/contracts.py` with new types; keep `ReadinessRequest`/`ReadinessResult` unchanged. @impl REA-001, REA-002, REA-003

## 2. Hard checks

- [x] 2.1 Add red tests for `check_citation_availability`, `check_provenance`, `check_hitl2_consumption`, `run_hard_rules`. @impl REA-001
- [x] 2.2 Implement `graph/nodes/readiness/hard_rules.py`. `HardRuleFailure` is a FrozenContract in contracts.py; the module produces and collects them. @impl REA-001, REA-005

## 3. Readiness critic

- [x] 3.1 Add red tests for critic deterministic fallback output structure. @impl REA-002
- [x] 3.2 Implement `graph/nodes/readiness/critic.py` with deterministic fallback; real agent loop pattern documented. @impl REA-002, REA-006

## 4. Report plan materializer

- [x] 4.1 Add red tests for `materialize_report_plan` — conclusions from ready_substantive, uncertainties from insufficient_judgment, blocked absent from both. @impl REA-003
- [x] 4.2 Implement `graph/nodes/readiness/materializer.py`. @impl REA-003

## 5. Real factory with route determination

- [x] 5.1 Add red tests for `build_real` — full pipeline: hard rules → critic → materializer → route determination. Test all three route outcomes (pass, repair_targeted, exhausted). @impl REA-001..005
- [x] 5.2 Implement `build_real` in `graph/nodes/readiness/node.py`. Node writes its own `route` (non-gated pattern). @impl REA-001..005

## 6. State fields and recipe wiring

- [x] 6.1 Add `readiness_hard_failures`, `readiness_critic_summary`, `readiness_blocked_count`, `readiness_report_plan` to `ResearchCheckpoint` and `ResearchState`. @impl REA-001..003
- [x] 6.2 Add ownership entries for all four fields (CONTROLLER writer). @impl REA-001..003
- [x] 6.3 Wire `readiness=real` dependency guard in `runtime/research.py`: requires `hitl2=real`. @impl REA-007
- [x] 6.4 Update contract test for readiness real factory. @impl REA-007

## 7. Builder: remove fixture gate for real readiness

- [x] 7.1 In `graph/builder.py`, when `readiness=real`, remove readiness from `_gate_defs` (set to None or delete key) so no gate evaluation runs. @impl REA-007
- [x] 7.2 Add full-fake regression test: fake readiness unchanged, fixture gate still provides route. @impl REA-007

## 8. Verification

- [x] 8.1 Run `make format && make lint`.
- [x] 8.2 Run `make test`; verify complete suite green.
- [x] 8.3 Run governance checks — both PASS.
- [x] 8.4 Verify no `backend/` or `frontend/` changes.
