"""Pure contracts for explicit workflow-node registration.

@impl PRS-003
"""

from __future__ import annotations

import inspect
import re
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Any, Protocol, get_type_hints, runtime_checkable

from pydantic import BaseModel

from deerflow_deep_research.domain.context import (
    GraphContextView,
    NodeAgentContext,
    NodeExecutionRequest,
    NodeExecutionResult,
)
from deerflow_deep_research.domain.enums import NodePhase

_LOGICAL_NAME_RE = re.compile(r"^[a-z][a-z0-9_]{1,63}$")
_POLICY_NAME_RE = re.compile(r"^[a-z][a-z0-9-]{1,63}$")
_POLICY_VERSION_RE = re.compile(r"^v[1-9][0-9]*$")

NodeState = Mapping[str, Any]
NodeUpdate = Mapping[str, Any]
NodeCallable = Callable[[NodeState], NodeUpdate | Awaitable[NodeUpdate]]


@runtime_checkable
class NodeExecutionCapabilities(Protocol):
    async def run_agent(
        self,
        *,
        context: NodeAgentContext,
        request: NodeExecutionRequest,
    ) -> NodeExecutionResult: ...


@dataclass(frozen=True)
class NodeBuildDependencies:
    graph_context: GraphContextView
    agent_context: NodeAgentContext
    capabilities: NodeExecutionCapabilities


NodeFactory = Callable[[NodeBuildDependencies], NodeCallable]


@dataclass(frozen=True)
class PolicyRef:
    name: str
    version: str

    def __post_init__(self) -> None:
        if not _POLICY_NAME_RE.fullmatch(self.name):
            raise ValueError("policy name must be stable lowercase kebab-case")
        if not _POLICY_VERSION_RE.fullmatch(self.version):
            raise ValueError("policy version must use v<positive integer>")


@dataclass(frozen=True)
class NodeContracts:
    request_type: type[BaseModel]
    result_type: type[BaseModel]

    def __post_init__(self) -> None:
        if not issubclass(self.request_type, BaseModel):
            raise TypeError("node request contract must be a Pydantic model type")
        if not issubclass(self.result_type, BaseModel):
            raise TypeError("node result contract must be a Pydantic model type")


def _validate_factory(factory: NodeFactory, label: str) -> None:
    if not callable(factory):
        raise TypeError(f"{label} must be callable")
    signature = inspect.signature(factory)
    parameters = list(signature.parameters.values())
    if len(parameters) != 1 or parameters[0].kind not in {
        inspect.Parameter.POSITIONAL_ONLY,
        inspect.Parameter.POSITIONAL_OR_KEYWORD,
    }:
        raise TypeError(f"{label} must accept exactly one NodeBuildDependencies argument")
    try:
        annotation = get_type_hints(factory).get(parameters[0].name)
    except (NameError, TypeError) as exc:
        raise TypeError(f"{label} has an unresolved dependency annotation") from exc
    if annotation is not NodeBuildDependencies:
        raise TypeError(f"{label} dependency argument must be annotated as NodeBuildDependencies")


@dataclass(frozen=True)
class NodeSpec:
    logical_name: str
    phase: NodePhase
    policy: PolicyRef
    contracts: NodeContracts
    real_factory: NodeFactory
    fake_factory: NodeFactory

    def __post_init__(self) -> None:
        if not _LOGICAL_NAME_RE.fullmatch(self.logical_name):
            raise ValueError("logical node name must be stable lowercase snake_case")
        if not isinstance(self.phase, NodePhase):
            raise TypeError("phase must be a NodePhase")
        if not isinstance(self.policy, PolicyRef):
            raise TypeError("policy must be a PolicyRef")
        if not isinstance(self.contracts, NodeContracts):
            raise TypeError("contracts must be a NodeContracts")
        _validate_factory(self.real_factory, "real_factory")
        _validate_factory(self.fake_factory, "fake_factory")
