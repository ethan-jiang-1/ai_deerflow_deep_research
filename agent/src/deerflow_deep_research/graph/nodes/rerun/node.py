"""Real rerun node — scoped invalidation, generation increment, back-edge routing.

@impl REN-001
@impl REN-002
@impl REN-003
@impl REN-004
@impl REN-005
@impl REN-006
@impl REN-007
"""

from __future__ import annotations

from typing import Any

from deerflow_deep_research.domain.lifecycle import LifecycleStatus, TerminalReason
from deerflow_deep_research.domain.node_spec import NodeBuildDependencies
from deerflow_deep_research.domain.state import PhaseStatus
from deerflow_deep_research.engine.fake_control import node_update

from .contracts import RerunPlan
from .planner import (
    apply_generation_increment,
    apply_invalidation,
    build_rerun_scope,
    determine_rerun_route,
    materialize_rerun_workspecs,
    reset_gate_state_for_scope,
)


def build_real(dependencies: NodeBuildDependencies):
    max_rerun_generations = getattr(dependencies, "max_rerun_generations", 2)

    async def run(state: dict[str, Any]) -> dict[str, Any]:
        # 1. Extract scope from HITL2 payload
        scope = build_rerun_scope(state)

        # 2. Invalidate derived projections
        invalidation = apply_invalidation(scope)

        # 3. Increment generation
        gen_update = apply_generation_increment(state)
        new_generation = gen_update["generation"]

        # 4. Materialize scoped WorkSpecs (no-op for FULL)
        workspec_update = materialize_rerun_workspecs(state, scope)

        # 5. Determine route
        route = determine_rerun_route(
            scope,
            generation=new_generation,
            max_rerun_generations=max_rerun_generations,
        )

        # 6. Reset gate state for affected phases
        gate_reset = reset_gate_state_for_scope(state, scope)

        # 7. Handle exhausted terminal state
        terminal_status = None
        terminal_reason = None
        if route == "exhausted":
            terminal_status = LifecycleStatus.BLOCKED.value
            terminal_reason = TerminalReason.RERUN_EXHAUSTED.value

        # 8. Assemble final RerunPlan (for diagnostics; not stored as-is)
        _plan = RerunPlan(
            generation=new_generation,
            parent_generation=gen_update["parent_generation"],
            scope=scope,
            route=route,
        )

        return {
            **node_update("rerun", route=route),
            **invalidation,
            **gen_update,
            **workspec_update,
            **gate_reset,
            "rerun_scope": scope.scope,
            "rerun_reason": scope.reason,
            "phase_status": PhaseStatus.WAITING.value,
            **(dict(terminal_status=terminal_status) if terminal_status else {}),
            **(dict(terminal_reason=terminal_reason) if terminal_reason else {}),
        }

    return run
