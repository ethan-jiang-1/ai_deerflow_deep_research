"""Explicit live-evaluation preflight and reporting surfaces.

@impl EVH-002
@impl EVH-005
@impl EVH-007
@impl EVH-009
"""

from __future__ import annotations

import json
import re
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any

from tests.eval.metrics import (
    MetricResult,
    MetricStatus,
    MetricValueKind,
    ValidatedEvaluationOutcome,
    compute_citation_binding_rate,
    compute_contradiction_recall,
    compute_distinct_canonical_url_count,
    compute_distinct_normalized_host_count,
    compute_final_citation_completeness,
    compute_labeled_citation_precision,
    compute_must_answer_coverage,
    compute_semantic_unsupported_major_claim_count,
    compute_structural_missing_backing_ref_count,
    compute_synthesis_finding_support_coverage,
    evaluate_metric_result,
)

REPORT_SCHEMA_VERSION = 1
METRICS_SCHEMA = "evidence-v1"
MAX_LIVE_DIAGNOSTIC_CHARS = 4096
MAX_LIVE_REPORT_BYTES = 128 * 1024
MAX_LIVE_ARCHIVE_BYTES = 512 * 1024
MAX_LIVE_ARCHIVE_REPORTS = 64
_SENSITIVE_DIAGNOSTIC_RE = re.compile(
    r"(?i)(?:https?://|(?:token|api[_-]?key|secret|authorization)=|/(?:Users|home|private|tmp)/)"
)


class ReportClassification(StrEnum):
    EVIDENCE_V1 = "evidence-v1"
    LEGACY = "legacy"


@dataclass(frozen=True)
class LiveOutcome:
    route: str | None = None
    terminal: str | None = None
    artifacts: tuple[str, ...] = ()
    citations: tuple[str, ...] = ()
    values: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class LiveScenario:
    scenario_id: str
    requirement_ids: tuple[str, ...]
    entrypoint: str
    preconditions: dict[str, Any]
    live_requirements: tuple[str, ...]
    expected: LiveOutcome
    hard_invariants: tuple[str, ...]
    metrics: tuple[str, ...]


class ScenarioAssertionError(AssertionError):
    pass


MODEL_CREDENTIALS = {
    "ANTHROPIC_API_KEY": "anthropic",
    "DEEPSEEK_API_KEY": "deepseek",
    "OPENAI_API_KEY": "openai",
}


class LivePreflightError(RuntimeError):
    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code


@dataclass(frozen=True)
class LiveEnvironment:
    model_provider: str
    web_provider: str | None = None


@dataclass(frozen=True)
class LiveAttempt:
    outcome: LiveOutcome | None
    error_code: str | None
    model_id: str
    tool_ids: tuple[str, ...]
    input_tokens: int | None
    output_tokens: int | None
    cost_usd: float | None
    tool_calls: int
    wall_time_seconds: float
    diagnostics: str
    workflow_attempts: int = 1
    workflow_retries: int = 0


@dataclass(frozen=True)
class LiveAttemptReport:
    attempt: int
    succeeded: bool
    error_code: str | None
    diagnostics: str


@dataclass(frozen=True)
class LiveScenarioReport:
    report_schema_version: int
    metrics_schema: str
    scenario_id: str
    attempt_count: int
    retry_count: int
    workflow_attempt_count: int
    workflow_retry_count: int
    hard_invariants: dict[str, bool]
    quality_metrics: dict[str, object]
    model_ids: tuple[str, ...]
    tool_ids: tuple[str, ...]
    input_tokens: int | None
    output_tokens: int | None
    cost_usd: float | None
    tool_calls: int
    wall_time_seconds: float
    attempts: tuple[LiveAttemptReport, ...]
    diagnostics: dict[str, object]

    def __post_init__(self) -> None:
        if self.report_schema_version != REPORT_SCHEMA_VERSION or self.metrics_schema != METRICS_SCHEMA:
            raise ValueError("live_report_schema_invalid")
        if not isinstance(self.quality_metrics, dict):
            raise ValueError("live_report_metrics_invalid")
        expected_fields = {
            "metric_id",
            "status",
            "value_kind",
            "value",
            "evidence_basis",
            "authoritative_denominator",
        }
        for metric_id, metric in self.quality_metrics.items():
            if not isinstance(metric_id, str) or not isinstance(metric, dict) or set(metric) != expected_fields:
                raise ValueError("live_report_metrics_invalid")
            if metric.get("metric_id") != metric_id:
                raise ValueError("live_report_metric_identity_invalid")
            basis = metric.get("evidence_basis")
            try:
                MetricResult(
                    metric_id=metric_id,
                    status=MetricStatus(metric.get("status")),
                    value_kind=MetricValueKind(metric.get("value_kind")),
                    value=metric.get("value"),
                    evidence_basis=tuple(basis) if isinstance(basis, list) else (),
                    authoritative_denominator=metric.get("authoritative_denominator"),
                )
            except (TypeError, ValueError) as exc:
                raise ValueError("live_report_metric_result_invalid") from exc
        self._validate_diagnostics()

    def _validate_diagnostics(self) -> None:
        expected_sections = {"identity", "invariants", "metrics", "attempts", "resources"}
        if not isinstance(self.diagnostics, dict) or set(self.diagnostics) != expected_sections:
            raise ValueError("live_report_diagnostics_invalid")
        schemas = {
            "identity": {
                "thread_id_present": bool,
                "run_id_present": bool,
                "research_id_present": bool,
                "pairwise_distinct": bool,
            },
            "invariants": {"declared": int, "passed": int},
            "metrics": {"selected": int, "measured": int, "unavailable": int},
            "attempts": {"outer": int, "retries": int, "workflow": int, "workflow_retries": int},
            "resources": {
                "models": int,
                "tools": int,
                "tokens_available": bool,
                "cost_available": bool,
            },
        }
        for section, fields in schemas.items():
            value = self.diagnostics.get(section)
            if not isinstance(value, dict) or set(value) != set(fields):
                raise ValueError("live_report_diagnostics_invalid")
            for field_name, field_type in fields.items():
                field_value = value[field_name]
                if field_type is bool:
                    valid = isinstance(field_value, bool)
                else:
                    valid = isinstance(field_value, int) and not isinstance(field_value, bool) and field_value >= 0
                if not valid:
                    raise ValueError("live_report_diagnostics_invalid")
        identity = self.diagnostics["identity"]
        invariants = self.diagnostics["invariants"]
        metrics = self.diagnostics["metrics"]
        attempts_summary = self.diagnostics["attempts"]
        resources = self.diagnostics["resources"]
        identity_presence = (
            identity["thread_id_present"],
            identity["run_id_present"],
            identity["research_id_present"],
        )
        expected = (
            identity["pairwise_distinct"] is False or all(identity_presence),
            invariants == {"declared": len(self.hard_invariants), "passed": sum(self.hard_invariants.values())},
            metrics["selected"] == len(self.quality_metrics),
            metrics["measured"] + metrics["unavailable"] == metrics["selected"],
            attempts_summary
            == {
                "outer": self.attempt_count,
                "retries": self.retry_count,
                "workflow": self.workflow_attempt_count,
                "workflow_retries": self.workflow_retry_count,
            },
            resources["models"] == len(self.model_ids),
            resources["tools"] == len(self.tool_ids),
            resources["tokens_available"] is (self.input_tokens is not None or self.output_tokens is not None),
            resources["cost_available"] is (self.cost_usd is not None),
        )
        if not all(expected):
            raise ValueError("live_report_diagnostics_invalid")
        for attempt in self.attempts:
            if not isinstance(attempt, LiveAttemptReport):
                raise ValueError("live_report_diagnostics_invalid")
            if (
                not isinstance(attempt.diagnostics, str)
                or len(attempt.diagnostics) > MAX_LIVE_DIAGNOSTIC_CHARS
                or _SENSITIVE_DIAGNOSTIC_RE.search(attempt.diagnostics)
            ):
                raise ValueError("live_report_diagnostics_invalid")

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class LiveScenarioFailure(ScenarioAssertionError):
    def __init__(self, message: str, report: LiveScenarioReport) -> None:
        super().__init__(message)
        self.report = report


LiveExecutor = Callable[[LiveScenario], Awaitable[LiveAttempt]]


def _unique(values: list[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(values))


def _redact_diagnostics(value: str) -> str:
    redacted = re.sub(r"(?i)(?:token|api[_-]?key|secret|authorization)=\S+", "credential=<redacted>", value)
    redacted = re.sub(r"/(?:Users|home|private|tmp)/\S+", "<redacted-path>", redacted)
    redacted = re.sub(r"https?://\S+", "<redacted-url>", redacted, flags=re.IGNORECASE)
    return redacted[:MAX_LIVE_DIAGNOSTIC_CHARS]


def classify_live_report(payload: Mapping[str, object]) -> ReportClassification:
    if not isinstance(payload, Mapping):
        raise TypeError("live_report_mapping_required")
    has_version = "report_schema_version" in payload
    has_metrics_schema = "metrics_schema" in payload
    if not has_version and not has_metrics_schema:
        return ReportClassification.LEGACY
    if payload.get("report_schema_version") != REPORT_SCHEMA_VERSION or payload.get("metrics_schema") != METRICS_SCHEMA:
        raise ValueError("live_report_schema_invalid")
    return ReportClassification.EVIDENCE_V1


def _validate_outcome(scenario: LiveScenario, outcome: LiveOutcome) -> None:
    failures: list[str] = []
    if scenario.expected.route is not None and outcome.route != scenario.expected.route:
        failures.append(f"route expected={scenario.expected.route} actual={outcome.route}")
    if scenario.expected.terminal is not None and outcome.terminal != scenario.expected.terminal:
        failures.append(f"terminal expected={scenario.expected.terminal} actual={outcome.terminal}")
    missing_artifacts = set(scenario.expected.artifacts) - set(outcome.artifacts)
    if missing_artifacts:
        failures.append(f"missing artifacts={sorted(missing_artifacts)}")
    if failures:
        raise ScenarioAssertionError(
            f"scenario={scenario.scenario_id} lane=live authenticity=live_real_dependencies: "
            f"invariant failed: {'; '.join(failures)}"
        )


class LiveScenarioRunner:
    def __init__(self, *, executor: LiveExecutor, max_attempts: int) -> None:
        if not 1 <= max_attempts <= 3:
            raise ValueError("live_attempt_bound_invalid")
        self._executor = executor
        self._max_attempts = max_attempts

    async def run(self, scenario: LiveScenario) -> LiveScenarioReport:
        attempts: list[LiveAttempt] = []
        outcome: LiveOutcome | None = None
        for _ in range(self._max_attempts):
            attempt = await self._executor(scenario)
            attempts.append(attempt)
            if attempt.outcome is not None:
                outcome = attempt.outcome
                break
        if outcome is None:
            codes = ",".join(attempt.error_code or "unknown" for attempt in attempts)
            report = self._report(
                scenario,
                attempts,
                outcome=LiveOutcome(values={}),
                hard_invariants={name: False for name in scenario.hard_invariants},
            )
            raise LiveScenarioFailure(
                f"scenario={scenario.scenario_id} lane=live authenticity=live_real_dependencies: "
                f"attempts exhausted: {codes}",
                report,
            )
        _validate_outcome(scenario, outcome)

        return self._report(
            scenario,
            attempts,
            outcome=outcome,
            hard_invariants={name: True for name in scenario.hard_invariants},
        )

    @staticmethod
    def _report(
        scenario: LiveScenario,
        attempts: list[LiveAttempt],
        *,
        outcome: LiveOutcome,
        hard_invariants: dict[str, bool],
    ) -> LiveScenarioReport:
        input_values = [attempt.input_tokens for attempt in attempts if attempt.input_tokens is not None]
        output_values = [attempt.output_tokens for attempt in attempts if attempt.output_tokens is not None]
        cost_values = [attempt.cost_usd for attempt in attempts if attempt.cost_usd is not None]
        metrics = _compute_typed_metrics(scenario, outcome)
        identity = outcome.values.get("identity")
        identity_values = (
            tuple(identity.get(name) for name in ("thread_id", "run_id", "research_id"))
            if isinstance(identity, Mapping)
            else (None, None, None)
        )
        identity_present = tuple(isinstance(value, str) and bool(value) for value in identity_values)
        measured_metrics = sum(metric.get("status") == MetricStatus.MEASURED.value for metric in metrics.values())
        return LiveScenarioReport(
            report_schema_version=REPORT_SCHEMA_VERSION,
            metrics_schema=METRICS_SCHEMA,
            scenario_id=scenario.scenario_id,
            attempt_count=len(attempts),
            retry_count=len(attempts) - 1,
            workflow_attempt_count=sum(attempt.workflow_attempts for attempt in attempts),
            workflow_retry_count=sum(attempt.workflow_retries for attempt in attempts),
            hard_invariants=hard_invariants,
            quality_metrics=metrics,
            model_ids=_unique([attempt.model_id for attempt in attempts]),
            tool_ids=_unique([tool_id for attempt in attempts for tool_id in attempt.tool_ids]),
            input_tokens=sum(input_values) if input_values else None,
            output_tokens=sum(output_values) if output_values else None,
            cost_usd=sum(cost_values) if cost_values else None,
            tool_calls=sum(attempt.tool_calls for attempt in attempts),
            wall_time_seconds=sum(attempt.wall_time_seconds for attempt in attempts),
            attempts=tuple(
                LiveAttemptReport(
                    attempt=index,
                    succeeded=attempt.outcome is not None,
                    error_code=attempt.error_code,
                    diagnostics=_redact_diagnostics(attempt.diagnostics),
                )
                for index, attempt in enumerate(attempts, start=1)
            ),
            diagnostics={
                "identity": {
                    "thread_id_present": identity_present[0],
                    "run_id_present": identity_present[1],
                    "research_id_present": identity_present[2],
                    "pairwise_distinct": all(identity_present) and len(set(identity_values)) == 3,
                },
                "invariants": {
                    "declared": len(hard_invariants),
                    "passed": sum(hard_invariants.values()),
                },
                "metrics": {
                    "selected": len(metrics),
                    "measured": measured_metrics,
                    "unavailable": len(metrics) - measured_metrics,
                },
                "attempts": {
                    "outer": len(attempts),
                    "retries": len(attempts) - 1,
                    "workflow": sum(attempt.workflow_attempts for attempt in attempts),
                    "workflow_retries": sum(attempt.workflow_retries for attempt in attempts),
                },
                "resources": {
                    "models": len(_unique([attempt.model_id for attempt in attempts])),
                    "tools": len(_unique([tool_id for attempt in attempts for tool_id in attempt.tool_ids])),
                    "tokens_available": bool(input_values or output_values),
                    "cost_available": bool(cost_values),
                },
            },
        )


def _compute_typed_metrics(scenario: LiveScenario, outcome: LiveOutcome) -> dict[str, object]:
    values = outcome.values
    validated = ValidatedEvaluationOutcome(
        selected_metric_ids=scenario.metrics,
        accepted_ledger_records=_authority_projection(values, "accepted_ledger_records"),
        topic_question_bindings=_authority_projection(values, "topic_question_bindings"),
        synthesis_findings=_authority_projection(values, "synthesis_findings"),
        synthesis_gaps=_authority_projection(values, "synthesis_gaps"),
        final_citation_map=_authority_projection(values, "final_citation_map"),
        labeled_expectations=_authority_projection(values, "labeled_expectations"),
    )
    evaluators = {
        "citation-binding-rate": lambda: compute_citation_binding_rate(validated),
        "labeled-citation-precision": lambda: compute_labeled_citation_precision(validated),
        "must-answer-coverage": lambda: compute_must_answer_coverage(validated).result,
        "distinct-canonical-url-count": lambda: compute_distinct_canonical_url_count(validated),
        "distinct-normalized-host-count": lambda: compute_distinct_normalized_host_count(validated),
        "final-citation-completeness": lambda: compute_final_citation_completeness(validated),
        "synthesis-finding-support-coverage": lambda: compute_synthesis_finding_support_coverage(validated),
        "structural-missing-backing-ref-count": lambda: compute_structural_missing_backing_ref_count(validated),
        "unsupported-major-claim-count": lambda: compute_semantic_unsupported_major_claim_count(validated),
        "contradiction-recall": lambda: compute_contradiction_recall(validated),
        "accepted-authority-count": lambda: evaluate_metric_result(
            validated,
            "accepted-authority-count",
            required_authorities=("accepted_ledger_records",),
            value=(len(validated.accepted_ledger_records) if validated.accepted_ledger_records is not None else None),
            evidence_basis=(f"accepted-ledger-records:{len(validated.accepted_ledger_records or ())}",),
        ),
    }
    results: dict[str, object] = {}
    for metric_id in scenario.metrics:
        evaluator = evaluators.get(metric_id)
        if evaluator is None:
            raise ValueError(f"live_metric_unsupported:{metric_id}")
        results[metric_id] = _metric_result_dict(evaluator())
    return results


def _authority_projection(values: Mapping[str, Any], field_name: str) -> tuple[object, ...] | None:
    value = values.get(field_name)
    if value is None:
        return None
    if not isinstance(value, tuple):
        raise ValueError(f"live_outcome_{field_name}_invalid")
    return value


def _metric_result_dict(result: MetricResult) -> dict[str, object]:
    return {
        "metric_id": result.metric_id,
        "status": result.status.value,
        "value_kind": result.value_kind.value,
        "value": result.value,
        "evidence_basis": list(result.evidence_basis),
        "authoritative_denominator": result.authoritative_denominator,
    }


def write_live_report(report: LiveScenarioReport, directory: Path) -> Path:
    if not isinstance(report, LiveScenarioReport):
        raise TypeError("live_scenario_report_required")
    if not isinstance(directory, Path):
        raise TypeError("live_report_directory_required")
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{report.scenario_id}.json"
    path.write_text(json.dumps(report.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def scan_live_report_archive(directory: Path) -> tuple[str, ...]:
    if not isinstance(directory, Path):
        raise TypeError("live_report_archive_path_required")
    paths = tuple(sorted(directory.glob("*.json"))) if directory.is_dir() else ()
    if not paths:
        raise ValueError("live_report_archive_empty")
    if len(paths) > MAX_LIVE_ARCHIVE_REPORTS:
        raise ValueError("live_report_archive_oversize")
    total_bytes = 0
    scenario_ids: list[str] = []
    for path in paths:
        raw = path.read_bytes()
        total_bytes += len(raw)
        if len(raw) > MAX_LIVE_REPORT_BYTES or total_bytes > MAX_LIVE_ARCHIVE_BYTES:
            raise ValueError("live_report_archive_oversize")
        text = raw.decode("utf-8", "strict")
        if _SENSITIVE_DIAGNOSTIC_RE.search(text):
            raise ValueError("live_report_archive_sensitive")
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError("live_report_archive_json_invalid") from exc
        if classify_live_report(payload) is not ReportClassification.EVIDENCE_V1:
            raise ValueError("live_report_archive_schema_invalid")
        if not isinstance(payload, dict):
            raise ValueError("live_report_archive_schema_invalid")
        attempts = payload.get("attempts")
        if not isinstance(attempts, list):
            raise ValueError("live_report_archive_schema_invalid")
        try:
            report = LiveScenarioReport(
                **{
                    **payload,
                    "model_ids": tuple(payload.get("model_ids", ())),
                    "tool_ids": tuple(payload.get("tool_ids", ())),
                    "attempts": tuple(LiveAttemptReport(**attempt) for attempt in attempts),
                }
            )
        except (TypeError, ValueError) as exc:
            raise ValueError("live_report_archive_schema_invalid") from exc
        if report.scenario_id in scenario_ids:
            raise ValueError("live_report_archive_duplicate_case")
        scenario_ids.append(report.scenario_id)
    return tuple(sorted(scenario_ids))


def preflight_live_environment(*, environ: Mapping[str, str], require_web: bool) -> LiveEnvironment:
    for name, provider in MODEL_CREDENTIALS.items():
        if environ.get(name, "").strip():
            if require_web and not environ.get("TAVILY_API_KEY", "").strip():
                raise LivePreflightError(
                    "live_web_credentials_missing",
                    "set TAVILY_API_KEY before selecting a live web scenario",
                )
            return LiveEnvironment(
                model_provider=provider,
                web_provider="tavily" if require_web else None,
            )
    else:
        raise LivePreflightError(
            "live_model_credentials_missing",
            f"set one of {', '.join(MODEL_CREDENTIALS)} before selecting the live lane",
        )


__all__ = [
    "LiveAttempt",
    "LiveAttemptReport",
    "LiveEnvironment",
    "LiveOutcome",
    "LivePreflightError",
    "LiveScenario",
    "LiveScenarioFailure",
    "LiveScenarioReport",
    "LiveScenarioRunner",
    "ReportClassification",
    "classify_live_report",
    "preflight_live_environment",
    "scan_live_report_archive",
    "write_live_report",
]
