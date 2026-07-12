"""Runtime projection from a trusted envelope onto pure domain contracts.

@impl RUI-002

Projection is the only place a research scope becomes model-facing structure.
It runs only when a registered research handler supplies a validated opaque
scope id together with a ``TrustedRuntimeEnvelope``; ``infra_probe`` never calls
it. The emitted ``GraphContextView``/``NodeAgentContext`` are frozen, authority
reduced values: canonical virtual roots and opaque attribution only -- never raw
identity, AppConfig, host paths, sandbox internals, or checkpoint keys.

The node-execution ``capabilities`` are supplied by the runtime-owned node-agent
bridge (group 9). Projection packs them into ``NodeBuildDependencies`` but never
constructs a bridge itself, keeping this module free of raw runtime authority.
"""

from __future__ import annotations

import re

from deerflow_deep_research.domain.context import GraphContextView, NodeAgentContext
from deerflow_deep_research.domain.node_spec import (
    NodeBuildDependencies,
    NodeExecutionCapabilities,
)
from deerflow_deep_research.runtime.runtime_adapter import (
    OUTPUTS_VIRTUAL_ROOT,
    UPLOADS_VIRTUAL_ROOT,
    WORKSPACE_VIRTUAL_ROOT,
    TrustedRuntimeEnvelope,
)

RESEARCH_PREFIX = "deep-research"
_OPAQUE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$")
_NODE_NAME_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_POLICY_NAME_RE = re.compile(r"^[a-z][a-z0-9-]{0,63}$")


class ProjectionError(ValueError):
    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"[{code}] {detail}")
        self.code = code
        self.detail = detail


def _require_opaque_id(value: str, *, field: str) -> str:
    if not isinstance(value, str) or not _OPAQUE_ID_RE.fullmatch(value):
        raise ProjectionError("scope_invalid", f"{field} must be a bounded URL-safe opaque id")
    return value


def project_research_scope(
    envelope: TrustedRuntimeEnvelope,
    *,
    research_scope_id: str,
) -> GraphContextView:
    """Derive the frozen, model-facing graph context for a validated scope.

    The ``envelope`` argument proves a registered handler already adapted trusted
    runtime; the ``research_scope_id`` is that handler's validated opaque id. No
    raw tool argument selects host paths here: roots are derived purely from
    canonical virtual prefixes and the validated id.
    """
    if not isinstance(envelope, TrustedRuntimeEnvelope):
        raise ProjectionError("envelope_required", "research projection requires a trusted envelope")
    scope = _require_opaque_id(research_scope_id, field="research_scope_id")
    return GraphContextView(
        research_scope_id=scope,
        workspace_root=f"{WORKSPACE_VIRTUAL_ROOT}/{RESEARCH_PREFIX}/{scope}",
        uploads_root=UPLOADS_VIRTUAL_ROOT,
        outputs_root=f"{OUTPUTS_VIRTUAL_ROOT}/{RESEARCH_PREFIX}/{scope}",
    )


def project_node_agent(
    graph_context: GraphContextView,
    *,
    node_name: str,
    attempt_id: str,
    policy_name: str,
) -> NodeAgentContext:
    """Derive the frozen per-node/attempt context under a graph scope."""
    if not isinstance(graph_context, GraphContextView):
        raise ProjectionError("graph_context_required", "node projection requires a GraphContextView")
    if not _NODE_NAME_RE.fullmatch(node_name):
        raise ProjectionError("node_name_invalid", "node name must be stable lowercase snake_case")
    if not _POLICY_NAME_RE.fullmatch(policy_name):
        raise ProjectionError("policy_name_invalid", "policy name must be stable lowercase kebab-case")
    attempt = _require_opaque_id(attempt_id, field="attempt_id")
    return NodeAgentContext(
        research_scope_id=graph_context.research_scope_id,
        node_name=node_name,
        attempt_id=attempt,
        workspace_root=graph_context.workspace_root,
        attempt_root=f"{graph_context.workspace_root}/attempts/{attempt}",
        policy_name=policy_name,
    )


def build_node_dependencies(
    graph_context: GraphContextView,
    agent_context: NodeAgentContext,
    capabilities: NodeExecutionCapabilities,
) -> NodeBuildDependencies:
    """Pack reduced context with the injected node-agent bridge capabilities."""
    if not isinstance(capabilities, NodeExecutionCapabilities):
        raise ProjectionError("capabilities_required", "capabilities must implement NodeExecutionCapabilities")
    return NodeBuildDependencies(
        graph_context=graph_context,
        agent_context=agent_context,
        capabilities=capabilities,
    )


__all__ = [
    "ProjectionError",
    "build_node_dependencies",
    "project_node_agent",
    "project_research_scope",
]
