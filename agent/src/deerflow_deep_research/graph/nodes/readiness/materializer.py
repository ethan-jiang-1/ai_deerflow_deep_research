"""Deterministic report plan materializer.

@impl REA-003
"""

from __future__ import annotations

from .contracts import (
    ReadinessCriticOutput,
    ReadinessReportPlan,
    ReportPlanConclusion,
    ReportPlanUncertainty,
)
from .hard_rules import HardRuleFailure


def materialize_report_plan(
    critic_output: ReadinessCriticOutput,
    hard_failures: tuple[HardRuleFailure, ...],
) -> ReadinessReportPlan:
    """Produce an immutable report plan from critic verdicts and hard-rule results.

    - ready_substantive → writable conclusions
    - ready_insufficient_judgment → mandatory uncertainties
    - blocked_repair_required → absent from both (counted by caller)
    """
    conclusions: list[ReportPlanConclusion] = []
    uncertainties: list[ReportPlanUncertainty] = []

    for pq in critic_output.per_question:
        if pq.verdict == "ready_substantive":
            conclusions.append(
                ReportPlanConclusion(
                    question=pq.question,
                    conclusion_text=f"Evidence supports a substantive answer for: {pq.question}",
                    backing_claim_ids=pq.backing_claim_ids,
                )
            )
        elif pq.verdict == "ready_insufficient_judgment":
            uncertainties.append(
                ReportPlanUncertainty(
                    question=pq.question,
                    limitation=pq.limitation_note or "Evidence insufficient for definitive judgment.",
                )
            )

    # Provenance failures become blanket uncertainties
    for f in hard_failures:
        if f.code.startswith("provenance"):
            uncertainties.append(ReportPlanUncertainty(question="(provenance)", limitation=f.detail))

    return ReadinessReportPlan(
        schema_version=1,
        writable_conclusions=tuple(conclusions),
        mandatory_uncertainties=tuple(uncertainties),
    )


__all__ = ["materialize_report_plan"]
