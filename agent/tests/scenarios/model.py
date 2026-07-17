"""Minimal typed scenario manifest and explicit runner contract.

@impl EVH-001
@impl EVH-007
"""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from enum import IntEnum, StrEnum
from typing import Any

SCENARIO_ID_RE = re.compile(r"^[a-z][a-z0-9-]{2,63}$")
REQ_ID_RE = re.compile(r"^[A-Z]{3}-\d{3}$")


class AuthenticityLevel(IntEnum):
    FAKE_GRAPH = 1
    REAL_NODE_FAKE_CAPABILITIES = 2
    SCRIPTED_REAL_WORKFLOW = 3
    LIVE_REAL_DEPENDENCIES = 4
    FULL_REAL_PIPELINE = 5


class ExecutionLane(StrEnum):
    DETERMINISTIC = "deterministic"
    LIVE = "live"
    RELEASE = "release"


@dataclass(frozen=True)
class ScenarioOutcome:
    route: str | None = None
    terminal: str | None = None
    artifacts: tuple[str, ...] = ()
    citations: tuple[str, ...] = ()
    values: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Scenario:
    scenario_id: str
    risk_family: str
    requirement_ids: tuple[str, ...]
    regression_ids: tuple[str, ...]
    entrypoint: str
    authenticity: AuthenticityLevel
    preconditions: dict[str, Any]
    scripted_inputs: tuple[Any, ...]
    live_requirements: tuple[str, ...]
    expected: ScenarioOutcome
    hard_invariants: tuple[str, ...]
    metrics: tuple[str, ...]
    permitted_degradation: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not SCENARIO_ID_RE.fullmatch(self.scenario_id):
            raise ValueError("scenario_id_invalid")
        if not self.risk_family or not self.entrypoint:
            raise ValueError("scenario_identity_incomplete")
        if not self.requirement_ids or any(not REQ_ID_RE.fullmatch(value) for value in self.requirement_ids):
            raise ValueError("scenario_requirement_ids_invalid")
        if not self.hard_invariants:
            raise ValueError("scenario_invariants_required")
        if self.authenticity >= AuthenticityLevel.LIVE_REAL_DEPENDENCIES and not self.live_requirements:
            raise ValueError("live_requirements_required")


class ScenarioAssertionError(AssertionError):
    pass


Executor = Callable[[Scenario], Awaitable[ScenarioOutcome]]


class ScenarioRunner:
    def __init__(self, lane: ExecutionLane, authenticity: AuthenticityLevel, executor: Executor) -> None:
        self.lane = lane
        self.authenticity = authenticity
        self._executor = executor

    async def run(self, scenario: Scenario) -> ScenarioOutcome:
        prefix = f"scenario={scenario.scenario_id} lane={self.lane.value} authenticity={self.authenticity.name.lower()}"
        if self.authenticity < scenario.authenticity:
            raise ScenarioAssertionError(f"{prefix}: authenticity claim is insufficient")
        try:
            outcome = await self._executor(scenario)
        except Exception as exc:
            raise ScenarioAssertionError(f"{prefix}: executor failed: {type(exc).__name__}") from exc
        mismatches: list[str] = []
        if scenario.expected.route is not None and outcome.route != scenario.expected.route:
            mismatches.append(f"route expected={scenario.expected.route} actual={outcome.route}")
        if scenario.expected.terminal is not None and outcome.terminal != scenario.expected.terminal:
            mismatches.append(f"terminal expected={scenario.expected.terminal} actual={outcome.terminal}")
        missing_artifacts = set(scenario.expected.artifacts) - set(outcome.artifacts)
        if missing_artifacts:
            mismatches.append(f"missing artifacts={sorted(missing_artifacts)}")
        if mismatches:
            raise ScenarioAssertionError(f"{prefix}: invariant failed: {'; '.join(mismatches)}")
        return outcome


__all__ = [
    "AuthenticityLevel",
    "ExecutionLane",
    "Scenario",
    "ScenarioAssertionError",
    "ScenarioOutcome",
    "ScenarioRunner",
]
