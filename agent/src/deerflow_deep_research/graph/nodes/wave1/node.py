"""Real Wave1 evidence extraction node.

@impl WON-001
@impl WON-002
@impl WON-005
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from deerflow_deep_research.domain.node_spec import NodeBuildDependencies
from deerflow_deep_research.domain.work_units import WORK_UNIT_GATE_VIEW_KEY
from deerflow_deep_research.engine.fake_control import node_update

from .subgraph import run_wave1_work_units_real


def build_real(dependencies: NodeBuildDependencies):
    if dependencies.work_units is None:
        raise ValueError("work_unit_capability_missing")

    async def run(state: dict[str, Any]) -> dict[str, Any]:
        topic_registry = state.get("topic_registry") or ()
        # Collect Wave0 URLs for dedup
        wave0_urls: set[str] = set()
        accepted_refs = state.get("accepted_submission_refs") or ()
        for _ref in accepted_refs:
            # Source URLs are in the submission records; for now, derive from
            # source_refs in the work-unit state. In production this is read
            # from the sandbox ledger.
            pass
        # Read from checkpointed wave0 source refs if available
        for _spec_entry in state.get("work_specs_by_id", {}).values():
            pass  # Wave0 URLs are in the ledger, not checkpoint state

        result = await run_wave1_work_units_real(
            state,
            controller=dependencies.work_units,
            topic_registry=topic_registry,
            capabilities=dependencies.capabilities,
            wave0_urls=frozenset(wave0_urls),
            clock=lambda: datetime.now(UTC),
        )
        return {
            **node_update("wave1"),
            **result.parent_update,
            WORK_UNIT_GATE_VIEW_KEY: result.gate_view,
        }

    return run
