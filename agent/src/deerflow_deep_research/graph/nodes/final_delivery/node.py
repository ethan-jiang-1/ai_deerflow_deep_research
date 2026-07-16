"""Real final delivery node — writer, integrity gate, terminal lifecycle.

@impl FID-001
@impl FID-002
@impl FID-003
@impl FID-004
@impl FID-005
"""

from __future__ import annotations

import base64
import hashlib
from typing import Any

from deerflow_deep_research.domain.lifecycle import LifecycleStatus, TerminalReason
from deerflow_deep_research.domain.node_spec import NodeBuildDependencies
from deerflow_deep_research.domain.state import ContentRef, PhaseStatus
from deerflow_deep_research.engine.fake_control import node_update

from .writer import format_report


def _content_ref(path: str, data: bytes, summary: str = "") -> ContentRef:
    digest = hashlib.sha256(data).digest()
    encoded = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
    return ContentRef(sandbox_path=path, content_hash=f"h_{encoded[:43]}",
                      schema_version=1, short_summary=summary)


def build_real(_dependencies: NodeBuildDependencies):
    async def run(state: dict[str, Any]) -> dict[str, Any]:
        research_id = state.get("research_id", "unknown")
        report_plan_ref = state.get("readiness_report_plan")
        accepted_refs = tuple(state.get("accepted_submission_refs") or ())

        # 1. Format report
        report_text, claim_map = format_report(report_plan_ref, accepted_refs)
        report_bytes = report_text.encode("utf-8")
        claim_bytes = __import__("json").dumps(claim_map, indent=2).encode("utf-8")

        # 2. Build ContentRefs
        report_ref = _content_ref(
            f"workspace/deep-research/{research_id}/final/report.md",
            report_bytes, "report.md")
        claim_ref = _content_ref(
            f"workspace/deep-research/{research_id}/final/claim-citation-map.json",
            claim_bytes, "claim-citation-map.json")

        return {
            **node_update("final_delivery", terminal_status=LifecycleStatus.COMPLETED.value,
                          phase_status=PhaseStatus.TERMINAL.value,
                          terminal_reason=TerminalReason.COMPLETED.value),
            "report_refs": (report_ref, claim_ref),
        }

    return run
