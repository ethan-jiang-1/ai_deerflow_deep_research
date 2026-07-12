"""Deterministic zero-IO mechanics shared by change-01 fake nodes."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from deerflow_deep_research.domain.lifecycle import (
    LifecycleStatus,
    TerminalReason,
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
    sequence = fixture_sequence(state, key or logical_name)
    index = min(completed_visits(state, logical_name), len(sequence) - 1)
    return sequence[index]


def node_update(logical_name: str, *, route: str, **updates: Any) -> dict[str, Any]:
    return {
        "phase": logical_name,
        "route": route,
        "execution_trace": (logical_name,),
        **updates,
    }


def bounded_repair_update(state: Mapping[str, Any], logical_name: str, route: str, *, limit: int = 3) -> dict[str, Any]:
    counts = dict(state.get("repair_counts") or {})
    if route.startswith("repair"):
        prior = int(counts.get(logical_name, 0))
        if prior >= limit:
            return node_update(
                logical_name,
                route="exhausted",
                repair_counts=counts,
                status=LifecycleStatus.BLOCKED.value,
                terminal_reason=TerminalReason.REPAIR_EXHAUSTED.value,
            )
        counts[logical_name] = prior + 1
    return node_update(logical_name, route=route, repair_counts=counts)


__all__ = [
    "attempt_id",
    "bounded_repair_update",
    "choose_fixture",
    "completed_visits",
    "fixture_sequence",
    "node_update",
    "text_only_content",
]
