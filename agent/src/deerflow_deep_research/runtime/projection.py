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
from dataclasses import replace

from deerflow_deep_research.domain.bundle import first_work_spec_path
from deerflow_deep_research.domain.context import GraphContextView, NodeAgentContext
from deerflow_deep_research.domain.invocation import (
    NodeDependencyResolver,
    WorkUnitWorkerDependencies,
)
from deerflow_deep_research.domain.node_spec import (
    NodeBuildDependencies,
    NodeExecutionCapabilities,
    PolicyRef,
)
from deerflow_deep_research.domain.work_units import (
    ATTEMPT_ID_RE,
    MAX_WORK_SPEC_BYTES,
    WORK_ID_RE,
    Attempt,
    AttemptStatus,
    WorkSpec,
    WorkUnitStoreProtocol,
    canonical_json_bytes,
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


def project_work_unit_agent(
    graph_context: GraphContextView,
    *,
    node_name: str,
    work_spec: WorkSpec,
    attempt: Attempt,
    policy_name: str,
) -> NodeAgentContext:
    """Derive a worker context from trusted work and attempt identities.

    @impl WOU-001, WOU-003, NOA-001, REG-010
    """
    if not isinstance(graph_context, GraphContextView):
        raise ProjectionError("graph_context_required", "work-unit projection requires a GraphContextView")
    if not isinstance(work_spec, WorkSpec):
        raise ProjectionError("work_spec_required", "work-unit projection requires a validated WorkSpec")
    if not isinstance(attempt, Attempt):
        raise ProjectionError("attempt_required", "work-unit projection requires a validated Attempt")
    if not _NODE_NAME_RE.fullmatch(node_name):
        raise ProjectionError("node_name_invalid", "node name must be stable lowercase snake_case")
    if not _POLICY_NAME_RE.fullmatch(policy_name):
        raise ProjectionError("policy_name_invalid", "policy name must be stable lowercase kebab-case")
    if not WORK_ID_RE.fullmatch(work_spec.work_id):
        raise ProjectionError("work_id_invalid", "work id must use the canonical controller grammar")
    if not ATTEMPT_ID_RE.fullmatch(attempt.attempt_id):
        raise ProjectionError("attempt_id_invalid", "attempt id must use the canonical controller grammar")
    if graph_context.research_scope_id != work_spec.research_id:
        raise ProjectionError("research_scope_mismatch", "graph scope does not match the work specification")
    if (
        attempt.research_id != work_spec.research_id
        or attempt.generation != work_spec.generation
        or attempt.phase != work_spec.phase
        or attempt.work_id != work_spec.work_id
        or attempt.spec_hash != work_spec.spec_hash
    ):
        raise ProjectionError("work_attempt_mismatch", "attempt identity does not match the work specification")
    if attempt.status not in {AttemptStatus.PENDING, AttemptStatus.RUNNING}:
        raise ProjectionError("attempt_not_active", "work-unit projection requires a pending or running attempt")
    return NodeAgentContext(
        research_scope_id=graph_context.research_scope_id,
        node_name=node_name,
        attempt_id=attempt.attempt_id,
        workspace_root=graph_context.workspace_root,
        attempt_root=f"{graph_context.workspace_root}/work/{work_spec.work_id}/{attempt.attempt_id}",
        policy_name=policy_name,
    )


class RuntimeWorkUnitDependencyResolver:
    """Resolve one validated work attempt without propagating controller authority."""

    def __init__(
        self,
        graph_context: GraphContextView,
        base_resolver: NodeDependencyResolver,
        store: WorkUnitStoreProtocol,
    ) -> None:
        self._graph_context = graph_context
        self._base_resolver = base_resolver
        self._store = store

    async def resolve_worker(
        self,
        *,
        logical_name: str,
        work_spec: WorkSpec,
        attempt: Attempt,
        policy: PolicyRef,
    ) -> WorkUnitWorkerDependencies:
        first_ref = first_work_spec_path(work_spec.research_id, work_spec.work_id)
        try:
            first_bytes = await self._store.read_canonical_bytes(first_ref, max_bytes=MAX_WORK_SPEC_BYTES)
        except FileNotFoundError:
            if attempt.attempt_ordinal != 0:
                raise ValueError("work_spec_replay_missing") from None
            resolved_spec = work_spec
        else:
            try:
                resolved_spec = WorkSpec.model_validate_json(first_bytes)
            except ValueError as exc:
                raise ValueError("work_spec_replay_invalid") from exc
            if canonical_json_bytes(resolved_spec) != first_bytes or resolved_spec != work_spec:
                raise ValueError("work_spec_replay_invalid")

        await self._store.write_work_spec(resolved_spec, attempt)
        agent_context = project_work_unit_agent(
            self._graph_context,
            node_name=logical_name,
            work_spec=resolved_spec,
            attempt=attempt,
            policy_name=policy.name,
        )
        base = self._base_resolver.resolve(
            logical_name=logical_name,
            attempt_id=attempt.attempt_id,
            policy=policy,
        )
        narrowed = replace(base, agent_context=agent_context, work_units=None)
        return WorkUnitWorkerDependencies(
            work_spec=resolved_spec,
            attempt=attempt,
            node_dependencies=narrowed,
            artifact_writer=self._store.attempt_artifact_writer(work_spec, attempt),
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
    "RuntimeWorkUnitDependencyResolver",
    "build_node_dependencies",
    "project_node_agent",
    "project_research_scope",
    "project_work_unit_agent",
]
