"""Runtime wiring for the infrastructure-probe action.

@impl RUI-001

Bridges the pure ``graph/infra_probe`` topology to GraphHost: it derives the
isolated probe checkpoint namespace, refuses an unknown persisted schema version,
reads the prior visit marker, advances the monotonic visit count, and returns an
opaque result (probe id, previous/current marker, provider kind, durability) with
no user, thread, host, or internal checkpoint values. Change 00 registers only
this invoke/inspect handler; research lifecycle actions remain unavailable.
"""

from __future__ import annotations

from typing import Any

from deerflow_deep_research.graph.infra_probe import (
    INFRA_PROBE_ACTION,
    PROBE_SCHEMA_VERSION,
    build_infra_probe_graph,
)
from deerflow_deep_research.runtime.checkpoint import (
    CheckpointNamespaceError,
    derive_probe_thread_key,
    resolve_effective_provider,
)
from deerflow_deep_research.runtime.graph_host import GraphHost
from deerflow_deep_research.runtime.runtime_adapter import TrustedRuntimeEnvelope


class InfraProbeHandler:
    """Generic GraphHost action handler for the infrastructure probe."""

    action = INFRA_PROBE_ACTION

    def build_graph(self) -> Any:
        return build_infra_probe_graph()

    def derive_namespace(self, envelope: TrustedRuntimeEnvelope, action_input: Any) -> str:
        return derive_probe_thread_key(
            effective_user_id=envelope.effective_user_id,
            outer_thread_id=envelope.outer_thread_id,
            probe_id=str(action_input),
        )

    async def execute(
        self,
        graph: Any,
        *,
        config: dict[str, Any],
        envelope: TrustedRuntimeEnvelope,
        action_input: Any,
    ) -> dict[str, Any]:
        provider = resolve_effective_provider(envelope.app_config)
        prior = await graph.aget_state(config)
        prior_values = dict(prior.values) if prior and prior.values else {}
        prior_schema = prior_values.get("schema_version")
        if prior_schema is not None and prior_schema != PROBE_SCHEMA_VERSION:
            raise CheckpointNamespaceError("schema_unsupported", "probe checkpoint schema version is unknown")
        previous_visit = prior_values.get("visits")

        result = await graph.ainvoke(
            {
                "schema_version": PROBE_SCHEMA_VERSION,
                "probe_id": str(action_input),
                "provider_kind": provider.kind,
            },
            config=config,
        )
        return {
            "probe_id": str(action_input),
            "previous_visit": previous_visit,
            "current_visit": result["visits"],
            "last_marker": result["last_marker"],
            "provider_kind": provider.kind,
            "durability": provider.durability,
        }


def build_probe_graph_host(**kwargs: Any) -> GraphHost:
    host = GraphHost(**kwargs)
    host.register(InfraProbeHandler())
    return host


__all__ = ["InfraProbeHandler", "build_probe_graph_host"]
