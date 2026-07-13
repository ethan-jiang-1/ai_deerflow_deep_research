"""Fixture gate rules that preserve change-01 fake graph paths.

@impl GAK-005
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from deerflow_deep_research.domain.failure_codes import FailureCode
from deerflow_deep_research.domain.gate import (
    Failure,
    GateDefinition,
    GateRule,
    PhaseVerdict,
)
from deerflow_deep_research.domain.lifecycle import completed_visits

# ---------------------------------------------------------------------------
# FixtureSequenceRule
# ---------------------------------------------------------------------------


class FixtureSequenceRule:
    """A ``GateRule`` that reads change-01 ``fixture_plan`` sequences.

    Constructed with *pass_values* (strings that mean "pass") and a
    *failure_code_map* from fixture string value to ``FailureCode``.

    The checkpoint stores fixture values as strings (see
    ``fixture_plan_to_checkpoint``), so comparisons are string-based.
    """

    def __init__(
        self,
        *,
        pass_values: frozenset[str],
        failure_code_map: dict[str, FailureCode],
        phase: str,
    ) -> None:
        self._pass_values = pass_values
        self._failure_code_map = failure_code_map
        self._phase = phase

    def evaluate(self, state: Mapping[str, Any]) -> Failure | None:
        fixture_plan = state.get("fixture_plan")
        if not isinstance(fixture_plan, Mapping):
            return None
        sequence = fixture_plan.get(self._phase)
        if not sequence or not isinstance(sequence, (tuple, list)):
            return None
        index = completed_visits(state, self._phase)
        # Clamp index to last element
        clamped = min(index, len(sequence) - 1)
        value = str(sequence[clamped])
        if value in self._pass_values:
            return None
        code = self._failure_code_map.get(value)
        if code is None:
            return None
        return Failure(code=code, rule_name="fixture_sequence", description=f"fixture: {value}")


# ---------------------------------------------------------------------------
# GateRule adapter
# ---------------------------------------------------------------------------


def _make_fixture_rule(
    phase: str,
    pass_values: frozenset[str],
    failure_code_map: dict[str, FailureCode],
) -> GateRule:
    instance = FixtureSequenceRule(
        pass_values=pass_values,
        failure_code_map=failure_code_map,
        phase=phase,
    )
    # Use the first failure code as the registered code (for multi-code
    # rules the registered code is just a representative).
    registered_code = next(iter(failure_code_map.values())) if failure_code_map else FailureCode.WORK_FAILED
    return GateRule(
        name=f"fixture_sequence_{phase}",
        evaluate=instance.evaluate,
        failure_code=registered_code,
    )


# ---------------------------------------------------------------------------
# Per-phase GateDefinitions
# ---------------------------------------------------------------------------


def _wave_route_map() -> dict[PhaseVerdict, str]:
    return {
        PhaseVerdict.PASS: "pass",
        PhaseVerdict.REPAIR: "repair",
        PhaseVerdict.BLOCKED: "exhausted",
    }


def _wave_fixture_map() -> dict[str, FailureCode]:
    return {"repair": FailureCode.WORK_FAILED}


def _synthesis_route_map() -> dict[PhaseVerdict, str]:
    return {
        PhaseVerdict.PASS: "pass",
        PhaseVerdict.REPAIR: "evidence_needed",
        PhaseVerdict.BLOCKED: "exhausted",
    }


def _synthesis_fixture_map() -> dict[str, FailureCode]:
    return {"evidence_needed": FailureCode.MISSING_EVIDENCE}


def _readiness_route_resolver(verdict: PhaseVerdict, failures: tuple[Failure, ...]) -> str:
    if verdict is PhaseVerdict.PASS:
        return "pass"
    if verdict is PhaseVerdict.BLOCKED:
        return "exhausted"
    # REPAIR: map failure code to route
    code_to_route = {
        FailureCode.REPAIR_TARGETED.value: "repair_targeted",
        FailureCode.REPAIR_SYNTHESIS.value: "repair_synthesis",
        FailureCode.REPAIR_HITL2.value: "repair_hitl2",
    }
    for f in failures:
        route = code_to_route.get(f.code.value)
        if route:
            return route
    return "repair_targeted"  # fallback


def _readiness_fixture_map() -> dict[str, FailureCode]:
    return {
        "repair_targeted": FailureCode.REPAIR_TARGETED,
        "repair_synthesis": FailureCode.REPAIR_SYNTHESIS,
        "repair_hitl2": FailureCode.REPAIR_HITL2,
    }


def _final_delivery_route_resolver(verdict: PhaseVerdict, failures: tuple[Failure, ...]) -> str:
    if verdict is PhaseVerdict.PASS:
        return "pass"
    if verdict is PhaseVerdict.BLOCKED:
        return "exhausted"
    # REPAIR: distinguish self-repair vs evidence_blocked
    for f in failures:
        if f.code is FailureCode.EVIDENCE_INSUFFICIENT:
            return "evidence_blocked"
        if f.code is FailureCode.WORK_FAILED:
            return "repair"
    return "repair"  # fallback


def _final_delivery_fixture_map() -> dict[str, FailureCode]:
    return {
        "repair": FailureCode.WORK_FAILED,
        "evidence_blocked": FailureCode.EVIDENCE_INSUFFICIENT,
    }


# ---- Public registry -------------------------------------------------------


def build_fixture_gate_defs() -> dict[str, GateDefinition]:
    """Return per-phase ``GateDefinition`` for all gated phases in the fake graph.

    Non-gated nodes (bootstrap, hitl1, topic_planning, targeted_evidence,
    hitl2, rerun) are not included.
    """
    return {
        "wave0": GateDefinition(
            phase="wave0",
            rules=(_make_fixture_rule("wave0", frozenset({"pass"}), _wave_fixture_map()),),
            default_budget=3,
            route_map=_wave_route_map(),
        ),
        "wave1": GateDefinition(
            phase="wave1",
            rules=(_make_fixture_rule("wave1", frozenset({"pass"}), _wave_fixture_map()),),
            default_budget=3,
            route_map=_wave_route_map(),
        ),
        "wave2_synthesis": GateDefinition(
            phase="wave2_synthesis",
            rules=(_make_fixture_rule("wave2_synthesis", frozenset({"pass"}), _synthesis_fixture_map()),),
            default_budget=3,
            route_map=_synthesis_route_map(),
        ),
        "readiness": GateDefinition(
            phase="readiness",
            rules=(
                _make_fixture_rule(
                    "readiness",
                    frozenset({"pass"}),
                    _readiness_fixture_map(),
                ),
            ),
            default_budget=3,
            route_resolver=_readiness_route_resolver,
        ),
        "final_delivery": GateDefinition(
            phase="final_delivery",
            rules=(
                _make_fixture_rule(
                    "final_delivery",
                    frozenset({"pass"}),
                    _final_delivery_fixture_map(),
                ),
            ),
            default_budget=3,  # covers both self-repair and evidence_blocked attempts
            route_resolver=_final_delivery_route_resolver,
        ),
    }


__all__ = [
    "FixtureSequenceRule",
    "build_fixture_gate_defs",
]
