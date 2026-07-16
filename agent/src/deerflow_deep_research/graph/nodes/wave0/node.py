"""Real Wave0 source-intake node.

@impl WAN-001
@impl WAN-002
@impl WAN-005
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from deerflow_deep_research.domain.node_spec import NodeBuildDependencies
from deerflow_deep_research.domain.work_units import WORK_UNIT_GATE_VIEW_KEY
from deerflow_deep_research.engine.fake_control import node_update

from .subgraph import run_wave0_work_units_real


def build_real(dependencies: NodeBuildDependencies):
    if dependencies.work_units is None:
        raise ValueError("work_unit_capability_missing")

    async def run(state: dict[str, Any]):
        topic_registry = state.get("topic_registry") or ()
        active_topic_filter = state.get("active_topic_filter") or ()
        topic_filter: tuple[str, ...] | None = tuple(active_topic_filter) if active_topic_filter else None
        result = await run_wave0_work_units_real(
            state,
            controller=dependencies.work_units,
            topic_registry=topic_registry,
            topic_filter=topic_filter,
            clock=lambda: datetime.now(UTC),
        )
        return {
            **node_update("wave0"),
            **result.parent_update,
            WORK_UNIT_GATE_VIEW_KEY: result.gate_view,
        }

    return run


__all__ = ["build_real"]
