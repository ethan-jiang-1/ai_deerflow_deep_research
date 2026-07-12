"""Process-local control-host lifecycle.

@impl RUI-006

The default reflected tool must retain one GraphHost so its memory saver and
request-independent recipes survive across same-process actions.  This module
owns only that process-local singleton; it never retains request envelopes,
provider contexts, namespaces, or other request authority.
"""

from __future__ import annotations

from typing import Any

from deerflow_deep_research.runtime.graph_host import GraphHost
from deerflow_deep_research.runtime.probe import InfraProbeHandler
from deerflow_deep_research.runtime.research import build_research_handlers

_default_host: GraphHost | None = None


def build_control_graph_host(**kwargs: Any) -> GraphHost:
    """Build an isolated combined infra-probe and research control host."""
    host = GraphHost(**kwargs)
    host.register(InfraProbeHandler())
    for handler in build_research_handlers():
        host.register(handler)
    return host


def get_default_graph_host() -> GraphHost:
    """Return the lazily created process-local default control host."""
    global _default_host
    if _default_host is None:
        _default_host = build_control_graph_host()
    return _default_host


def reset_default_graph_host(host: GraphHost | None = None) -> None:
    """Replace the process-local reference, for deterministic isolated tests."""
    global _default_host
    _default_host = host


__all__ = ["build_control_graph_host", "get_default_graph_host", "reset_default_graph_host"]
