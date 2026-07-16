"""Deterministic rerun planner — scope extraction, invalidation, generation, routing.

@impl REN-001
@impl REN-002
@impl REN-003
@impl REN-004
@impl REN-005
@impl REN-006
"""

from __future__ import annotations

from typing import Any

from .contracts import RerunScope

_VALID_SCOPES = frozenset({"full", "topic", "finding"})


def build_rerun_scope(state: dict[str, Any]) -> RerunScope:
    """Extract typed RerunScope from hitl2_rerun_payload in checkpoint state.

    Pure parsing; generation is not involved. Defaults to FULL when payload is
    absent, None, or contains invalid data.
    """
    payload = state.get("hitl2_rerun_payload")
    if not isinstance(payload, dict):
        return RerunScope(scope="full", reason="")

    scope_key = payload.get("scope")
    if not isinstance(scope_key, str) or scope_key not in _VALID_SCOPES:
        raise ValueError(f"invalid_rerun_scope: {scope_key!r}")

    reason = payload.get("reason", "")
    if not isinstance(reason, str):
        reason = ""

    target_topic_ids = _parse_str_tuple(payload.get("target_topic_ids"))
    target_finding_ids = _parse_str_tuple(payload.get("target_finding_ids"))

    if scope_key == "topic":
        # Validate target_topic_ids against topic_registry
        topic_registry = state.get("topic_registry") or ()
        registry_ids = _extract_topic_ids(topic_registry)
        for tid in target_topic_ids:
            if tid not in registry_ids:
                # Invalid ID → fall back to FULL
                return RerunScope(scope="full", reason=reason)
        retain_topic_ids = tuple(tid for tid in registry_ids if tid not in target_topic_ids)
        return RerunScope(
            scope="topic",
            reason=reason,
            target_topic_ids=target_topic_ids,
            target_finding_ids=(),
            retain_topic_ids=retain_topic_ids,
        )

    if scope_key == "finding":
        return RerunScope(
            scope="finding",
            reason=reason,
            target_topic_ids=(),
            target_finding_ids=target_finding_ids,
            retain_topic_ids=_parse_str_tuple(payload.get("retain_topic_ids")),
        )

    # scope_key == "full"
    return RerunScope(
        scope="full",
        reason=reason,
        target_topic_ids=(),
        target_finding_ids=(),
        retain_topic_ids=(),
    )


def apply_invalidation(_scope: RerunScope) -> dict[str, Any]:
    """Clear derived projections and consume the HITL2 payload.

    Returns a dict of checkpoint field updates. Does not touch sandbox files.
    """
    return {
        "synthesis_ref": None,
        "decision_brief_ref": None,
        "report_refs": (),
        "repair_counts": {},
        "hitl2_rerun_payload": None,
    }


def apply_generation_increment(state: dict[str, Any]) -> dict[str, Any]:
    """Increment generation monotonically and record parent."""
    current_gen = int(state.get("generation", 0))
    return {
        "generation": current_gen + 1,
        "parent_generation": current_gen,
    }


def determine_rerun_route(
    scope: RerunScope,
    *,
    generation: int,
    max_rerun_generations: int,
) -> str:
    """Determine the graph back edge based on scope and generation ceiling."""
    if generation >= max_rerun_generations:
        return "exhausted"

    if scope.scope == "full":
        return "topic_planning"
    if scope.scope == "topic":
        return "wave0"
    # finding: stale sources → wave0 (conservative default)
    return "wave0"


def reset_gate_state_for_scope(
    state: dict[str, Any],
    scope: RerunScope,
) -> dict[str, Any]:
    """Reset gate_attempts and repair_budget for phases affected by the rerun scope."""
    if scope.scope == "full":
        # Full rerun: reset all phases
        return {
            "gate_attempts_by_phase": {},
            "repair_budget_by_phase": {},
        }
    # For topic/finding scoped reruns, reset all phases too —
    # the downstream planners filter by active_topic_filter, and the
    # gates need to evaluate the new work from scratch.
    return {
        "gate_attempts_by_phase": {},
        "repair_budget_by_phase": {},
    }


def materialize_rerun_workspecs(
    state: dict[str, Any],
    scope: RerunScope,
) -> dict[str, Any]:
    """Create scoped WorkSpecs via work-unit controller for TOPIC/FINDING.

    FULL scope is a no-op — topic_planning handles WorkSpec creation.
    Returns a dict with pending_work_ids and active_topic_filter.
    """
    if scope.scope == "full":
        return {
            "pending_work_ids": (),
            "active_topic_filter": (),
        }

    if scope.scope == "topic":
        return {
            "pending_work_ids": (),  # wave0 planner creates WorkSpecs via topic_filter
            "active_topic_filter": scope.target_topic_ids,
        }

    # finding scope
    return {
        "pending_work_ids": (),
        "active_topic_filter": scope.retain_topic_ids,
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_str_tuple(value: Any) -> tuple[str, ...]:
    """Coerce a list/tuple of strings to a tuple of strings."""
    if isinstance(value, (list, tuple)):
        return tuple(str(v) for v in value if isinstance(v, str))
    return ()


def _extract_topic_ids(
    topic_registry: tuple[dict[str, Any], ...] | list[dict[str, Any]],
) -> frozenset[str]:
    """Extract all topic_id values from the topic registry."""
    ids: set[str] = set()
    for entry in topic_registry or ():
        if isinstance(entry, dict):
            tid = entry.get("topic_id")
            if isinstance(tid, str):
                ids.add(tid)
    return frozenset(ids)
