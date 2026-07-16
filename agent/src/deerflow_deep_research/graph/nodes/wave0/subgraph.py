"""Wave0 fixture recipe over the shared work-unit component.

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

WAVE0_FIXTURE_INTENTS = tuple(
    WorkIntent(
        worker_role="fixture_worker",
        scope=(f"wave0:fixture:{index}",),
        result_contract="fixture.work-unit",
        result_schema_version=1,
        required_outputs=("fixture.json",),
    )
    for index in range(3)
)


def materialize_wave0_intents(
    topic_registry: Mapping[str, Any] | tuple[Mapping[str, Any], ...] | None,
) -> tuple[WorkIntent, ...]:
    """Build one real source-intake ``WorkIntent`` per topic in the planner registry.

    @impl WAN-001
    """
    intents: list[WorkIntent] = []
    for entry in topic_registry or ():
        if not isinstance(entry, Mapping):
            continue
        topic_id = entry.get("topic_id")
        if not isinstance(topic_id, str) or not topic_id.strip():
            continue
        intents.append(
            WorkIntent(
                worker_role="wave0_intake",
                scope=(topic_id,),
                result_contract="wave0.source-intake",
                result_schema_version=1,
                required_outputs=(),
            )
        )
    if not intents:
        raise ValueError("topic_registry_empty")
    return tuple(intents)


async def run_wave0_work_units(
    state: Mapping[str, Any],
    *,
    controller: WorkUnitControllerDependencies,
    clock: Callable[[], datetime],
    fault_hook: Callable[[str], None] | None = None,
) -> WorkUnitComponentResult:
    return await run_fixture_work_unit_component(
        state,
        logical_name="wave0",
        policy=PolicyRef(name="skeleton-wave0", version="v1"),
        controller=controller,
        intents=WAVE0_FIXTURE_INTENTS,
        clock=clock,
        fault_hook=fault_hook,
    )


__all__ = ["WAVE0_FIXTURE_INTENTS", "materialize_wave0_intents", "run_wave0_work_units"]
