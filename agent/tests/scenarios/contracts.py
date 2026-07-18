"""Lane-neutral scenario families and lane-specific case declarations.

@impl EVH-001
@impl EVH-007
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum

from tests.assets.evidence import AssetClass, AuthenticityLevel, StableSeam
from tests.scenarios.inputs import LiveRequirements, ScenarioInputs

SCENARIO_ID_RE = re.compile(r"^[a-z][a-z0-9-]{2,63}$")
REQUIREMENT_ID_RE = re.compile(r"^[A-Z]{3}-\d{3}$")
REGRESSION_ID_RE = re.compile(r"^(?:LIVE|RELEASE)-\d{8}-\d{2}$")


class ScenarioLane(StrEnum):
    DETERMINISTIC = "deterministic"
    LIVE = "live"
    RELEASE = "release"


@dataclass(frozen=True)
class ScenarioBounds:
    max_attempts: int
    max_model_calls: int
    max_tool_calls: int
    max_wall_seconds: int

    def __post_init__(self) -> None:
        if (
            not isinstance(self.max_attempts, int)
            or not 1 <= self.max_attempts <= 8
            or not isinstance(self.max_model_calls, int)
            or not 0 <= self.max_model_calls <= 64
            or not isinstance(self.max_tool_calls, int)
            or not 0 <= self.max_tool_calls <= 128
            or not isinstance(self.max_wall_seconds, int)
            or not 1 <= self.max_wall_seconds <= 900
        ):
            raise ValueError("scenario_bounds_invalid")


@dataclass(frozen=True)
class ScenarioExpectations:
    route: str | None = None
    terminal: str | None = None
    artifacts: tuple[str, ...] = ()
    support: tuple[str, ...] = ()
    citations: tuple[str, ...] = ()
    permitted_degradation: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for field_name in ("artifacts", "support", "citations", "permitted_degradation"):
            values = getattr(self, field_name)
            if not isinstance(values, tuple) or any(not _valid_label(value) for value in values):
                raise ValueError(f"case_expectation_{field_name}_invalid")
            if len(set(values)) != len(values):
                raise ValueError(f"case_expectation_{field_name}_duplicate")
        if self.route is not None and not _valid_label(self.route):
            raise ValueError("case_expectation_route_invalid")
        if self.terminal is not None and not _valid_label(self.terminal):
            raise ValueError("case_expectation_terminal_invalid")


@dataclass(frozen=True)
class ScenarioFamily:
    family_id: str
    risk_intent: str
    requirement_ids: tuple[str, ...]
    regression_ids: tuple[str, ...]
    permitted_degradation: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.family_id, str) or not SCENARIO_ID_RE.fullmatch(self.family_id):
            raise ValueError("family_id_invalid")
        if not isinstance(self.risk_intent, str) or not self.risk_intent.strip() or len(self.risk_intent) > 512:
            raise ValueError("family_risk_intent_required")
        if not _valid_ids(self.requirement_ids, REQUIREMENT_ID_RE, required=True):
            raise ValueError("family_requirement_ids_invalid")
        if not _valid_ids(self.regression_ids, REGRESSION_ID_RE, required=False):
            raise ValueError("family_regression_ids_invalid")
        if not isinstance(self.permitted_degradation, tuple) or any(
            not _valid_label(value) for value in self.permitted_degradation
        ):
            raise ValueError("family_permitted_degradation_invalid")
        if len(set(self.permitted_degradation)) != len(self.permitted_degradation):
            raise ValueError("family_permitted_degradation_duplicate")


@dataclass(frozen=True)
class ScenarioCase:
    case_id: str
    family_id: str
    lane: ScenarioLane
    entrypoint: str
    asset_class: AssetClass
    seam: StableSeam
    authenticity: AuthenticityLevel | None
    preconditions: tuple[str, ...]
    inputs: ScenarioInputs | LiveRequirements
    bounds: ScenarioBounds
    expectations: ScenarioExpectations
    hard_invariants: tuple[str, ...]
    applicable_metrics: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.case_id, str) or not SCENARIO_ID_RE.fullmatch(self.case_id):
            raise ValueError("case_id_invalid")
        if not isinstance(self.family_id, str) or not SCENARIO_ID_RE.fullmatch(self.family_id):
            raise ValueError("case_family_id_invalid")
        if not isinstance(self.lane, ScenarioLane):
            raise ValueError("case_lane_invalid")
        if not _valid_label(self.entrypoint):
            raise ValueError("case_entrypoint_invalid")
        if not isinstance(self.asset_class, AssetClass):
            raise ValueError("case_asset_class_invalid")
        if not isinstance(self.seam, StableSeam):
            raise ValueError("case_seam_invalid")
        if self.authenticity is not None and not isinstance(self.authenticity, AuthenticityLevel):
            raise ValueError("case_authenticity_invalid")
        if (
            not isinstance(self.preconditions, tuple)
            or not self.preconditions
            or any(not _valid_label(value) for value in self.preconditions)
        ):
            raise ValueError("case_preconditions_required")
        if self.lane is ScenarioLane.DETERMINISTIC and not isinstance(self.inputs, ScenarioInputs):
            raise ValueError("case_deterministic_inputs_required")
        if self.lane in {ScenarioLane.LIVE, ScenarioLane.RELEASE} and not isinstance(self.inputs, LiveRequirements):
            raise ValueError("case_live_requirements_required")
        if not isinstance(self.bounds, ScenarioBounds):
            raise ValueError("case_bounds_invalid")
        if not isinstance(self.expectations, ScenarioExpectations):
            raise ValueError("case_expectations_invalid")
        if (
            not isinstance(self.hard_invariants, tuple)
            or not self.hard_invariants
            or any(not _valid_label(value) for value in self.hard_invariants)
        ):
            raise ValueError("case_hard_invariants_required")
        if (
            not isinstance(self.applicable_metrics, tuple)
            or not self.applicable_metrics
            or any(not _valid_label(value) for value in self.applicable_metrics)
        ):
            raise ValueError("case_metrics_required")


class ScenarioContractError(ValueError):
    pass


def validate_scenario_registry(
    families: Iterable[ScenarioFamily],
    cases: Iterable[ScenarioCase],
) -> None:
    families = tuple(families)
    cases = tuple(cases)
    errors: list[str] = []
    by_family: dict[str, ScenarioFamily] = {}
    for family in families:
        if family.family_id in by_family:
            errors.append(f"{family.family_id}: duplicate family")
        by_family[family.family_id] = family

    case_ids: set[str] = set()
    cases_by_family: dict[str, list[ScenarioCase]] = {family_id: [] for family_id in by_family}
    for case in cases:
        if case.case_id in case_ids:
            errors.append(f"{case.case_id}: duplicate case")
        case_ids.add(case.case_id)
        family = by_family.get(case.family_id)
        if family is None:
            errors.append(f"{case.case_id}: unknown family {case.family_id}")
            continue
        cases_by_family[case.family_id].append(case)
        unsupported = set(case.expectations.permitted_degradation) - set(family.permitted_degradation)
        if unsupported:
            errors.append(f"{case.case_id}: degradation outside family policy {sorted(unsupported)}")

    for family_id, bound_cases in cases_by_family.items():
        if not bound_cases:
            errors.append(f"{family_id}: no executable cases")

    if errors:
        raise ScenarioContractError("\n".join(errors))


def _valid_ids(values: object, pattern: re.Pattern[str], *, required: bool) -> bool:
    return (
        isinstance(values, tuple)
        and (bool(values) or not required)
        and len(set(values)) == len(values)
        and all(isinstance(value, str) and pattern.fullmatch(value) for value in values)
    )


def _valid_label(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip()) and len(value) <= 128


__all__ = [
    "ScenarioBounds",
    "ScenarioCase",
    "ScenarioContractError",
    "ScenarioExpectations",
    "ScenarioFamily",
    "ScenarioLane",
    "validate_scenario_registry",
]
