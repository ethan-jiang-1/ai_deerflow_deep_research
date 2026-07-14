"""Real bootstrap node factory.

@impl BON-001
@impl BON-002
@impl BON-003

The real bootstrap atomically establishes the research bundle marker through the injected
runtime store, reads it back, and runs the pure binding validation. On a bound marker it
routes ``needs_input`` to HITL1; on a post-establish divergence (corruption) it fails closed
to a terminal ``BLOCKED`` lifecycle with ``route=exhausted``. It performs no research model
call. A ``WorkUnitStoreError`` from establishment (unavailable workspace, lock timeout)
propagates to the handler denial path and is not turned into a terminal route here.
"""

from __future__ import annotations

from typing import Any

from deerflow_deep_research.domain.bootstrap import BootstrapMarker, validate_bootstrap_binding
from deerflow_deep_research.domain.lifecycle import LifecycleStatus, TerminalReason
from deerflow_deep_research.domain.node_spec import NodeBuildDependencies
from deerflow_deep_research.domain.state import PhaseStatus
from deerflow_deep_research.engine.fake_control import node_update


def build_real(dependencies: NodeBuildDependencies):
    store = dependencies.bootstrap_bundle
    if store is None:
        raise ValueError("bootstrap_bundle_capability_missing")

    async def run(state: dict[str, Any]) -> dict[str, Any]:
        marker = BootstrapMarker(
            research_id=state["research_id"],
            start_message_id=state["start_message_id"],
            request_digest=state["request_digest"],
            state_schema_version=state["schema_version"],
        )
        await store.establish_bundle(marker)
        read_back = await store.read_marker()
        failure = None if read_back is None else validate_bootstrap_binding(read_back, state)
        if read_back is not None and failure is None:
            return node_update("bootstrap", route="needs_input")
        return {
            **node_update("bootstrap"),
            "phase_status": PhaseStatus.TERMINAL.value,
            "terminal_status": LifecycleStatus.BLOCKED.value,
            "terminal_reason": TerminalReason.GATE_BLOCKED.value,
            "route": "exhausted",
        }

    return run
