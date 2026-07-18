# Live And Release Regression Descent

Every live or release discovery is classified at the lowest stable seam. A
deterministically reproducible defect must name a collected zero-API regression;
provider distribution behavior must remain live and explain why replay would be
misleading.

| Discovery | Risk family | Stable seam | Disposition | Deterministic selector | Provider-only rationale |
| --- | --- | --- | --- | --- | --- |
| LIVE-20260717-01 | mounted-workspace-cleanup | runtime-store | deterministic-regression | tests/unit/test_work_unit_storage.py::test_runtime_verifier_cleanup_is_idempotent_with_real_local_sandbox | n/a |
| LIVE-20260717-02 | model-construction | runtime-bridge | deterministic-regression | tests/unit/test_live_evaluation.py::test_live_model_config_constructs_with_one_retry_authority | n/a |
| LIVE-20260717-03 | canary-precondition | node-contract | deterministic-regression | tests/unit/test_live_evaluation.py::test_live_canary_setup_payloads_satisfy_real_node_parsers | n/a |
| LIVE-20260717-04 | structured-output-contract | node-capability | deterministic-regression | tests/graph/test_wave0_worker.py::test_build_wave0_worker_prompt_carries_topic_constraints | n/a |
| LIVE-20260717-05 | model-tool-selection | live-real-dependencies | provider-only-live | n/a | The live model made no web tool call across bounded attempts; scripted real-workflow coverage proves the tool path but cannot reproduce the provider decision distribution honestly. |
| RELEASE-20260717-01 | final-artifact-publication | runtime-store | deterministic-regression | tests/unit/test_final_delivery_real.py::TestRealFinalDelivery::test_materializes_report_and_citation_map_with_matching_refs | n/a |
| LIVE-20260717-06 | source-provenance | runtime-bridge | deterministic-regression | tests/unit/test_node_agent_bridge.py::test_request_requiring_tool_execution_rejects_direct_model_answer | n/a |
| RELEASE-20260717-02 | profile-budget-expansion | node-contract | deterministic-regression | tests/graph/test_topic_planning_prompts.py::test_very_quick_overview_limits_plan_to_one_topic | n/a |
| RELEASE-20260717-03 | source-url-canonicalization | domain-contract | deterministic-regression | tests/graph/test_wave0_worker.py::test_worker_source_canonicalizes_untrusted_model_url | n/a |
| RELEASE-20260717-04 | source-status-normalization | domain-contract | deterministic-regression | tests/graph/test_wave0_worker.py::test_worker_source_normalizes_fetched_status_aliases[available] | n/a |
| RELEASE-20260717-05 | structured-field-normalization | domain-contract | deterministic-regression | tests/graph/test_wave0_worker.py::test_wave0_worker_output_normalizes_bounded_limitations_list | n/a |
| RELEASE-20260717-06 | wave1-authority-boundary | node-capability | deterministic-regression | tests/integration/test_wave1_work_units.py::test_real_wave1_crosses_worker_context_artifact_validator_and_ledger | n/a |
| RELEASE-20260717-07 | wave1-provider-identifiers | domain-contract | deterministic-regression | tests/unit/test_wave1_contracts.py::TestWave1WorkerOutput::test_provider_ids_and_question_state_are_normalized | n/a |
| RELEASE-20260717-08 | synthesis-structured-repair | node-capability | deterministic-regression | tests/graph/test_wave2_synthesis_real.py::test_real_synthesis_repairs_malformed_output_once_without_tools | n/a |
| RELEASE-20260717-09 | synthesis-provider-shape | domain-contract | deterministic-regression | tests/graph/test_wave2_provider_shapes.py::test_wave2_provider_shape[shape-wave2-provider-field-aliases] | n/a |
| RELEASE-20260717-10 | profile-topic-bound-enforcement | node-contract | deterministic-regression | tests/graph/test_topic_planning_node.py::test_minimal_quick_profile_repairs_multi_topic_plan_to_exactly_one | n/a |
| RELEASE-20260717-11 | synthesis-gap-priority-alias | domain-contract | deterministic-regression | tests/graph/test_wave2_provider_shapes.py::test_wave2_provider_shape[shape-wave2-gap-priority-alias] | n/a |
| RELEASE-20260717-12 | wave0-partial-source-degradation | domain-contract | deterministic-regression | tests/graph/test_wave0_worker.py::test_wave0_worker_output_keeps_valid_sources_and_records_dropped_items | n/a |
| RELEASE-20260717-13 | synthesis-evidence-and-semantic-floor | runtime-store/node-capability | deterministic-regression | tests/graph/test_wave2_synthesis_real.py::test_real_synthesis_rejects_empty_repair_when_accepted_evidence_exists | n/a |
| RELEASE-20260717-14 | readiness-ledger-provenance | domain-contract | deterministic-regression | tests/unit/test_readiness_real.py::TestRealReadiness::test_canonical_ledger_hash_passes_provenance | n/a |
| RELEASE-20260717-15 | visible-internal-retry-trace | release-control | deterministic-regression | tests/unit/test_release_control_plane.py::test_release_trace_accepts_consecutive_visible_internal_retries | n/a |
| RELEASE-20260717-16 | release-dotenv-handoff | release-control | deterministic-regression | tests/unit/test_release_control_plane.py::test_release_make_target_shares_optional_dotenv_with_preflight_and_pytest | n/a |
| RELEASE-20260717-17 | redacted-schema-diagnostics | live-reporting | deterministic-regression | tests/unit/test_live_evaluation.py::test_live_usage_tracker_reports_synthesis_schema_errors_without_values | n/a |
| RELEASE-20260717-18 | wave1-provider-source-identifiers | domain-contract/node-capability | deterministic-regression | tests/unit/test_wave1_contracts.py::TestWave1WorkerOutput::test_provider_source_ids_and_claim_refs_are_normalized_together | n/a |
| RELEASE-20260717-19 | synthesis-provider-description-and-gap-shape | domain-contract/node-capability | deterministic-regression | tests/graph/test_wave2_provider_shapes.py::test_wave2_provider_shape[shape-wave2-description-string-gaps] | n/a |
| RELEASE-20260717-20 | synthesis-sparse-finding-shape | domain-contract/node-capability | deterministic-regression | tests/graph/test_wave2_provider_shapes.py::test_wave2_provider_shape[shape-wave2-sparse-findings] | n/a |
| RELEASE-20260717-21 | wave1-source-order-canonicalization | runtime-materializer/submit-validator | deterministic-regression | tests/integration/test_wave1_work_units.py::test_real_wave1_canonicalizes_provider_source_order_before_candidate_validation[shape-wave1-source-order] | n/a |
| RELEASE-20260717-22 | synthesis-relation-endpoint-aliases | domain-contract/node-capability | deterministic-regression | tests/graph/test_wave2_provider_shapes.py::test_wave2_provider_shape[shape-wave2-relation-endpoints] | n/a |
| RELEASE-20260717-23 | synthesis-singular-affected-topic | domain-contract/node-capability | deterministic-regression | tests/graph/test_wave2_provider_shapes.py::test_wave2_provider_shape[shape-wave2-singular-affected-topic] | n/a |
| RELEASE-20260717-24 | synthesis-alternate-relation-shape | domain-contract/node-capability | deterministic-regression | tests/graph/test_wave2_provider_shapes.py::test_wave2_provider_shape[shape-wave2-alternate-relation] | n/a |
| RELEASE-20260717-25 | synthesis-missing-gap-identity | domain-contract/node-capability | deterministic-regression | tests/graph/test_wave2_provider_shapes.py::test_wave2_provider_shape[shape-wave2-missing-gap-identity] | n/a |
| LIVE-20260718-01 | synthesis-gap-routing-authority | domain-contract/node-capability | deterministic-regression | tests/graph/test_wave2_synthesis_real.py::test_real_synthesis_persists_searchable_gap_and_returns_typed_preview | n/a |
| LIVE-20260718-02 | targeted-structured-output-repair | node-capability/runtime-store | deterministic-regression | tests/graph/test_targeted_evidence_real.py::test_targeted_invalid_first_response_repairs_once_without_tools[prose] | n/a |
| LIVE-20260718-03 | wave1-tool-only-budget-exhaustion | live-real-dependencies | provider-only-live | n/a | The bounded live model emitted only tool calls with empty content across all three allowed turns. Scripted bridge and fail-closed budget tests prove mechanics, but cannot honestly reproduce this provider decision distribution. |
| LIVE-20260718-05 | targeted-final-answer-timeout | live-real-dependencies | provider-only-live | n/a | After the request quota correctly denied a three-call parallel batch, a one-search targeted request reached the provider but did not return a final answer within the declared 180-second case deadline. Deterministic quota/repair coverage passes; this provider latency/convergence distribution is not replayed as a fake. |

## Current Evidence-V1 Findings Awaiting Closure

The reviewed `harden-late-node-structured-output` change deterministically fixed
the original gap-routing and targeted-repair findings. In the fresh complete
lane, targeted evidence passed with two real Tavily calls and validated ledger
authority, while Wave2 accepted the canonical gap field. The complete lane did
not close: Wave1 exhausted its bounded turns with tool-only responses, and
Wave2 exposed the distinct zero-findings/non-empty-gaps semantic-floor gap.
Both failed closed without fabricated authority. Nightly remains disabled until
a newly reviewed remediation is followed by another complete fresh lane; the
passing targeted case is not used to hide the two failures.

The zero-findings/non-empty-gaps discovery is not yet added to the closed table:
it has no reviewed collected deterministic selector, and recording a pending
selector as a deterministic regression would fabricate evidence. Its proposed
lowest seam is the Wave2 node semantic-floor boundary; proposal/design review
must define the rule and red selector before it receives a discovery row.

## Workflow

1. Record the discovery before fixing it, including scenario id and redacted
   attempt evidence.
2. Classify the lowest stable seam and decide whether the behavior can be
   replayed without the provider.
3. For deterministic defects, add the smallest red test at that seam before the
   fix and retain its exact collected selector in the table.
4. For provider-only behavior, keep the live scenario, bounded attempt report,
   and rationale. Do not replace it with a tautological fake.
5. A release discovery is not closed until its deterministic regression passes
   or its provider-only live result is reviewed explicitly.
