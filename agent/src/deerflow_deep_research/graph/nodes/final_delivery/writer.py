"""Deterministic final writer — report plan to report.md + claim-citation-map.

@impl FID-001
"""

from __future__ import annotations

from typing import Any

from deerflow_deep_research.domain.state import ContentRef


def format_report(
    report_plan_ref: ContentRef | None,
    accepted_submission_refs: tuple[str, ...],
) -> tuple[str, dict[str, Any]]:
    """Produce report.md text and claim-citation-map from the report plan.

    Deterministic formatter. LLM writer agent is a deferred follow-up.
    """
    lines: list[str] = [
        "# Deep Research Report",
        "",
        f"*Evidence base: {len(accepted_submission_refs)} accepted submissions*",
        "",
        "## Findings",
        "",
    ]

    claim_map: dict[str, list[str]] = {}

    if report_plan_ref is not None:
        lines.append(f"*Report plan: {report_plan_ref.sandbox_path}*")
        lines.append("")
        for i, ref in enumerate(accepted_submission_refs):
            cid = f"claim-{i + 1}"
            claim_map[cid] = [str(ref)]
            lines.append(f"- **{cid}**: sourced from {ref}")
    else:
        lines.append("No readiness report plan available.")

    report_text = "\n".join(lines) + "\n"

    citation_map: dict[str, Any] = {
        "schema_version": 1,
        "claims": {cid: {"backing_refs": refs} for cid, refs in claim_map.items()},
    }

    return report_text, citation_map


__all__ = ["format_report"]
