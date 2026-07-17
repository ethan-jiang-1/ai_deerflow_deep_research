"""Deterministic hard checks for readiness.

@impl REA-001
@impl REA-005
"""

from __future__ import annotations

from typing import Any

from deerflow_deep_research.domain.work_units import CONTENT_HASH_RE

from .contracts import HardRuleFailure


def check_citation_availability(state: dict[str, Any]) -> tuple[HardRuleFailure, ...]:
    """Accepted submissions must be non-empty."""
    refs = state.get("accepted_submission_refs") or ()
    if not refs:
        return (HardRuleFailure(code="citation_no_accepted_evidence", detail="No accepted submissions exist."),)
    return ()


def check_provenance(state: dict[str, Any]) -> tuple[HardRuleFailure, ...]:
    """Every accepted ref must be a canonical submission-ledger record hash."""
    refs = state.get("accepted_submission_refs") or ()
    failures: list[HardRuleFailure] = []
    for ref in refs:
        if not isinstance(ref, str) or not CONTENT_HASH_RE.fullmatch(ref):
            failures.append(
                HardRuleFailure(code="provenance_invalid_ref", detail=f"Invalid ref format: {ref!r}", refs=(str(ref),))
            )
    return tuple(failures)


def check_hitl2_consumption(state: dict[str, Any]) -> tuple[HardRuleFailure, ...]:
    """At least one HITL request must have been consumed."""
    consumed = state.get("consumed_request_ids") or ()
    if not consumed:
        return (HardRuleFailure(code="hitl2_not_consumed", detail="No HITL2 request consumed."),)
    return ()


def run_hard_rules(state: dict[str, Any]) -> tuple[HardRuleFailure, ...]:
    """Collect-all: run every hard rule, return all failures."""
    return (
        *check_citation_availability(state),
        *check_provenance(state),
        *check_hitl2_consumption(state),
    )


def has_structural_failure(failures: tuple[HardRuleFailure, ...]) -> bool:
    """True if any failure is a structural precondition failure that blocks readiness."""
    return len(failures) > 0


__all__ = [
    "check_citation_availability",
    "check_hitl2_consumption",
    "check_provenance",
    "has_structural_failure",
    "run_hard_rules",
]
