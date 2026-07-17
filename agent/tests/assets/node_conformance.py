"""Collected success and highest-risk selectors for every real node.

@impl EVH-007
@impl EVH-008
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass


@dataclass(frozen=True)
class NodeConformance:
    logical_name: str
    success_selector: str
    risk_selector: str
    highest_risk: str


class NodeConformanceError(ValueError):
    pass


NODE_CONFORMANCE = (
    NodeConformance(
        "bootstrap",
        "tests/graph/test_bootstrap_node.py::TestBuildRealRoutesOnBinding::test_bound_marker_routes_needs_input_with_no_model_call",
        "tests/graph/test_bootstrap_node.py::TestBuildRealRoutesOnBinding::test_divergent_read_back_fails_closed_terminal",
        "bundle identity divergence fails closed",
    ),
    NodeConformance(
        "hitl1",
        "tests/graph/test_hitl1_node.py::test_complete_response_writes_profile_and_routes_accepted",
        "tests/graph/test_hitl1_node.py::test_run_agent_failure_exhausts_without_partial_state",
        "model failure cannot publish profile state",
    ),
    NodeConformance(
        "topic_planning",
        "tests/graph/test_topic_planning_node.py::test_valid_plan_routes_next_and_records_registry",
        "tests/graph/test_topic_planning_node.py::test_repeated_invalid_plan_exhausts_without_topic_state",
        "repeated malformed planning output blocks before Wave0",
    ),
    NodeConformance(
        "wave0",
        "tests/integration/test_wave0_lifecycle.py::test_mixed_wave0_complete_lifecycle",
        "tests/integration/test_wave0_lifecycle.py::test_wave0_blocked_when_worker_fails_every_topic",
        "all worker attempts fail and exhaust without accepted evidence",
    ),
    NodeConformance(
        "wave1",
        "tests/integration/test_wave1_work_units.py::test_real_wave1_crosses_worker_context_artifact_validator_and_ledger",
        "tests/integration/test_wave1_work_units.py::test_real_wave1_malformed_output_becomes_typed_worker_failure_without_ledger",
        "malformed worker output becomes typed failure before ledger publication",
    ),
    NodeConformance(
        "wave2_synthesis",
        "tests/graph/test_wave2_synthesis_real.py::test_real_synthesis_uses_node_context_and_materializes_canonical_findings",
        "tests/graph/test_wave2_synthesis_real.py::test_real_synthesis_malformed_output_fails_without_artifact",
        "malformed synthesis output cannot publish findings",
    ),
    NodeConformance(
        "targeted_evidence",
        "tests/graph/test_targeted_evidence_real.py::test_source_diagnostic_uses_node_context_and_materializes_validated_artifact",
        "tests/graph/test_targeted_evidence_real.py::test_source_diagnostic_malformed_output_fails_without_artifact",
        "malformed critic output cannot publish a verdict artifact",
    ),
    NodeConformance(
        "hitl2",
        "tests/unit/test_hitl2_real.py::TestRealHitl2Factory::test_proceed_route",
        "tests/unit/test_hitl2_real.py::TestRealHitl2Factory::test_stale_request_id_rejected",
        "stale human response cannot control routing",
    ),
    NodeConformance(
        "rerun",
        "tests/unit/test_rerun_real.py::TestRealRerunFactory::test_full_scope_full_lifecycle",
        "tests/unit/test_rerun_real.py::TestRealRerunFactory::test_generation_at_ceiling_exhausted",
        "generation ceiling terminates the rerun loop",
    ),
    NodeConformance(
        "readiness",
        "tests/unit/test_readiness_real.py::TestRealReadiness::test_all_clear_routes_pass",
        "tests/unit/test_readiness_real.py::TestRealReadiness::test_no_evidence_routes_exhausted",
        "missing evidence is a hard readiness failure",
    ),
    NodeConformance(
        "final_delivery",
        "tests/unit/test_final_delivery_real.py::TestRealFinalDelivery::test_produces_report_refs_and_completed",
        "tests/unit/test_final_delivery_real.py::TestRealFinalDelivery::test_handles_empty_evidence",
        "delivery does not assume evidence authority that belongs to readiness",
    ),
)


def validate_node_conformance(
    entries: Iterable[NodeConformance],
    collected_selectors: set[str],
    *,
    registered_names: set[str],
) -> None:
    entries = tuple(entries)
    names = {entry.logical_name for entry in entries}
    errors: list[str] = []
    if names != registered_names:
        missing = sorted(registered_names - names)
        extra = sorted(names - registered_names)
        errors.append(f"registered node mismatch: missing={missing} extra={extra}")
    for entry in entries:
        for label, selector in (("success", entry.success_selector), ("risk", entry.risk_selector)):
            if selector not in collected_selectors:
                errors.append(f"{entry.logical_name}: stale {label} selector {selector}")
    if errors:
        raise NodeConformanceError("\n".join(errors))


__all__ = ["NODE_CONFORMANCE", "NodeConformance", "NodeConformanceError", "validate_node_conformance"]
