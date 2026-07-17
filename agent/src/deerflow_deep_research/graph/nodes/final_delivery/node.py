"""Real final delivery node — writer, integrity gate, terminal lifecycle.

@impl FID-001
@impl FID-002
@impl FID-003
@impl FID-004
@impl FID-005
"""

from __future__ import annotations

from typing import Any

from deerflow_deep_research.domain.lifecycle import LifecycleStatus, TerminalReason
from deerflow_deep_research.domain.node_spec import NodeBuildDependencies
from deerflow_deep_research.domain.state import PhaseStatus
from deerflow_deep_research.engine.fake_control import node_update

from .writer import format_report


def build_real(dependencies: NodeBuildDependencies):
    if dependencies.publication_bundle is None:
        raise ValueError("publication_bundle_capability_missing")

    async def run(state: dict[str, Any]) -> dict[str, Any]:
        report_plan_ref = state.get("readiness_report_plan")
        accepted_refs = tuple(state.get("accepted_submission_refs") or ())

        # 1. Format report
        report_text, claim_map = format_report(report_plan_ref, accepted_refs)
        report_bytes = report_text.encode("utf-8")
        claim_bytes = __import__("json").dumps(claim_map, indent=2).encode("utf-8")

        report_ref, claim_ref = await dependencies.publication_bundle.publish_final(report_bytes, claim_bytes)

        return {
            **node_update(
                "final_delivery",
                terminal_status=LifecycleStatus.COMPLETED.value,
                phase_status=PhaseStatus.TERMINAL.value,
                terminal_reason=TerminalReason.COMPLETED.value,
            ),
            "report_refs": (report_ref, claim_ref),
        }

    return run
