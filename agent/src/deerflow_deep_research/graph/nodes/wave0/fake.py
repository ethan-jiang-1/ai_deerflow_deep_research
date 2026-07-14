from datetime import UTC, datetime

from deerflow_deep_research.domain.node_spec import NodeBuildDependencies
from deerflow_deep_research.domain.work_units import WORK_UNIT_GATE_VIEW_KEY
from deerflow_deep_research.engine.fake_control import node_update

from .subgraph import run_wave0_work_units


def build_fake(dependencies: NodeBuildDependencies):
    if dependencies.work_units is None:
        raise ValueError("work_unit_capability_missing")

    async def run(state):
        result = await run_wave0_work_units(
            state,
            controller=dependencies.work_units,
            clock=lambda: datetime(2026, 1, 1, tzinfo=UTC),
        )
        return {
            **node_update("wave0"),
            **result.parent_update,
            WORK_UNIT_GATE_VIEW_KEY: result.gate_view,
        }

    return run
