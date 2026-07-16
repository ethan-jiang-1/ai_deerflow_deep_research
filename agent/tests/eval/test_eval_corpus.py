"""Replay-based eval corpus — deterministic scenarios with FakeToolCallingModel.

@impl EVH-001
"""

from __future__ import annotations

import pytest

from tests.eval.metrics import compute_metrics


class TestQuickFactual:
    """Quick factual: answer is clear, sources are easy to verify."""

    def test_citation_precision_with_valid_refs(self) -> None:
        state = {
            "accepted_submission_refs": ("ref:1", "ref:2", "ref:3"),
            "must_answer_questions": ("What is X?",),
        }
        metrics = compute_metrics(state)
        assert metrics["citation_precision"] == 1.0

    def test_citation_precision_with_mixed_refs(self) -> None:
        state = {
            "accepted_submission_refs": ("ref:1", "bad-format", "ref:3"),
            "must_answer_questions": ("Q1",),
        }
        metrics = compute_metrics(state)
        assert metrics["citation_precision"] == 2.0 / 3.0


class TestClaimVerification:
    """Claim verification: evidence supports, refutes, or is uncertain."""

    def test_source_diversity_counts_unique_refs(self) -> None:
        state = {
            "accepted_submission_refs": ("ref:1", "ref:2", "ref:2", "ref:3"),
        }
        assert compute_metrics(state)["source_diversity"] == 3

    def test_empty_refs_zero_diversity(self) -> None:
        state: dict = {"accepted_submission_refs": ()}
        assert compute_metrics(state)["source_diversity"] == 0


class TestInsufficientEvidence:
    """Insufficient evidence: correctly reports inability to answer."""

    def test_no_evidence_zero_coverage(self) -> None:
        state = {
            "accepted_submission_refs": (),
            "must_answer_questions": ("Q1", "Q2"),
        }
        metrics = compute_metrics(state)
        assert metrics["must_answer_coverage"] == 0.0

    def test_no_questions_full_coverage(self) -> None:
        state = {
            "accepted_submission_refs": ("ref:1",),
            "must_answer_questions": (),
        }
        metrics = compute_metrics(state)
        assert metrics["must_answer_coverage"] == 1.0
