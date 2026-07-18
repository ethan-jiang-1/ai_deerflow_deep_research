"""Collected success and highest-risk selectors for every real node.

@impl EVH-007
@impl EVH-008
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from tests.assets.evidence import TestEvidenceClaim


@dataclass(frozen=True)
class NodeConformance:
    logical_name: str
    success_claim_id: str
    risk_claim_id: str
    highest_risk: str


class NodeConformanceError(ValueError):
    pass


NODE_CONFORMANCE = (
    NodeConformance(
        "bootstrap",
        "bootstrap-marker-needs-input",
        "bootstrap-divergent-read-back",
        "bundle identity divergence fails closed",
    ),
    NodeConformance(
        "hitl1",
        "hitl1-complete-response",
        "hitl1-run-agent-failure",
        "model failure cannot publish profile state",
    ),
    NodeConformance(
        "topic_planning",
        "topic-planning-valid-plan",
        "topic-planning-invalid-output",
        "repeated malformed planning output blocks before Wave0",
    ),
    NodeConformance(
        "wave0",
        "wave0-complete-lifecycle",
        "wave0-all-workers-fail",
        "all worker attempts fail and exhaust without accepted evidence",
    ),
    NodeConformance(
        "wave1",
        "wave1-worker-ledger-success",
        "wave1-malformed-worker-output",
        "malformed worker output becomes typed failure before ledger publication",
    ),
    NodeConformance(
        "wave2_synthesis",
        "wave2-canonical-findings",
        "wave2-malformed-output",
        "malformed synthesis output cannot publish findings",
    ),
    NodeConformance(
        "targeted_evidence",
        "targeted-evidence-valid-artifact",
        "targeted-evidence-malformed-output",
        "malformed critic output cannot publish a verdict artifact",
    ),
    NodeConformance(
        "hitl2",
        "hitl2-proceed-route",
        "hitl2-stale-request-rejected",
        "stale human response cannot control routing",
    ),
    NodeConformance(
        "rerun",
        "rerun-full-scope-lifecycle",
        "rerun-generation-ceiling",
        "generation ceiling terminates the rerun loop",
    ),
    NodeConformance(
        "readiness",
        "readiness-all-clear",
        "readiness-no-evidence",
        "missing evidence is a hard readiness failure",
    ),
    NodeConformance(
        "final_delivery",
        "final-delivery-completed",
        "final-delivery-empty-evidence",
        "delivery does not assume evidence authority that belongs to readiness",
    ),
)


def validate_node_conformance(
    entries: Iterable[NodeConformance],
    claims: dict[str, TestEvidenceClaim],
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
        for label, claim_id in (("success", entry.success_claim_id), ("risk", entry.risk_claim_id)):
            claim = claims.get(claim_id)
            if claim is None:
                errors.append(f"{entry.logical_name}: unknown {label} claim {claim_id}")
                continue
            selector = claim.selector
            if selector not in collected_selectors:
                errors.append(f"{entry.logical_name}: {claim_id}: stale {label} selector {selector}")
    if errors:
        raise NodeConformanceError("\n".join(errors))


__all__ = ["NODE_CONFORMANCE", "NodeConformance", "NodeConformanceError", "validate_node_conformance"]
