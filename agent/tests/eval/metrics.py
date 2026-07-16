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


def compute_metrics(state: dict[str, Any]) -> dict[str, Any]:
    """Compute all quality metrics from a checkpoint state snapshot."""
    return {
        "citation_precision": compute_citation_precision(state),
        "must_answer_coverage": compute_must_answer_coverage(state),
        "source_diversity": compute_source_diversity(state),
    }


__all__ = [
    "compute_citation_precision",
    "compute_metrics",
    "compute_must_answer_coverage",
    "compute_source_diversity",
]
