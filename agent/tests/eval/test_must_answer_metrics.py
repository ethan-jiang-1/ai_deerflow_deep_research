"""Must-answer coverage through planner and synthesis topic authority.

@impl EVH-002
"""

from __future__ import annotations

import pytest

from tests.eval.metrics import MetricStatus, ValidatedEvaluationOutcome, compute_must_answer_coverage


def _outcome(**overrides: object) -> ValidatedEvaluationOutcome:
    values: dict[str, object] = {
        "selected_metric_ids": ("must-answer-coverage",),
        "accepted_ledger_records": None,
        "topic_question_bindings": (
            {"question_id": "q:a", "topic_ids": ("topic:a", "topic:b")},
            {"question_id": "q:b", "topic_ids": ("topic:c",)},
            {"question_id": "q:c", "topic_ids": ("topic:d",)},
        ),
        "synthesis_findings": (
            {"finding_id": "finding:a", "affected_topics": ("topic:a",)},
            {"finding_id": "finding:c", "affected_topics": ("topic:c", "topic:unknown")},
        ),
        "synthesis_gaps": ({"gap_id": "gap:b", "affected_topics": ("topic:b",)},),
        "final_citation_map": None,
        "labeled_expectations": None,
    }
    values.update(overrides)
    return ValidatedEvaluationOutcome(**values)


def test_must_answer_coverage_joins_questions_to_topics_then_findings_or_gaps() -> None:
    evaluation = compute_must_answer_coverage(_outcome())
    assert evaluation.result.status is MetricStatus.MEASURED
    assert evaluation.result.value == 2 / 3
    assert evaluation.result.authoritative_denominator == 3
    assert evaluation.covered_question_ids == ("q:a", "q:b")
    assert evaluation.partial_question_ids == ()
    assert evaluation.uncovered_question_ids == ("q:c",)
    assert evaluation.missing_topic_ids == ("topic:d",)
    assert evaluation.unknown_synthesis_topic_ids == ("topic:unknown",)
    assert evaluation.unmapped_planned_topic_ids == ("topic:d",)


def test_question_is_partial_when_only_some_known_bound_topics_are_represented() -> None:
    outcome = _outcome(
        synthesis_findings=({"finding_id": "finding:a", "affected_topics": ("topic:a",)},),
        synthesis_gaps=(),
    )
    evaluation = compute_must_answer_coverage(outcome)
    assert evaluation.result.value == 0.0
    assert evaluation.covered_question_ids == ()
    assert evaluation.partial_question_ids == ("q:a",)
    assert evaluation.uncovered_question_ids == ("q:b", "q:c")
    assert evaluation.missing_topic_ids == ("topic:b", "topic:c", "topic:d")


def test_typed_gap_representation_counts_as_honest_topic_coverage() -> None:
    outcome = _outcome(
        topic_question_bindings=({"question_id": "q:a", "topic_ids": ("topic:a",)},),
        synthesis_findings=(),
        synthesis_gaps=({"gap_id": "gap:a", "affected_topics": ("topic:a",)},),
    )
    evaluation = compute_must_answer_coverage(outcome)
    assert evaluation.result.status is MetricStatus.MEASURED
    assert evaluation.result.value == 1.0


def test_missing_or_empty_question_authority_is_insufficient() -> None:
    assert compute_must_answer_coverage(_outcome(topic_question_bindings=None)).result.status is (
        MetricStatus.INSUFFICIENT_AUTHORITY
    )
    assert compute_must_answer_coverage(_outcome(topic_question_bindings=())).result.status is (
        MetricStatus.INSUFFICIENT_AUTHORITY
    )


def test_unselected_must_answer_metric_is_not_applicable() -> None:
    evaluation = compute_must_answer_coverage(
        _outcome(selected_metric_ids=("accepted-authority-count",), topic_question_bindings=None)
    )
    assert evaluation.result.status is MetricStatus.NOT_APPLICABLE


@pytest.mark.parametrize(
    "overrides",
    [
        {"topic_question_bindings": ({"question_id": "q:a", "topic_ids": ()},)},
        {
            "topic_question_bindings": (
                {"question_id": "q:a", "topic_ids": ("topic:a",)},
                {"question_id": "q:a", "topic_ids": ("topic:b",)},
            )
        },
        {"synthesis_findings": ({"finding_id": "finding:a", "affected_topics": (1,)},)},
    ],
)
def test_must_answer_coverage_rejects_malformed_authority(overrides: dict[str, object]) -> None:
    with pytest.raises(ValueError, match="must_answer_authority_invalid"):
        compute_must_answer_coverage(_outcome(**overrides))
