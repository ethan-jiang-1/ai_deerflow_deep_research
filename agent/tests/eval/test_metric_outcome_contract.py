"""Typed metric availability and validated-outcome contracts.

@impl EVH-002
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from tests.eval.metrics import (
    MetricStatus,
    MetricValueKind,
    ValidatedEvaluationOutcome,
    evaluate_metric_result,
    insufficient_authority,
    measured,
)


def _outcome(**overrides: object) -> ValidatedEvaluationOutcome:
    values: dict[str, object] = {
        "selected_metric_ids": ("citation-binding-rate", "accepted-authority-count"),
        "accepted_ledger_records": (),
        "topic_question_bindings": None,
        "synthesis_findings": None,
        "synthesis_gaps": None,
        "final_citation_map": None,
        "labeled_expectations": None,
    }
    values.update(overrides)
    return ValidatedEvaluationOutcome(**values)


def test_validated_outcome_preserves_missing_empty_and_present_authority() -> None:
    outcome = _outcome(accepted_ledger_records=(), synthesis_findings=({"finding_id": "finding:a"},))
    assert outcome.accepted_ledger_records == ()
    assert outcome.topic_question_bindings is None
    assert outcome.synthesis_findings == ((("finding_id", "finding:a"),),)
    with pytest.raises(FrozenInstanceError):
        outcome.accepted_ledger_records = None  # type: ignore[misc]


@pytest.mark.parametrize(
    "overrides",
    [
        {"selected_metric_ids": ()},
        {"selected_metric_ids": ("Bad Metric",)},
        {"selected_metric_ids": ("citation-binding-rate", "citation-binding-rate")},
        {"accepted_ledger_records": ["not-frozen-input"]},
        {"final_citation_map": ({"claim_id": object()},)},
    ],
)
def test_validated_outcome_rejects_invalid_or_mutable_inputs(overrides: dict[str, object]) -> None:
    with pytest.raises(ValueError, match="validated_outcome"):
        _outcome(**overrides)


def test_unselected_metric_is_not_applicable_with_null_value() -> None:
    result = evaluate_metric_result(
        _outcome(),
        "must-answer-coverage",
        required_authorities=("topic_question_bindings",),
        value=None,
    )
    assert result.status is MetricStatus.NOT_APPLICABLE
    assert result.value is None
    assert result.value_kind is MetricValueKind.RATIO


def test_selected_metric_with_missing_authority_is_insufficient_with_null_value() -> None:
    result = evaluate_metric_result(
        _outcome(),
        "citation-binding-rate",
        required_authorities=("final_citation_map",),
        value=None,
    )
    assert result.status is MetricStatus.INSUFFICIENT_AUTHORITY
    assert result.value is None


def test_valid_empty_count_authority_can_measure_numeric_zero() -> None:
    result = evaluate_metric_result(
        _outcome(),
        "accepted-authority-count",
        required_authorities=("accepted_ledger_records",),
        value=0,
        evidence_basis=("accepted-ledger-records:validated-empty",),
    )
    assert result.status is MetricStatus.MEASURED
    assert result.value == 0
    assert isinstance(result.value, int)


def test_sufficient_ratio_authority_is_numeric_measured() -> None:
    result = evaluate_metric_result(
        _outcome(final_citation_map=({"claim_id": "claim:a"},)),
        "citation-binding-rate",
        required_authorities=("final_citation_map",),
        value=0.5,
        authoritative_denominator=2,
        evidence_basis=("bound-citations:1", "authoritative-citations:2"),
    )
    assert result.status is MetricStatus.MEASURED
    assert result.value == 0.5


def test_selected_labeled_metric_requires_labeled_authority() -> None:
    outcome = _outcome(selected_metric_ids=("labeled-citation-precision",))
    result = evaluate_metric_result(
        outcome,
        "labeled-citation-precision",
        required_authorities=("accepted_ledger_records", "labeled_expectations"),
        value=None,
    )
    assert result.status is MetricStatus.INSUFFICIENT_AUTHORITY
    assert result.evidence_basis == ("labeled-expectations:missing",)


def test_selected_ratio_with_empty_authoritative_denominator_is_insufficient() -> None:
    outcome = _outcome(final_citation_map=())
    result = evaluate_metric_result(
        outcome,
        "citation-binding-rate",
        required_authorities=("final_citation_map",),
        value=None,
        authoritative_denominator=0,
    )
    assert result.status is MetricStatus.INSUFFICIENT_AUTHORITY
    assert result.value is None
    assert result.evidence_basis == ("authoritative-denominator:empty",)


@pytest.mark.parametrize(
    "factory",
    [
        lambda: measured(
            "citation-binding-rate",
            value_kind=MetricValueKind.RATIO,
            value=0,
            authoritative_denominator=0,
            evidence_basis=("empty-denominator",),
        ),
        lambda: measured(
            "accepted-authority-count",
            value_kind=MetricValueKind.COUNT,
            value=0.5,
            authoritative_denominator=None,
            evidence_basis=("accepted-ledger-records",),
        ),
        lambda: insufficient_authority(
            "citation-binding-rate",
            value_kind=MetricValueKind.RATIO,
            evidence_basis=(),
        ),
    ],
)
def test_metric_result_rejects_vacuous_ratio_wrong_numeric_type_or_missing_basis(factory) -> None:
    with pytest.raises(ValueError, match="metric_result"):
        factory()
