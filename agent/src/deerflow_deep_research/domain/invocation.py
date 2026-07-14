"""Reduced non-checkpointed invocation context.

@impl REG-001
@impl RUI-006
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from deerflow_deep_research.domain.context import GraphContextView
from deerflow_deep_research.domain.node_spec import NodeBuildDependencies, PolicyRef
from deerflow_deep_research.domain.work_units import Attempt, AttemptArtifactWriter, WorkSpec, WorkUnitStoreProtocol


@runtime_checkable
class NodeDependencyResolver(Protocol):
    def resolve(self, *, logical_name: str, attempt_id: str, policy: PolicyRef) -> NodeBuildDependencies: ...


@dataclass(frozen=True)
class WorkUnitWorkerDependencies:
    work_spec: WorkSpec
    attempt: Attempt
    node_dependencies: NodeBuildDependencies
    artifact_writer: AttemptArtifactWriter | None = None


@runtime_checkable
class WorkUnitDependencyResolver(Protocol):
    async def resolve_worker(
        self,
        *,
        logical_name: str,
        work_spec: WorkSpec,
        attempt: Attempt,
        policy: PolicyRef,
    ) -> WorkUnitWorkerDependencies: ...


@dataclass(frozen=True)
class WorkUnitControllerDependencies:
    store: WorkUnitStoreProtocol
    resolver: WorkUnitDependencyResolver

    def __post_init__(self) -> None:
        if not isinstance(self.store, WorkUnitStoreProtocol):
            raise TypeError("store must implement WorkUnitStoreProtocol")
        if not isinstance(self.resolver, WorkUnitDependencyResolver):
            raise TypeError("resolver must implement WorkUnitDependencyResolver")


@dataclass(frozen=True)
class GraphInvocationContext:
    graph_context: GraphContextView
    dependency_resolver: NodeDependencyResolver
    work_units: WorkUnitControllerDependencies | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.graph_context, GraphContextView):
            raise TypeError("graph_context must be a GraphContextView")
        if not isinstance(self.dependency_resolver, NodeDependencyResolver):
            raise TypeError("dependency_resolver must implement NodeDependencyResolver")


__all__ = ["GraphInvocationContext", "NodeDependencyResolver"]
