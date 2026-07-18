"""Structural citation binding and labeled semantic precision examples.

@impl EVH-002
"""

from __future__ import annotations

import pytest

from tests.eval.metrics import (
    MetricStatus,
    ValidatedEvaluationOutcome,
    compute_citation_binding_rate,
    compute_labeled_citation_precision,
)


def _outcome(**overrides: object) -> ValidatedEvaluationOutcome:
    values: dict[str, object] = {
        "selected_metric_ids": ("citation-binding-rate", "labeled-citation-precision"),
        "accepted_ledger_records": (
            {"submission_ref": "h_accepted_a"},
            {"submission_ref": "h_accepted_b"},
        ),
        "topic_question_bindings": None,
        "synthesis_findings": None,
        "synthesis_gaps": None,
        "final_citation_map": (
            {"claim_id": "claim:a", "citation_refs": ("h_accepted_a", "h_missing")},
            {"claim_id": "claim:b", "citation_refs": ("h_accepted_b",)},
        ),
        "labeled_expectations": (
            {"claim_id": "claim:a", "submission_ref": "h_accepted_a", "judgment": "supports"},
            {"claim_id": "claim:a", "submission_ref": "h_missing", "judgment": "unsupported"},
            {"claim_id": "claim:b", "submission_ref": "h_accepted_b", "judgment": "contradicts"},
        ),
    }
    values.update(overrides)
    return ValidatedEvaluationOutcome(**values)


def test_citation_binding_rate_uses_accepted_ledger_membership_not_ref_syntax() -> None:
    result = compute_citation_binding_rate(_outcome())
    assert result.status is MetricStatus.MEASURED
    assert result.value == 2 / 3
    assert result.authoritative_denominator == 3
    assert result.evidence_basis == ("accepted-ledger-records:2", "final-citations:3", "bound-citations:2")


def test_ref_shaped_text_without_accepted_record_is_structurally_unbound() -> None:
    outcome = _outcome(
        accepted_ledger_records=({"submission_ref": "h_accepted_a"},),
        final_citation_map=({"claim_id": "claim:a", "citation_refs": ("ref:looks-valid",)},),
    )
    result = compute_citation_binding_rate(outcome)
    assert result.status is MetricStatus.MEASURED
    assert result.value == 0.0


def test_selected_binding_rate_with_empty_citation_denominator_is_insufficient() -> None:
    result = compute_citation_binding_rate(_outcome(final_citation_map=()))
    assert result.status is MetricStatus.INSUFFICIENT_AUTHORITY
    assert result.value is None


def test_unselected_binding_rate_is_not_applicable_even_when_authority_is_missing() -> None:
    outcome = _outcome(
        selected_metric_ids=("labeled-citation-precision",),
        accepted_ledger_records=None,
        final_citation_map=None,
    )
    result = compute_citation_binding_rate(outcome)
    assert result.status is MetricStatus.NOT_APPLICABLE
    assert result.value is None


def test_labeled_semantic_precision_scores_only_labeled_cited_pairs() -> None:
    result = compute_labeled_citation_precision(_outcome())
    assert result.status is MetricStatus.MEASURED
    assert result.value == 1 / 3
    assert result.authoritative_denominator == 3
    assert result.evidence_basis == ("labeled-cited-pairs:3", "semantically-supported-pairs:1")


def test_accepted_but_unlabeled_bindings_are_insufficient_for_semantic_precision() -> None:
    outcome = _outcome(
        final_citation_map=({"claim_id": "claim:a", "citation_refs": ("h_accepted_a",)},),
        labeled_expectations=(),
    )
    result = compute_labeled_citation_precision(outcome)
    assert result.status is MetricStatus.INSUFFICIENT_AUTHORITY
    assert result.value is None
    assert result.evidence_basis == ("labeled-expectations:validated-empty",)


def test_semantic_precision_rejects_labels_that_do_not_cover_every_cited_pair() -> None:
    outcome = _outcome(
        labeled_expectations=({"claim_id": "claim:a", "submission_ref": "h_accepted_a", "judgment": "supports"},)
    )
    result = compute_labeled_citation_precision(outcome)
    assert result.status is MetricStatus.INSUFFICIENT_AUTHORITY
    assert result.value is None
    assert result.evidence_basis == ("unlabeled-cited-pairs:2",)


def test_citation_metrics_fail_closed_on_malformed_refs_or_duplicate_labels() -> None:
    malformed = _outcome(final_citation_map=({"claim_id": "claim:a", "citation_refs": (1,)},))
    with pytest.raises(ValueError, match="metric_authority_citation_refs_invalid"):
        compute_citation_binding_rate(malformed)

    duplicate = {
        "claim_id": "claim:a",
        "submission_ref": "h_accepted_a",
        "judgment": "supports",
    }
    with pytest.raises(ValueError, match="labeled_expectation_invalid"):
        compute_labeled_citation_precision(_outcome(labeled_expectations=(duplicate, duplicate)))
