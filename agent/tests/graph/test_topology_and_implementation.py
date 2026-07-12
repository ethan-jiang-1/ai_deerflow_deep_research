"""Explicit topology and implementation-map contracts (REG-001/005)."""

from __future__ import annotations

from dataclasses import replace

import pytest

from deerflow_deep_research.domain.context import NodeExecutionRequest, NodeExecutionResult
from deerflow_deep_research.domain.enums import NodePhase
from deerflow_deep_research.domain.node_spec import (
    UNAVAILABLE_REAL_FACTORY,
    NodeBuildDependencies,
    NodeContracts,
    NodeSpec,
    PolicyRef,
)
from deerflow_deep_research.graph.builder import build_research_graph
from deerflow_deep_research.graph.implementation_map import (
    ImplementationMapError,
    resolve_implementations,
)
from deerflow_deep_research.graph.registry import load_research_node_specs
from deerflow_deep_research.graph.topology import LOGICAL_NODES, NORMALIZED_EDGES, validate_topology


async def _fake_node(state):
    return state


def _fake_factory(_dependencies: NodeBuildDependencies):
    return _fake_node


def _spec(name: str) -> NodeSpec:
    return NodeSpec(
        logical_name=name,
        phase=NodePhase.ORCHESTRATION,
        policy=PolicyRef(name="fake-policy", version="v1"),
        contracts=NodeContracts(request_type=NodeExecutionRequest, result_type=NodeExecutionResult),
        real_factory=UNAVAILABLE_REAL_FACTORY,
        fake_factory=_fake_factory,
    )


def test_normalized_topology_has_eleven_reachable_nodes_and_no_internal_workers() -> None:
    assert LOGICAL_NODES == (
        "bootstrap",
        "hitl1",
        "topic_planning",
        "wave0",
        "wave1",
        "wave2_synthesis",
        "targeted_evidence",
        "hitl2",
        "rerun",
        "readiness",
        "final_delivery",
    )
    validate_topology(LOGICAL_NODES, NORMALIZED_EDGES)
    assert not any("dispatch" in edge.source or "join" in edge.source for edge in NORMALIZED_EDGES)


def test_full_fake_map_resolves_every_explicit_node() -> None:
    specs = {name: _spec(name) for name in LOGICAL_NODES}
    resolved = resolve_implementations(specs, {name: "fake" for name in LOGICAL_NODES})
    assert tuple(resolved) == LOGICAL_NODES
    assert all(factory is _fake_factory for factory in resolved.values())


def test_real_selection_fails_before_invocation_and_never_falls_back() -> None:
    specs = {name: _spec(name) for name in LOGICAL_NODES}
    modes = {name: "fake" for name in LOGICAL_NODES}
    modes["wave0"] = "real"
    with pytest.raises(ImplementationMapError, match="implementation_unavailable.*wave0"):
        resolve_implementations(specs, modes)


def test_incomplete_or_unknown_map_is_rejected() -> None:
    specs = {name: _spec(name) for name in LOGICAL_NODES}
    with pytest.raises(ImplementationMapError, match="implementation_map_incomplete"):
        resolve_implementations(specs, {"bootstrap": "fake"})
    modes = {name: "fake" for name in LOGICAL_NODES} | {"extra": "fake"}
    with pytest.raises(ImplementationMapError, match="implementation_map_unknown"):
        resolve_implementations(specs, modes)


def test_explicit_mixed_override_preserves_identical_graph_shape() -> None:
    specs = load_research_node_specs()
    test_wave0 = replace(specs["wave0"], real_factory=_fake_factory)
    modes = {name: "fake" for name in LOGICAL_NODES} | {"wave0": "real"}
    mixed = build_research_graph(implementation_modes=modes, spec_overrides={"wave0": test_wave0}).compile()
    fake = build_research_graph().compile()
    assert {(edge.source, edge.target) for edge in mixed.get_graph().edges} == {
        (edge.source, edge.target) for edge in fake.get_graph().edges
    }
    with pytest.raises(ImplementationMapError, match="implementation_unavailable.*wave0"):
        build_research_graph(implementation_modes=modes)
