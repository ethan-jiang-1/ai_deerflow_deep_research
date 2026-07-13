"""Shared deterministic gate domain types.

@impl GAK-001
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from deerflow_deep_research.domain.failure_codes import FailureCode, get_classification


class PhaseVerdict(StrEnum):
    """Typed verdict produced by phase-gate evaluation.

    Distinct from ``lifecycle.GateVerdict`` (branch-level verdict: pass | repair).
    """

    PASS = "pass"
    REPAIR = "repair"
    BLOCKED = "blocked"
    NEEDS_HUMAN = "needs_human"


# ---------------------------------------------------------------------------
# Failure
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Failure:
    """One rule failure collected during gate evaluation."""

    code: FailureCode
    rule_name: str
    description: str = ""
    ref: str | None = None  # work/attempt id or sandbox path

    @property
    def classification(self) -> str:
        return get_classification(self.code)


# ---------------------------------------------------------------------------
# GateResult
# ---------------------------------------------------------------------------


def _build_inspect(failures: tuple[Failure, ...]) -> str:
    if not failures:
        return "no issues"
    codes = ", ".join(f.code.value for f in failures)
    summary = f"{len(failures)} failure(s): {codes}"
    return summary[:512]


def _build_advice(failures: tuple[Failure, ...], verdict: PhaseVerdict) -> str:
    if not failures:
        return "no action needed"
    if verdict is PhaseVerdict.BLOCKED:
        return "blocked — cannot repair"
    lines: list[str] = []
    for f in failures:
        lines.append(f"- [{f.code.value}] {f.description}" if f.description else f"- [{f.code.value}]")
    return "\n".join(lines)[:2048]


@dataclass(frozen=True)
class GateResult:
    """The output of one gate evaluation for a specific phase."""

    phase: str
    verdict: PhaseVerdict
    route: str = ""  # resolved topology edge label from route_map/route_resolver
    failures: tuple[Failure, ...] = ()
    inspect: str = ""
    advice: str = ""
    failed_refs: tuple[str, ...] = ()
    degraded: bool = False
    attempt: int = 1
    remaining_budget: int = 0
    new_generation: int | None = None
    fingerprint: tuple[tuple[str, str], ...] = ()
    consecutive: int = 1

    def __post_init__(self) -> None:
        if not self.inspect:
            object.__setattr__(self, "inspect", _build_inspect(self.failures))
        if not self.advice:
            object.__setattr__(self, "advice", _build_advice(self.failures, self.verdict))
        if len(self.inspect) > 512:
            object.__setattr__(self, "inspect", self.inspect[:512])
        if len(self.advice) > 2048:
            object.__setattr__(self, "advice", self.advice[:2048])

    def model_dump(self, mode: str = "json") -> dict[str, Any]:
        """JSON-serializable dict for ``latest_gate_feedback`` storage."""
        return {
            "phase": self.phase,
            "verdict": self.verdict.value,
            "route": self.route,
            "failures": [
                {
                    "code": f.code.value,
                    "classification": f.classification,
                    "rule_name": f.rule_name,
                    "description": f.description,
                    "ref": f.ref,
                }
                for f in self.failures
            ],
            "inspect": self.inspect,
            "advice": self.advice,
            "failed_refs": list(self.failed_refs),
            "degraded": self.degraded,
            "attempt": self.attempt,
            "remaining_budget": self.remaining_budget,
            "new_generation": self.new_generation,
            "fingerprint": [list(fp) for fp in self.fingerprint],
            "consecutive": self.consecutive,
        }


# ---------------------------------------------------------------------------
# GateRule
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class GateRule:
    """One rule registered in a ``GateDefinition``.

    The *failure_code* is the code this rule is registered to produce; the
    actual code on a returned ``Failure`` MAY differ when the rule
    discriminates among multiple outcomes (e.g. ``FixtureSequenceRule``).
    """

    name: str
    evaluate: Callable[[Any], Failure | None]  # (ResearchState) -> Failure | None
    failure_code: FailureCode


# ---------------------------------------------------------------------------
# GateDefinition
# ---------------------------------------------------------------------------

# Known topology route labels for construction-time validation.
_KNOWN_ROUTE_LABELS = frozenset(
    {
        "pass",
        "repair",
        "exhausted",
        "evidence_needed",
        "evidence_blocked",
        "repair_targeted",
        "repair_synthesis",
        "repair_hitl2",
        "needs_input",
        "profile_complete",
        "accepted",
        "cancel",
        "next",
        "proceed",
        "revise_view",
        "rerun",
        "stop",
    }
)


def _validate_route_map(
    route_map: dict[PhaseVerdict, str] | None,
    route_resolver: Callable[..., str] | None,
) -> None:
    if route_map is not None:
        for verdict, label in route_map.items():
            if not isinstance(verdict, PhaseVerdict):
                raise ValueError(f"route_map key must be PhaseVerdict: {verdict!r}")
            if label not in _KNOWN_ROUTE_LABELS:
                raise ValueError(f"unknown route label: {label!r}")
    if route_map is None and route_resolver is None:
        raise ValueError("GateDefinition requires route_map or route_resolver")


@dataclass(frozen=True)
class GateDefinition:
    """A named collection of rules + route resolution for one phase."""

    phase: str
    rules: tuple[GateRule, ...]
    default_budget: int = 3
    route_map: dict[PhaseVerdict, str] | None = None
    route_resolver: Callable[..., str] | None = None

    def __post_init__(self) -> None:
        if self.default_budget < 0 or self.default_budget > 10:
            raise ValueError(f"default_budget out of range [0, 10]: {self.default_budget}")
        if not self.rules:
            raise ValueError("GateDefinition requires at least one rule")
        _validate_route_map(self.route_map, self.route_resolver)

    def resolve_route(self, verdict: PhaseVerdict, failures: tuple[Failure, ...]) -> str:
        """Return the topology edge label for *verdict*."""
        if self.route_resolver is not None:
            return self.route_resolver(verdict, failures)
        if self.route_map is not None:
            return self.route_map[verdict]
        raise RuntimeError("no route_map or route_resolver")


__all__ = [
    "Failure",
    "GateDefinition",
    "GateResult",
    "GateRule",
    "PhaseVerdict",
]
