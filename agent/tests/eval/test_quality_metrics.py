"""Independent worked examples for quality metrics and hard invariants.

@impl EVH-002
"""

from __future__ import annotations

import pytest

from tests.eval.metrics import assert_hard_invariants, compute_metrics


def test_extended_quality_metrics_use_independent_worked_example() -> None:
    outcome = {
        "accepted_submission_refs": ("ref:1", "ref:2"),
        "must_answer_questions": ("Q1", "Q2"),
        "major_claims": (
            {"claim_id": "c1", "citation_refs": ("ref:1",), "support_refs": ("ref:1",)},
            {"claim_id": "c2", "citation_refs": (), "support_refs": ()},
        ),
        "expected_contradiction_ids": ("x1", "x2"),
        "found_contradiction_ids": ("x2",),
    }
    metrics = compute_metrics(outcome)
    assert metrics["citation_completeness"] == 0.5
    assert metrics["contradiction_recall"] == 0.5
    assert metrics["unsupported_major_claims"] == 1


def test_hard_invariant_failure_is_not_a_quality_score() -> None:
    with pytest.raises(AssertionError, match="forged_submission"):
        assert_hard_invariants({"hard_invariant_failures": ("forged_submission",)})
    assert_hard_invariants({"hard_invariant_failures": ()})
