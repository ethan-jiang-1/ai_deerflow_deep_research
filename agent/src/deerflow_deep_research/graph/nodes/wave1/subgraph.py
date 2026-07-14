"""Wave1 fixture recipe over the shared work-unit component.

@impl WOU-001
@impl WOU-002
@impl WOU-003
@impl WOU-004
@impl REG-002
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import datetime
from typing import Any

from deerflow_deep_research.domain.invocation import WorkUnitControllerDependencies
from deerflow_deep_research.domain.node_spec import PolicyRef
from deerflow_deep_research.engine.work_units.kernel import WorkIntent
from deerflow_deep_research.graph.components.work_units import (
    WorkUnitComponentResult,
    run_fixture_work_unit_component,
)

WAVE1_FIXTURE_INTENTS = tuple(
    WorkIntent(
        worker_role="fixture_worker",
        scope=(f"wave1:fixture:{index}",),
        result_contract="fixture.work-unit",
        result_schema_version=1,
        required_outputs=("fixture.json",),
    )
    for index in range(3)
)


async def run_wave1_work_units(
    state: Mapping[str, Any],
    *,
    controller: WorkUnitControllerDependencies,
    clock: Callable[[], datetime],
) -> WorkUnitComponentResult:
    return await run_fixture_work_unit_component(
        state,
        logical_name="wave1",
        policy=PolicyRef(name="skeleton-wave1", version="v1"),
        controller=controller,
        intents=WAVE1_FIXTURE_INTENTS,
        clock=clock,
    )


__all__ = ["WAVE1_FIXTURE_INTENTS", "run_wave1_work_units"]
