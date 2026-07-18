"""Validated source, citation, synthesis, and labeled quality metrics.

@impl EVH-002
"""

from __future__ import annotations

import pytest

from tests.eval.metrics import (
    MetricStatus,
    ValidatedEvaluationOutcome,
    compute_contradiction_recall,
    compute_distinct_canonical_url_count,
    compute_distinct_normalized_host_count,
    compute_final_citation_completeness,
    compute_semantic_unsupported_major_claim_count,
    compute_structural_missing_backing_ref_count,
    compute_synthesis_finding_support_coverage,
)


def _outcome(**overrides: object) -> ValidatedEvaluationOutcome:
    values: dict[str, object] = {
        "selected_metric_ids": (
            "distinct-canonical-url-count",
            "distinct-normalized-host-count",
            "final-citation-completeness",
            "synthesis-finding-support-coverage",
            "structural-missing-backing-ref-count",
            "unsupported-major-claim-count",
            "contradiction-recall",
        ),
        "accepted_ledger_records": (
            {
                "submission_ref": "h_record_a",
                "source_refs": (
                    {"source_id": "source:provider-a", "canonical_url": "https://Example.invalid:443/a"},
                    {"source_id": "source:provider-b", "canonical_url": "https://example.invalid/a"},
                ),
            },
            {
                "submission_ref": "h_record_b",
                "source_refs": ({"source_id": "source:provider-a", "canonical_url": "https://sub.example.invalid/b"},),
            },
        ),
        "topic_question_bindings": None,
        "synthesis_findings": (
            {"finding_id": "finding:a", "backing_refs": ("h_record_a",)},
            {"finding_id": "finding:b", "backing_refs": ("h_missing",)},
            {"finding_id": "finding:c", "backing_refs": ()},
        ),
        "synthesis_gaps": None,
        "final_citation_map": (
            {"claim_id": "claim:a", "citation_refs": ("h_record_a",)},
            {"claim_id": "claim:b", "citation_refs": ()},
        ),
        "labeled_expectations": (
            {"claim_id": "claim:a", "submission_ref": "h_record_a", "judgment": "supports"},
            {"claim_id": "claim:b", "submission_ref": "h_record_b", "judgment": "unsupported", "major": True},
            {"claim_id": "claim:c", "submission_ref": "h_record_b", "judgment": "contradicts", "major": True},
            {"claim_id": "claim:d", "submission_ref": "h_record_a", "judgment": "expected_contradiction"},
            {"claim_id": "claim:c", "submission_ref": "h_record_b", "judgment": "expected_contradiction"},
        ),
    }
    values.update(overrides)
    return ValidatedEvaluationOutcome(**values)


def test_source_counts_use_validated_canonical_urls_and_normalized_hosts() -> None:
    outcome = _outcome()
    urls = compute_distinct_canonical_url_count(outcome)
    hosts = compute_distinct_normalized_host_count(outcome)
    assert urls.status is MetricStatus.MEASURED
    assert urls.value == 2
    assert urls.evidence_basis == ("accepted-source-refs:3", "distinct-canonical-urls:2")
    assert hosts.value == 2
    assert hosts.evidence_basis == ("accepted-source-refs:3", "distinct-normalized-hosts:2")


def test_provider_local_source_id_changes_cannot_inflate_source_counts() -> None:
    records = (
        {
            "submission_ref": "h_record_a",
            "source_refs": (
                {"source_id": "source:one", "canonical_url": "https://example.invalid/a"},
                {"source_id": "source:two", "canonical_url": "https://example.invalid/a"},
            ),
        },
    )
    outcome = _outcome(accepted_ledger_records=records)
    assert compute_distinct_canonical_url_count(outcome).value == 1
    assert compute_distinct_normalized_host_count(outcome).value == 1


def test_validated_empty_source_collection_measures_zero_counts() -> None:
    outcome = _outcome(accepted_ledger_records=())
    assert compute_distinct_canonical_url_count(outcome).value == 0
    assert compute_distinct_normalized_host_count(outcome).value == 0


def test_final_citation_completeness_is_separate_from_synthesis_support_coverage() -> None:
    outcome = _outcome()
    final = compute_final_citation_completeness(outcome)
    synthesis = compute_synthesis_finding_support_coverage(outcome)
    assert final.value == 0.5
    assert final.authoritative_denominator == 2
    assert synthesis.value == 1 / 3
    assert synthesis.authoritative_denominator == 3


def test_structural_missing_refs_are_separate_from_semantic_unsupported_claims() -> None:
    outcome = _outcome()
    missing = compute_structural_missing_backing_ref_count(outcome)
    unsupported = compute_semantic_unsupported_major_claim_count(outcome)
    assert missing.value == 2
    assert missing.evidence_basis == ("synthesis-findings:3", "missing-backing-refs:2")
    assert unsupported.value == 1
    assert unsupported.evidence_basis == ("labeled-major-claims:2", "semantic-unsupported-major-claims:1")


def test_labeled_contradiction_recall_uses_expected_and_observed_labels() -> None:
    result = compute_contradiction_recall(_outcome())
    assert result.status is MetricStatus.MEASURED
    assert result.value == 0.5
    assert result.authoritative_denominator == 2


def test_semantic_metrics_are_insufficient_without_labels() -> None:
    outcome = _outcome(labeled_expectations=None)
    assert compute_semantic_unsupported_major_claim_count(outcome).status is MetricStatus.INSUFFICIENT_AUTHORITY
    assert compute_contradiction_recall(outcome).status is MetricStatus.INSUFFICIENT_AUTHORITY
    empty = _outcome(labeled_expectations=())
    assert compute_semantic_unsupported_major_claim_count(empty).status is MetricStatus.INSUFFICIENT_AUTHORITY
    assert compute_contradiction_recall(empty).status is MetricStatus.INSUFFICIENT_AUTHORITY


def test_selected_empty_ratio_denominators_are_insufficient_not_perfect() -> None:
    outcome = _outcome(synthesis_findings=(), final_citation_map=(), labeled_expectations=())
    assert compute_final_citation_completeness(outcome).status is MetricStatus.INSUFFICIENT_AUTHORITY
    assert compute_synthesis_finding_support_coverage(outcome).status is MetricStatus.INSUFFICIENT_AUTHORITY
    assert compute_contradiction_recall(outcome).status is MetricStatus.INSUFFICIENT_AUTHORITY


def test_source_metrics_fail_closed_on_missing_source_authority_or_invalid_url() -> None:
    missing_sources = _outcome(accepted_ledger_records=({"submission_ref": "h_record_a"},))
    with pytest.raises(ValueError, match="accepted_source_refs_invalid"):
        compute_distinct_canonical_url_count(missing_sources)
    invalid_url = _outcome(
        accepted_ledger_records=(
            {
                "submission_ref": "h_record_a",
                "source_refs": ({"source_id": "source:a", "canonical_url": "not-a-url"},),
            },
        )
    )
    with pytest.raises(ValueError, match="accepted_source_url_invalid"):
        compute_distinct_normalized_host_count(invalid_url)
