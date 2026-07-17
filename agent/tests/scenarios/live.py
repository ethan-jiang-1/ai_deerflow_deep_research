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
from dataclasses import asdict, dataclass
from pathlib import Path

from tests.eval.metrics import compute_metrics
from tests.scenarios.model import Scenario, ScenarioAssertionError, ScenarioOutcome

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
    outcome: ScenarioOutcome | None
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

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class LiveScenarioFailure(ScenarioAssertionError):
    def __init__(self, message: str, report: LiveScenarioReport) -> None:
        super().__init__(message)
        self.report = report


LiveExecutor = Callable[[Scenario], Awaitable[LiveAttempt]]


def _unique(values: list[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(values))


def _redact_diagnostics(value: str) -> str:
    redacted = re.sub(r"(?i)(?:token|api[_-]?key|secret|authorization)=\S+", "credential=<redacted>", value)
    return re.sub(r"/(?:Users|home|private|tmp)/\S+", "<redacted-path>", redacted)


def _validate_outcome(scenario: Scenario, outcome: ScenarioOutcome) -> None:
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

    async def run(self, scenario: Scenario) -> LiveScenarioReport:
        attempts: list[LiveAttempt] = []
        outcome: ScenarioOutcome | None = None
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
                outcome=ScenarioOutcome(values={}),
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
        scenario: Scenario,
        attempts: list[LiveAttempt],
        *,
        outcome: ScenarioOutcome,
        hard_invariants: dict[str, bool],
    ) -> LiveScenarioReport:
        input_values = [attempt.input_tokens for attempt in attempts if attempt.input_tokens is not None]
        output_values = [attempt.output_tokens for attempt in attempts if attempt.output_tokens is not None]
        cost_values = [attempt.cost_usd for attempt in attempts if attempt.cost_usd is not None]
        return LiveScenarioReport(
            scenario_id=scenario.scenario_id,
            attempt_count=len(attempts),
            retry_count=len(attempts) - 1,
            workflow_attempt_count=sum(attempt.workflow_attempts for attempt in attempts),
            workflow_retry_count=sum(attempt.workflow_retries for attempt in attempts),
            hard_invariants=hard_invariants,
            quality_metrics=compute_metrics(outcome.values),
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
        )


def write_live_report(report: LiveScenarioReport, directory: Path) -> Path:
    if not isinstance(report, LiveScenarioReport):
        raise TypeError("live_scenario_report_required")
    if not isinstance(directory, Path):
        raise TypeError("live_report_directory_required")
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{report.scenario_id}.json"
    path.write_text(json.dumps(report.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


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
    "LiveEnvironment",
    "LivePreflightError",
    "LiveScenarioFailure",
    "LiveScenarioReport",
    "LiveScenarioRunner",
    "preflight_live_environment",
    "write_live_report",
]
