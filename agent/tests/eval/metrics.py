"""Quality metrics — pure functions on checkpoint state. Zero API, zero I/O.

@impl EVH-002
"""

from __future__ import annotations

import math
import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any
from urllib.parse import urlsplit, urlunsplit

METRIC_ID_RE = re.compile(r"^[a-z][a-z0-9-]{2,63}$")
EVIDENCE_BASIS_RE = re.compile(r"^[a-z0-9][a-z0-9:._/-]{2,127}$")


class MetricStatus(StrEnum):
    NOT_APPLICABLE = "not_applicable"
    INSUFFICIENT_AUTHORITY = "insufficient_authority"
    MEASURED = "measured"


class MetricValueKind(StrEnum):
    COUNT = "count"
    RATIO = "ratio"


METRIC_VALUE_KINDS = {
    "accepted-authority-count": MetricValueKind.COUNT,
    "checkpoint-transition-count": MetricValueKind.COUNT,
    "citation-binding-rate": MetricValueKind.RATIO,
    "contradiction-recall": MetricValueKind.RATIO,
    "distinct-canonical-url-count": MetricValueKind.COUNT,
    "distinct-normalized-host-count": MetricValueKind.COUNT,
    "final-citation-completeness": MetricValueKind.RATIO,
    "labeled-citation-precision": MetricValueKind.RATIO,
    "must-answer-coverage": MetricValueKind.RATIO,
    "structural-missing-backing-ref-count": MetricValueKind.COUNT,
    "synthesis-finding-support-coverage": MetricValueKind.RATIO,
    "unsupported-major-claim-count": MetricValueKind.COUNT,
}

FrozenProjection = None | bool | int | float | str | tuple["FrozenProjection", ...]


@dataclass(frozen=True)
class ValidatedEvaluationOutcome:
    """Already-read authority projections; ``None`` remains distinct from validated empty."""

    selected_metric_ids: tuple[str, ...]
    accepted_ledger_records: tuple[FrozenProjection, ...] | None
    topic_question_bindings: tuple[FrozenProjection, ...] | None
    synthesis_findings: tuple[FrozenProjection, ...] | None
    synthesis_gaps: tuple[FrozenProjection, ...] | None
    final_citation_map: tuple[FrozenProjection, ...] | None
    labeled_expectations: tuple[FrozenProjection, ...] | None

    def __post_init__(self) -> None:
        metric_ids = self.selected_metric_ids
        if (
            not isinstance(metric_ids, tuple)
            or not metric_ids
            or len(set(metric_ids)) != len(metric_ids)
            or any(not isinstance(value, str) or value not in METRIC_VALUE_KINDS for value in metric_ids)
        ):
            raise ValueError("validated_outcome_metric_ids_invalid")
        for field_name in (
            "accepted_ledger_records",
            "topic_question_bindings",
            "synthesis_findings",
            "synthesis_gaps",
            "final_citation_map",
            "labeled_expectations",
        ):
            value = getattr(self, field_name)
            if value is None:
                continue
            if not isinstance(value, tuple):
                raise ValueError("validated_outcome_authority_invalid")
            try:
                frozen = tuple(_freeze_projection(item) for item in value)
            except (TypeError, ValueError) as exc:
                raise ValueError("validated_outcome_authority_invalid") from exc
            object.__setattr__(self, field_name, frozen)


@dataclass(frozen=True)
class MetricResult:
    metric_id: str
    status: MetricStatus
    value_kind: MetricValueKind
    value: int | float | None
    evidence_basis: tuple[str, ...]
    authoritative_denominator: int | None = None

    def __post_init__(self) -> None:
        if (
            not isinstance(self.metric_id, str)
            or not METRIC_ID_RE.fullmatch(self.metric_id)
            or METRIC_VALUE_KINDS.get(self.metric_id) is not self.value_kind
        ):
            raise ValueError("metric_result_identity_invalid")
        if not isinstance(self.status, MetricStatus) or not isinstance(self.value_kind, MetricValueKind):
            raise ValueError("metric_result_type_invalid")
        if (
            not isinstance(self.evidence_basis, tuple)
            or not self.evidence_basis
            or len(set(self.evidence_basis)) != len(self.evidence_basis)
            or any(
                not isinstance(value, str) or not EVIDENCE_BASIS_RE.fullmatch(value) for value in self.evidence_basis
            )
        ):
            raise ValueError("metric_result_evidence_basis_invalid")
        if self.status is not MetricStatus.MEASURED:
            if self.value is not None or self.authoritative_denominator is not None:
                raise ValueError("metric_result_unavailable_value_invalid")
            return
        if isinstance(self.value, bool) or not isinstance(self.value, (int, float)) or not math.isfinite(self.value):
            raise ValueError("metric_result_measured_value_invalid")
        if self.value_kind is MetricValueKind.COUNT:
            if not isinstance(self.value, int) or self.value < 0 or self.authoritative_denominator is not None:
                raise ValueError("metric_result_count_invalid")
            return
        if not 0 <= self.value <= 1:
            raise ValueError("metric_result_ratio_invalid")
        if (
            not isinstance(self.authoritative_denominator, int)
            or isinstance(self.authoritative_denominator, bool)
            or self.authoritative_denominator <= 0
        ):
            raise ValueError("metric_result_ratio_denominator_invalid")


@dataclass(frozen=True)
class MustAnswerCoverageEvaluation:
    result: MetricResult
    covered_question_ids: tuple[str, ...] = ()
    partial_question_ids: tuple[str, ...] = ()
    uncovered_question_ids: tuple[str, ...] = ()
    missing_topic_ids: tuple[str, ...] = ()
    unknown_synthesis_topic_ids: tuple[str, ...] = ()
    unmapped_planned_topic_ids: tuple[str, ...] = ()


def not_applicable(metric_id: str, *, evidence_basis: tuple[str, ...]) -> MetricResult:
    return MetricResult(
        metric_id=metric_id,
        status=MetricStatus.NOT_APPLICABLE,
        value_kind=_metric_kind(metric_id),
        value=None,
        evidence_basis=evidence_basis,
    )


def insufficient_authority(
    metric_id: str,
    *,
    value_kind: MetricValueKind,
    evidence_basis: tuple[str, ...],
) -> MetricResult:
    return MetricResult(
        metric_id=metric_id,
        status=MetricStatus.INSUFFICIENT_AUTHORITY,
        value_kind=value_kind,
        value=None,
        evidence_basis=evidence_basis,
    )


def measured(
    metric_id: str,
    *,
    value_kind: MetricValueKind,
    value: int | float,
    evidence_basis: tuple[str, ...],
    authoritative_denominator: int | None = None,
) -> MetricResult:
    return MetricResult(
        metric_id=metric_id,
        status=MetricStatus.MEASURED,
        value_kind=value_kind,
        value=value,
        evidence_basis=evidence_basis,
        authoritative_denominator=authoritative_denominator,
    )


def evaluate_metric_result(
    outcome: ValidatedEvaluationOutcome,
    metric_id: str,
    *,
    required_authorities: tuple[str, ...],
    value: int | float | None,
    evidence_basis: tuple[str, ...] | None = None,
    authoritative_denominator: int | None = None,
) -> MetricResult:
    """Resolve availability before accepting a caller-computed pure metric value."""
    if not isinstance(outcome, ValidatedEvaluationOutcome):
        raise TypeError("validated_outcome_required")
    kind = _metric_kind(metric_id)
    if metric_id not in outcome.selected_metric_ids:
        return not_applicable(metric_id, evidence_basis=("case:not-selected",))
    allowed_authorities = {
        "accepted_ledger_records",
        "topic_question_bindings",
        "synthesis_findings",
        "synthesis_gaps",
        "final_citation_map",
        "labeled_expectations",
    }
    if (
        not isinstance(required_authorities, tuple)
        or not required_authorities
        or len(set(required_authorities)) != len(required_authorities)
        or not set(required_authorities) <= allowed_authorities
    ):
        raise ValueError("metric_authorities_invalid")
    missing = tuple(name for name in required_authorities if getattr(outcome, name) is None)
    if missing:
        basis = tuple(f"{name.replace('_', '-')}:missing" for name in missing)
        return insufficient_authority(metric_id, value_kind=kind, evidence_basis=basis)
    if kind is MetricValueKind.RATIO and authoritative_denominator == 0:
        return insufficient_authority(
            metric_id,
            value_kind=kind,
            evidence_basis=("authoritative-denominator:empty",),
        )
    if value is None or evidence_basis is None:
        raise ValueError("metric_result_measurement_required")
    return measured(
        metric_id,
        value_kind=kind,
        value=value,
        evidence_basis=evidence_basis,
        authoritative_denominator=authoritative_denominator,
    )


def _metric_kind(metric_id: str) -> MetricValueKind:
    try:
        return METRIC_VALUE_KINDS[metric_id]
    except (KeyError, TypeError) as exc:
        raise ValueError("metric_result_identity_invalid") from exc


def _freeze_projection(value: Any) -> FrozenProjection:
    if value is None or isinstance(value, (bool, int, float, str)):
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError("projection_number_invalid")
        return value
    if isinstance(value, tuple):
        return tuple(_freeze_projection(item) for item in value)
    if isinstance(value, Mapping) and all(isinstance(key, str) for key in value):
        return tuple((key, _freeze_projection(item)) for key, item in sorted(value.items()))
    raise TypeError("projection_value_invalid")


def compute_citation_binding_rate(outcome: ValidatedEvaluationOutcome) -> MetricResult:
    metric_id = "citation-binding-rate"
    required = ("accepted_ledger_records", "final_citation_map")
    if metric_id not in outcome.selected_metric_ids or any(getattr(outcome, name) is None for name in required):
        return evaluate_metric_result(outcome, metric_id, required_authorities=required, value=None)
    accepted_records = _projection_records(outcome.accepted_ledger_records, "accepted-ledger-records")
    citation_records = _projection_records(outcome.final_citation_map, "final-citation-map")
    accepted_refs = {_required_string(record, "submission_ref") for record in accepted_records}
    cited_pairs = _citation_pairs(citation_records)
    if not cited_pairs:
        return evaluate_metric_result(
            outcome,
            metric_id,
            required_authorities=required,
            value=None,
            authoritative_denominator=0,
        )
    bound = sum(1 for _claim_id, citation_ref in cited_pairs if citation_ref in accepted_refs)
    return evaluate_metric_result(
        outcome,
        metric_id,
        required_authorities=required,
        value=bound / len(cited_pairs),
        authoritative_denominator=len(cited_pairs),
        evidence_basis=(
            f"accepted-ledger-records:{len(accepted_records)}",
            f"final-citations:{len(cited_pairs)}",
            f"bound-citations:{bound}",
        ),
    )


def compute_labeled_citation_precision(outcome: ValidatedEvaluationOutcome) -> MetricResult:
    metric_id = "labeled-citation-precision"
    required = ("final_citation_map", "labeled_expectations")
    if metric_id not in outcome.selected_metric_ids or any(getattr(outcome, name) is None for name in required):
        return evaluate_metric_result(outcome, metric_id, required_authorities=required, value=None)
    citation_records = _projection_records(outcome.final_citation_map, "final-citation-map")
    label_records = _projection_records(outcome.labeled_expectations, "labeled-expectations")
    cited_pairs = _citation_pairs(citation_records)
    if not label_records:
        return insufficient_authority(
            metric_id,
            value_kind=MetricValueKind.RATIO,
            evidence_basis=("labeled-expectations:validated-empty",),
        )
    labels: dict[tuple[str, str], str] = {}
    for record in label_records:
        key = (_required_string(record, "claim_id"), _required_string(record, "submission_ref"))
        judgment = _required_string(record, "judgment")
        if judgment not in {"supports", "contradicts", "unsupported", "uncertain"} or key in labels:
            raise ValueError("labeled_expectation_invalid")
        labels[key] = judgment
    unlabeled = sum(1 for pair in cited_pairs if pair not in labels)
    if unlabeled:
        return insufficient_authority(
            metric_id,
            value_kind=MetricValueKind.RATIO,
            evidence_basis=(f"unlabeled-cited-pairs:{unlabeled}",),
        )
    if not cited_pairs:
        return evaluate_metric_result(
            outcome,
            metric_id,
            required_authorities=required,
            value=None,
            authoritative_denominator=0,
        )
    supported = sum(1 for pair in cited_pairs if labels[pair] == "supports")
    return evaluate_metric_result(
        outcome,
        metric_id,
        required_authorities=required,
        value=supported / len(cited_pairs),
        authoritative_denominator=len(cited_pairs),
        evidence_basis=(
            f"labeled-cited-pairs:{len(cited_pairs)}",
            f"semantically-supported-pairs:{supported}",
        ),
    )


def _projection_records(values: tuple[FrozenProjection, ...] | None, authority: str) -> tuple[dict[str, Any], ...]:
    if values is None:
        raise ValueError(f"{authority}_missing")
    records: list[dict[str, Any]] = []
    for value in values:
        if not isinstance(value, tuple) or any(
            not isinstance(item, tuple) or len(item) != 2 or not isinstance(item[0], str) for item in value
        ):
            raise ValueError(f"{authority}_record_invalid")
        records.append({key: item for key, item in value})
    return tuple(records)


def _required_string(record: Mapping[str, Any], field_name: str) -> str:
    value = record.get(field_name)
    if not isinstance(value, str) or not value:
        raise ValueError(f"metric_authority_{field_name}_invalid")
    return value


def _citation_pairs(records: tuple[dict[str, Any], ...]) -> tuple[tuple[str, str], ...]:
    pairs: list[tuple[str, str]] = []
    for record in records:
        claim_id = _required_string(record, "claim_id")
        refs = record.get("citation_refs")
        if not isinstance(refs, tuple) or any(not isinstance(ref, str) or not ref for ref in refs):
            raise ValueError("metric_authority_citation_refs_invalid")
        pairs.extend((claim_id, ref) for ref in refs)
    return tuple(pairs)


def compute_must_answer_coverage(outcome: ValidatedEvaluationOutcome) -> MustAnswerCoverageEvaluation:
    metric_id = "must-answer-coverage"
    required = ("topic_question_bindings", "synthesis_findings", "synthesis_gaps")
    if metric_id not in outcome.selected_metric_ids or any(getattr(outcome, name) is None for name in required):
        return MustAnswerCoverageEvaluation(
            result=evaluate_metric_result(outcome, metric_id, required_authorities=required, value=None)
        )
    binding_records = _projection_records(outcome.topic_question_bindings, "topic-question-bindings")
    finding_records = _projection_records(outcome.synthesis_findings, "synthesis-findings")
    gap_records = _projection_records(outcome.synthesis_gaps, "synthesis-gaps")
    if not binding_records:
        return MustAnswerCoverageEvaluation(
            result=insufficient_authority(
                metric_id,
                value_kind=MetricValueKind.RATIO,
                evidence_basis=("topic-question-bindings:validated-empty",),
            )
        )

    bindings: dict[str, frozenset[str]] = {}
    try:
        for record in binding_records:
            question_id = _required_string(record, "question_id")
            topic_ids = _required_string_tuple(record, "topic_ids")
            if question_id in bindings or not topic_ids:
                raise ValueError
            bindings[question_id] = frozenset(topic_ids)
        represented_topics = {
            topic_id
            for record in (*finding_records, *gap_records)
            for topic_id in _required_string_tuple(record, "affected_topics")
        }
    except ValueError as exc:
        raise ValueError("must_answer_authority_invalid") from exc

    planned_topics = set().union(*bindings.values())
    known_represented = represented_topics & planned_topics
    covered: list[str] = []
    partial: list[str] = []
    uncovered: list[str] = []
    for question_id, topic_ids in sorted(bindings.items()):
        represented = topic_ids & known_represented
        if represented == topic_ids:
            covered.append(question_id)
        elif represented:
            partial.append(question_id)
        else:
            uncovered.append(question_id)
    missing_topics = planned_topics - known_represented
    result = evaluate_metric_result(
        outcome,
        metric_id,
        required_authorities=required,
        value=len(covered) / len(bindings),
        authoritative_denominator=len(bindings),
        evidence_basis=(
            f"bound-questions:{len(bindings)}",
            f"covered-questions:{len(covered)}",
            f"partial-questions:{len(partial)}",
            f"missing-topics:{len(missing_topics)}",
            f"unknown-synthesis-topics:{len(represented_topics - planned_topics)}",
        ),
    )
    return MustAnswerCoverageEvaluation(
        result=result,
        covered_question_ids=tuple(covered),
        partial_question_ids=tuple(partial),
        uncovered_question_ids=tuple(uncovered),
        missing_topic_ids=tuple(sorted(missing_topics)),
        unknown_synthesis_topic_ids=tuple(sorted(represented_topics - planned_topics)),
        unmapped_planned_topic_ids=tuple(sorted(missing_topics)),
    )


def _required_string_tuple(record: Mapping[str, Any], field_name: str) -> tuple[str, ...]:
    value = record.get(field_name)
    if (
        not isinstance(value, tuple)
        or len(set(value)) != len(value)
        or any(not isinstance(item, str) or not item for item in value)
    ):
        raise ValueError(f"metric_authority_{field_name}_invalid")
    return value


def compute_distinct_canonical_url_count(outcome: ValidatedEvaluationOutcome) -> MetricResult:
    metric_id = "distinct-canonical-url-count"
    source_refs = _accepted_source_refs(outcome, metric_id)
    if isinstance(source_refs, MetricResult):
        return source_refs
    urls = {_canonical_url(_required_string(source, "canonical_url")) for source in source_refs}
    return evaluate_metric_result(
        outcome,
        metric_id,
        required_authorities=("accepted_ledger_records",),
        value=len(urls),
        evidence_basis=(f"accepted-source-refs:{len(source_refs)}", f"distinct-canonical-urls:{len(urls)}"),
    )


def compute_distinct_normalized_host_count(outcome: ValidatedEvaluationOutcome) -> MetricResult:
    metric_id = "distinct-normalized-host-count"
    source_refs = _accepted_source_refs(outcome, metric_id)
    if isinstance(source_refs, MetricResult):
        return source_refs
    hosts = {urlsplit(_canonical_url(_required_string(source, "canonical_url"))).hostname for source in source_refs}
    return evaluate_metric_result(
        outcome,
        metric_id,
        required_authorities=("accepted_ledger_records",),
        value=len(hosts),
        evidence_basis=(f"accepted-source-refs:{len(source_refs)}", f"distinct-normalized-hosts:{len(hosts)}"),
    )


def compute_final_citation_completeness(outcome: ValidatedEvaluationOutcome) -> MetricResult:
    metric_id = "final-citation-completeness"
    required = ("final_citation_map",)
    if metric_id not in outcome.selected_metric_ids or outcome.final_citation_map is None:
        return evaluate_metric_result(outcome, metric_id, required_authorities=required, value=None)
    records = _projection_records(outcome.final_citation_map, "final-citation-map")
    if not records:
        return evaluate_metric_result(
            outcome, metric_id, required_authorities=required, value=None, authoritative_denominator=0
        )
    cited = sum(1 for record in records if _required_string_tuple(record, "citation_refs"))
    return evaluate_metric_result(
        outcome,
        metric_id,
        required_authorities=required,
        value=cited / len(records),
        authoritative_denominator=len(records),
        evidence_basis=(f"final-claims:{len(records)}", f"cited-final-claims:{cited}"),
    )


def compute_synthesis_finding_support_coverage(outcome: ValidatedEvaluationOutcome) -> MetricResult:
    metric_id = "synthesis-finding-support-coverage"
    required = ("accepted_ledger_records", "synthesis_findings")
    if metric_id not in outcome.selected_metric_ids or any(getattr(outcome, name) is None for name in required):
        return evaluate_metric_result(outcome, metric_id, required_authorities=required, value=None)
    accepted_refs = _accepted_submission_refs(outcome)
    findings = _projection_records(outcome.synthesis_findings, "synthesis-findings")
    if not findings:
        return evaluate_metric_result(
            outcome, metric_id, required_authorities=required, value=None, authoritative_denominator=0
        )
    supported = sum(1 for finding in findings if set(_required_string_tuple(finding, "backing_refs")) & accepted_refs)
    return evaluate_metric_result(
        outcome,
        metric_id,
        required_authorities=required,
        value=supported / len(findings),
        authoritative_denominator=len(findings),
        evidence_basis=(f"synthesis-findings:{len(findings)}", f"supported-synthesis-findings:{supported}"),
    )


def compute_structural_missing_backing_ref_count(outcome: ValidatedEvaluationOutcome) -> MetricResult:
    metric_id = "structural-missing-backing-ref-count"
    required = ("accepted_ledger_records", "synthesis_findings")
    if metric_id not in outcome.selected_metric_ids or any(getattr(outcome, name) is None for name in required):
        return evaluate_metric_result(outcome, metric_id, required_authorities=required, value=None)
    accepted_refs = _accepted_submission_refs(outcome)
    findings = _projection_records(outcome.synthesis_findings, "synthesis-findings")
    missing = 0
    for finding in findings:
        refs = _required_string_tuple(finding, "backing_refs")
        missing += 1 if not refs else sum(1 for ref in refs if ref not in accepted_refs)
    return evaluate_metric_result(
        outcome,
        metric_id,
        required_authorities=required,
        value=missing,
        evidence_basis=(f"synthesis-findings:{len(findings)}", f"missing-backing-refs:{missing}"),
    )


def compute_semantic_unsupported_major_claim_count(outcome: ValidatedEvaluationOutcome) -> MetricResult:
    metric_id = "unsupported-major-claim-count"
    required = ("labeled_expectations",)
    if metric_id not in outcome.selected_metric_ids or outcome.labeled_expectations is None:
        return evaluate_metric_result(outcome, metric_id, required_authorities=required, value=None)
    labels = _projection_records(outcome.labeled_expectations, "labeled-expectations")
    if not labels:
        return insufficient_authority(
            metric_id,
            value_kind=MetricValueKind.COUNT,
            evidence_basis=("labeled-expectations:validated-empty",),
        )
    major = {
        _required_string(label, "claim_id")
        for label in labels
        if label.get("major") is True
        and _required_string(label, "judgment") in {"supports", "unsupported", "contradicts"}
    }
    unsupported = {
        _required_string(label, "claim_id")
        for label in labels
        if label.get("major") is True and _required_string(label, "judgment") == "unsupported"
    }
    return evaluate_metric_result(
        outcome,
        metric_id,
        required_authorities=required,
        value=len(unsupported),
        evidence_basis=(f"labeled-major-claims:{len(major)}", f"semantic-unsupported-major-claims:{len(unsupported)}"),
    )


def compute_contradiction_recall(outcome: ValidatedEvaluationOutcome) -> MetricResult:
    metric_id = "contradiction-recall"
    required = ("labeled_expectations",)
    if metric_id not in outcome.selected_metric_ids or outcome.labeled_expectations is None:
        return evaluate_metric_result(outcome, metric_id, required_authorities=required, value=None)
    labels = _projection_records(outcome.labeled_expectations, "labeled-expectations")
    expected = {
        (_required_string(label, "claim_id"), _required_string(label, "submission_ref"))
        for label in labels
        if _required_string(label, "judgment") == "expected_contradiction"
    }
    observed = {
        (_required_string(label, "claim_id"), _required_string(label, "submission_ref"))
        for label in labels
        if _required_string(label, "judgment") == "contradicts"
    }
    if not expected:
        return evaluate_metric_result(
            outcome, metric_id, required_authorities=required, value=None, authoritative_denominator=0
        )
    found = len(expected & observed)
    return evaluate_metric_result(
        outcome,
        metric_id,
        required_authorities=required,
        value=found / len(expected),
        authoritative_denominator=len(expected),
        evidence_basis=(f"expected-contradictions:{len(expected)}", f"observed-contradictions:{found}"),
    )


def _accepted_submission_refs(outcome: ValidatedEvaluationOutcome) -> set[str]:
    records = _projection_records(outcome.accepted_ledger_records, "accepted-ledger-records")
    refs = [_required_string(record, "submission_ref") for record in records]
    if len(set(refs)) != len(refs):
        raise ValueError("accepted_ledger_submission_ref_duplicate")
    return set(refs)


def _accepted_source_refs(
    outcome: ValidatedEvaluationOutcome, metric_id: str
) -> tuple[dict[str, Any], ...] | MetricResult:
    required = ("accepted_ledger_records",)
    if metric_id not in outcome.selected_metric_ids or outcome.accepted_ledger_records is None:
        return evaluate_metric_result(outcome, metric_id, required_authorities=required, value=None)
    records = _projection_records(outcome.accepted_ledger_records, "accepted-ledger-records")
    sources: list[dict[str, Any]] = []
    for record in records:
        raw_sources = record.get("source_refs")
        if not isinstance(raw_sources, tuple):
            raise ValueError("accepted_source_refs_invalid")
        sources.extend(_record_from_projection(source, "accepted-source-ref") for source in raw_sources)
    return tuple(sources)


def _record_from_projection(value: FrozenProjection, authority: str) -> dict[str, Any]:
    if not isinstance(value, tuple) or any(
        not isinstance(item, tuple) or len(item) != 2 or not isinstance(item[0], str) for item in value
    ):
        raise ValueError(f"{authority}_record_invalid")
    return {key: item for key, item in value}


def _canonical_url(value: str) -> str:
    parsed = urlsplit(value)
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("accepted_source_url_invalid")
    scheme = parsed.scheme.lower()
    host = parsed.hostname.lower()
    port = parsed.port
    default_port = (scheme == "https" and port == 443) or (scheme == "http" and port == 80)
    netloc = host if port is None or default_port else f"{host}:{port}"
    path = parsed.path or "/"
    return urlunsplit((scheme, netloc, path, parsed.query, ""))


def assert_hard_invariants(outcome: dict[str, Any]) -> None:
    failures = tuple(outcome.get("hard_invariant_failures") or ())
    if failures:
        raise AssertionError(f"hard invariants failed: {', '.join(str(value) for value in failures)}")


def compute_metrics(state: dict[str, Any]) -> dict[str, Any]:
    """Legacy report shim; typed outcome reporting is introduced by task 5.5."""
    if not isinstance(state, dict):
        raise TypeError("legacy_metric_state_required")
    return {}


__all__ = [
    "METRIC_VALUE_KINDS",
    "MetricResult",
    "MetricStatus",
    "MetricValueKind",
    "MustAnswerCoverageEvaluation",
    "ValidatedEvaluationOutcome",
    "evaluate_metric_result",
    "insufficient_authority",
    "measured",
    "not_applicable",
    "compute_citation_binding_rate",
    "compute_contradiction_recall",
    "compute_distinct_canonical_url_count",
    "compute_distinct_normalized_host_count",
    "compute_final_citation_completeness",
    "compute_labeled_citation_precision",
    "compute_metrics",
    "compute_must_answer_coverage",
    "compute_semantic_unsupported_major_claim_count",
    "compute_structural_missing_backing_ref_count",
    "compute_synthesis_finding_support_coverage",
    "assert_hard_invariants",
]
