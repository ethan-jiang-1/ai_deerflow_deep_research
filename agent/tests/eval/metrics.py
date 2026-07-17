"""Quality metrics — pure functions on checkpoint state. Zero API, zero I/O.

@impl EVH-002
"""

from __future__ import annotations

from typing import Any


def compute_citation_precision(state: dict[str, Any]) -> float:
    """Fraction of accepted submission refs that have valid format (start with 'ref:')."""
    refs = state.get("accepted_submission_refs") or ()
    if not refs:
        return 0.0
    valid = sum(1 for r in refs if isinstance(r, str) and r.startswith("ref:"))
    return valid / len(refs)


def compute_must_answer_coverage(state: dict[str, Any]) -> float:
    """Fraction of must-answer questions that have at least one accepted submission."""
    questions = state.get("must_answer_questions") or ()
    refs = state.get("accepted_submission_refs") or ()
    if not questions:
        return 1.0
    if not refs:
        return 0.0
    # Simplified: each accepted submission counts as covering one question
    covered = min(len(refs), len(questions))
    return covered / len(questions)


def compute_source_diversity(state: dict[str, Any]) -> int:
    """Count of unique accepted submission refs."""
    refs = state.get("accepted_submission_refs") or ()
    unique = len(set(str(r) for r in refs if isinstance(r, str)))
    return unique


def compute_citation_completeness(outcome: dict[str, Any]) -> float:
    major_claims = tuple(outcome.get("major_claims") or ())
    if not major_claims:
        return 1.0
    cited = sum(1 for claim in major_claims if claim.get("citation_refs"))
    return cited / len(major_claims)


def compute_contradiction_recall(outcome: dict[str, Any]) -> float:
    expected = set(outcome.get("expected_contradiction_ids") or ())
    if not expected:
        return 1.0
    found = set(outcome.get("found_contradiction_ids") or ())
    return len(expected & found) / len(expected)


def count_unsupported_major_claims(outcome: dict[str, Any]) -> int:
    return sum(1 for claim in outcome.get("major_claims") or () if not claim.get("support_refs"))


def assert_hard_invariants(outcome: dict[str, Any]) -> None:
    failures = tuple(outcome.get("hard_invariant_failures") or ())
    if failures:
        raise AssertionError(f"hard invariants failed: {', '.join(str(value) for value in failures)}")


def compute_metrics(state: dict[str, Any]) -> dict[str, Any]:
    """Compute all quality metrics from a checkpoint state snapshot."""
    return {
        "citation_precision": compute_citation_precision(state),
        "citation_completeness": compute_citation_completeness(state),
        "must_answer_coverage": compute_must_answer_coverage(state),
        "source_diversity": compute_source_diversity(state),
        "contradiction_recall": compute_contradiction_recall(state),
        "unsupported_major_claims": count_unsupported_major_claims(state),
    }


__all__ = [
    "compute_citation_precision",
    "compute_citation_completeness",
    "compute_contradiction_recall",
    "compute_metrics",
    "compute_must_answer_coverage",
    "compute_source_diversity",
    "count_unsupported_major_claims",
    "assert_hard_invariants",
]
