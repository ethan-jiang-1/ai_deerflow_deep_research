"""Readiness node contracts.

@impl REA-001
@impl REA-002
@impl REA-003
"""

from __future__ import annotations

from typing import Literal

from deerflow_deep_research.domain.lifecycle import FrozenContract, ReadinessVerdict


class ReadinessRequest(FrozenContract):
    generation: int


class ReadinessResult(FrozenContract):
    route: ReadinessVerdict


class HardRuleFailure(FrozenContract):
    """One deterministic hard-rule failure. Serialized to dict for checkpoint."""

    code: str
    detail: str = ""
    refs: tuple[str, ...] = ()


class PerQuestionVerdict(FrozenContract):
    """Answerability verdict for a single must-answer question."""

    question: str
    verdict: Literal["ready_substantive", "ready_insufficient_judgment", "blocked_repair_required"]
    backing_claim_ids: tuple[str, ...] = ()
    limitation_note: str = ""


class ReadinessCriticOutput(FrozenContract):
    """Structured output from the readiness critic."""

    schema_version: int = 1
    per_question: tuple[PerQuestionVerdict, ...] = ()
    overall_limitations: tuple[str, ...] = ()
    synthesis_flaws: tuple[str, ...] = ()
    contradiction_ids: tuple[str, ...] = ()


class ReportPlanConclusion(FrozenContract):
    question: str
    conclusion_text: str
    backing_claim_ids: tuple[str, ...]


class ReportPlanUncertainty(FrozenContract):
    question: str
    limitation: str


class ReportPlanProhibitedUpgrade(FrozenContract):
    claim_id: str
    stated_strength: str
    allowed_strength: str


class ReadinessReportPlan(FrozenContract):
    """Immutable projection of what the final writer may and must include."""

    schema_version: int = 1
    writable_conclusions: tuple[ReportPlanConclusion, ...] = ()
    mandatory_uncertainties: tuple[ReportPlanUncertainty, ...] = ()
    prohibited_upgrades: tuple[ReportPlanProhibitedUpgrade, ...] = ()


CONTRACTS = (ReadinessRequest, ReadinessResult)
