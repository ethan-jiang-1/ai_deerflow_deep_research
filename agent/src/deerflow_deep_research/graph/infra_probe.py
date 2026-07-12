"""Isolated one-node infrastructure-probe graph and state.

@impl RUI-001

``InfraProbeState`` is private diagnostic state -- a schema version, opaque probe
id, monotonic visit count, effective provider kind, and last-seen marker. It is
not ``ResearchState``, has no interrupt, and keeps its own topology/namespace so
old probe rows can never be interpreted as research state when change 01 adds the
fake research graph. Unknown probe schema versions fail closed at the handler.
"""

from __future__ import annotations

from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

PROBE_SCHEMA_VERSION = 1
INFRA_PROBE_ACTION = "infra_probe"


class InfraProbeState(TypedDict, total=False):
    schema_version: int
    probe_id: str
    visits: int
    provider_kind: str
    last_marker: str


def _probe_node(state: InfraProbeState) -> dict[str, Any]:
    visits = (state.get("visits") or 0) + 1
    return {"visits": visits, "last_marker": f"visit-{visits}"}


def build_infra_probe_graph() -> StateGraph:
    """Return the uncompiled one-node probe builder (request-independent recipe)."""
    builder = StateGraph(InfraProbeState)
    builder.add_node("probe", _probe_node)
    builder.add_edge(START, "probe")
    builder.add_edge("probe", END)
    return builder


__all__ = ["INFRA_PROBE_ACTION", "PROBE_SCHEMA_VERSION", "InfraProbeState", "build_infra_probe_graph"]
