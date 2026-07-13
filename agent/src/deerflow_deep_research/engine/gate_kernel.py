"""Deterministic gate evaluation engine.

@impl GAK-001
@impl GAK-003
@impl GAK-004
@impl GAK-006
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from deerflow_deep_research.domain.failure_codes import FailureCode
from deerflow_deep_research.domain.gate import (
    Failure,
    GateDefinition,
    GateResult,
    PhaseVerdict,
)
from deerflow_deep_research.domain.lifecycle import LifecycleStatus, TerminalReason
from deerflow_deep_research.domain.state import PhaseStatus, WriterRole, apply_research_update

# ---------------------------------------------------------------------------
# Verdict derivation
# ---------------------------------------------------------------------------


def _derive_verdict(
    failures: tuple[Failure, ...],
    *,
    remaining_budget: int,
) -> tuple[PhaseVerdict, bool]:
    """Derive the gate verdict and degraded flag from collected failures."""
    if not failures:
        return PhaseVerdict.PASS, False

    has_hard = any(f.classification == "hard" for f in failures)
    has_repairable_or_semantic = any(f.classification in ("repairable", "semantic") for f in failures)
    has_only_degradable = all(f.classification == "degradable" for f in failures)

    if has_hard:
        return PhaseVerdict.BLOCKED, False

    if has_only_degradable:
        return PhaseVerdict.PASS, True  # degraded pass

    if has_repairable_or_semantic:
        if remaining_budget <= 0:
            return PhaseVerdict.BLOCKED, False
        return PhaseVerdict.REPAIR, False

    return PhaseVerdict.PASS, False


# ---------------------------------------------------------------------------
# Fatigue detection
# ---------------------------------------------------------------------------


def _compute_consecutive(
    *,
    phase: str,
    fingerprint: tuple[tuple[str, str], ...],
    previous_feedback: Any,  # deserialized GateResult dict or None
) -> int:
    """Compare current fingerprint against the previous evaluation of the same phase."""
    if previous_feedback is None or not isinstance(previous_feedback, Mapping):
        return 1
    if previous_feedback.get("phase") != phase:
        return 1
    prev_fingerprint = tuple(tuple(fp) for fp in previous_feedback.get("fingerprint", ()))
    if prev_fingerprint == fingerprint:
        return int(previous_feedback.get("consecutive", 0)) + 1
    return 1


# ---------------------------------------------------------------------------
# Budget tracking
# ---------------------------------------------------------------------------


def _resolve_budget(
    state: Mapping[str, Any],
    phase: str,
    default_budget: int,
) -> tuple[int, dict[str, int]]:
    """Return (budget_for_this_phase, full_updated_dict)."""
    current: dict[str, int] = dict(state.get("repair_budget_by_phase") or {})
    if phase not in current:
        current[phase] = default_budget
    return current[phase], current


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def evaluate_gate(
    state: Mapping[str, Any],
    phase: str,
    gate_def: GateDefinition,
) -> GateResult:
    """Run every registered rule, collect failures, and produce a typed verdict.

    Pure synchronous function — no I/O, no model calls, no state mutation.
    """
    # 1. Collect failures from all rules
    failures: list[Failure] = []
    for rule in gate_def.rules:
        result = rule.evaluate(state)
        if result is not None:
            failures.append(result)

    # 2. Compute attempt count
    current_attempts: dict[str, int] = dict(state.get("gate_attempts_by_phase") or {})
    attempt = current_attempts.get(phase, 0) + 1

    # 3. Budget tracking
    budget, full_budget = _resolve_budget(state, phase, gate_def.default_budget)

    # 4. Derive verdict
    failures_tuple = tuple(failures)
    verdict, degraded = _derive_verdict(failures_tuple, remaining_budget=budget)

    # 5. Build failure fingerprint
    fingerprint = tuple((f.code.value, f.rule_name) for f in failures_tuple)

    # 6. Fatigue detection
    previous_feedback = state.get("latest_gate_feedback")
    consecutive = _compute_consecutive(
        phase=phase,
        fingerprint=fingerprint,
        previous_feedback=previous_feedback,
    )

    # 7. Escalate fatigue → BLOCKED
    if consecutive >= 3 and verdict is PhaseVerdict.REPAIR:
        verdict = PhaseVerdict.BLOCKED
        failures_tuple = (
            *failures_tuple,
            Failure(
                code=FailureCode.FATIGUE_ESCALATION,
                rule_name="gate_kernel",
                description=f"same failure fingerprint for {consecutive} consecutive evaluations",
            ),
        )

    # 8. Escalate budget exhaustion → BLOCKED
    #    Covers both the case where _derive_verdict returned REPAIR (budget=0
    #    after prior decrements) and where it returned BLOCKED (budget=0 from
    #    the start via default_budget=0).
    if budget <= 0 and any(f.classification in ("repairable", "semantic") for f in failures_tuple):
        if verdict is not PhaseVerdict.BLOCKED:
            verdict = PhaseVerdict.BLOCKED
        if not any(f.code is FailureCode.REPAIR_BUDGET_EXHAUSTED for f in failures_tuple):
            failures_tuple = (
                *failures_tuple,
                Failure(
                    code=FailureCode.REPAIR_BUDGET_EXHAUSTED,
                    rule_name="gate_kernel",
                    description=f"repair budget exhausted for phase {phase}",
                ),
            )

    # 9. Update budget for REPAIR verdict
    remaining_budget = budget
    if verdict is PhaseVerdict.REPAIR:
        remaining_budget = budget - 1
        full_budget[phase] = remaining_budget

    # 10. Collect failed_refs
    failed_refs = tuple(f.ref for f in failures_tuple if f.ref is not None)

    # 11. Compute new_generation — only on BLOCKED (terminal state change).
    #    PASS does not increment generation; the rerun node handles its own
    #    increment. Generation tracks major lifecycle transitions, not every
    #    phase pass.
    current_gen = int(state.get("generation", 0))
    new_generation: int | None = None
    if verdict is PhaseVerdict.BLOCKED:
        new_generation = current_gen + 1

    # 12. Resolve route
    route = gate_def.resolve_route(verdict, failures_tuple)

    # 13. Build GateResult
    return GateResult(
        phase=phase,
        verdict=verdict,
        route=route,
        failures=failures_tuple,
        failed_refs=failed_refs,
        degraded=degraded,
        attempt=attempt,
        remaining_budget=remaining_budget,
        new_generation=new_generation,
        fingerprint=fingerprint,
        consecutive=consecutive,
    )


# ---------------------------------------------------------------------------
# State update conversion
# ---------------------------------------------------------------------------


def gate_result_to_state_update(
    gate_result: GateResult,
    phase: str,
    state: Mapping[str, Any],
) -> dict[str, Any]:
    """Convert a ``GateResult`` into a partial ``ResearchState`` update dict.

    Writes full dicts for ``gate_attempts_by_phase`` and
    ``repair_budget_by_phase`` because LangGraph's ``LastValue`` channel
    replaces the entire dict on each write.
    """
    update: dict[str, Any] = {
        "route": gate_result.route,
        "latest_gate_feedback": gate_result.model_dump(mode="json"),
    }

    # Full dicts (LastValue channel)
    current_attempts: dict[str, int] = dict(state.get("gate_attempts_by_phase") or {})
    current_attempts[phase] = gate_result.attempt
    update["gate_attempts_by_phase"] = current_attempts

    current_budget: dict[str, int] = dict(state.get("repair_budget_by_phase") or {})
    current_budget[phase] = gate_result.remaining_budget
    update["repair_budget_by_phase"] = current_budget

    # Generation
    if gate_result.new_generation is not None:
        update["generation"] = gate_result.new_generation

    # Terminal fields on BLOCKED
    if gate_result.verdict is PhaseVerdict.BLOCKED:
        update["terminal_reason"] = TerminalReason.GATE_BLOCKED.value
        update["terminal_status"] = LifecycleStatus.BLOCKED.value
        update["phase_status"] = PhaseStatus.TERMINAL.value

    # Validate through authority reducer
    apply_research_update(state, update, writer=WriterRole.GATE)
    return update


__all__ = [
    "evaluate_gate",
    "gate_result_to_state_update",
]
