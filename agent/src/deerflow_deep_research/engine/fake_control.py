"""Deterministic zero-IO mechanics shared by change-01 fake nodes.

@impl GAK-005 — bounded_repair_update removed; gate kernel handles repair
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from deerflow_deep_research.domain.lifecycle import (
    completed_visits,
    make_attempt_id,
    text_only_content,
)

attempt_id = make_attempt_id


def fixture_sequence(state: Mapping[str, Any], key: str) -> tuple[str, ...]:
    plan = state.get("fixture_plan")
    if hasattr(plan, key):
        values = getattr(plan, key)
    elif isinstance(plan, Mapping):
        values = plan.get(key, ())
    else:
        values = ()
    sequence = tuple(value.value if hasattr(value, "value") else str(value) for value in values)
    if not sequence:
        raise ValueError(f"fixture sequence missing for {key}")
    return sequence


def choose_fixture(state: Mapping[str, Any], logical_name: str, key: str | None = None) -> str:
    """Fixture-driven route selection for non-gated nodes (bootstrap).

    Gated phases use ``evaluate_gate()`` instead.
    """
    sequence = fixture_sequence(state, key or logical_name)
    index = min(completed_visits(state, logical_name), len(sequence) - 1)
    return sequence[index]


def node_update(logical_name: str, **updates: Any) -> dict[str, Any]:
    """Return a minimal state update for *logical_name*.

    Does NOT include ``route`` — gated phases get their route from gate
    evaluation; non-gated nodes set route explicitly.
    """
    return {
        "phase": logical_name,
        "execution_trace": (logical_name,),
        **updates,
    }


__all__ = [
    "attempt_id",
    "choose_fixture",
    "completed_visits",
    "fixture_sequence",
    "node_update",
    "text_only_content",
]
