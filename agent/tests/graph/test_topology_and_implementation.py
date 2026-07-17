"""Explicit topology and implementation-map contracts.

@impl HIT-003
@impl REG-001
@impl REG-005
@impl WSN-004
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from deerflow_deep_research.domain.context import NodeExecutionRequest, NodeExecutionResult
from deerflow_deep_research.domain.enums import NodePhase
from deerflow_deep_research.domain.node_spec import (
    UNAVAILABLE_REAL_FACTORY,
    NodeBuildDependencies,
    NodeCapability,
    NodeContracts,
    NodeSpec,
    PolicyRef,
)
from deerflow_deep_research.graph.builder import _route, build_research_graph
from deerflow_deep_research.graph.implementation_map import (
    ImplementationMapError,
    resolve_implementations,
)
from deerflow_deep_research.graph.nodes.hitl1.contracts import Hitl1Result
from deerflow_deep_research.graph.registry import load_research_node_specs
from deerflow_deep_research.graph.topology import LOGICAL_NODES, NORMALIZED_EDGES, TopologyEdge, validate_topology


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
    assert not {"initialize", "allocate", "worker", "submit", "drain"} & set(LOGICAL_NODES)


def test_only_wave0_and_wave1_declare_work_unit_controller_capability() -> None:
    specs = load_research_node_specs()
    declaring = {name for name, spec in specs.items() if NodeCapability.WORK_UNIT_CONTROLLER in spec.capabilities}
    assert declaring == {"wave0", "wave1", "targeted_evidence"}


def test_real_hitl1_declares_only_request_bundle_capability() -> None:
    specs = load_research_node_specs()
    hitl1 = specs["hitl1"]
    assert hitl1.real_factory is not UNAVAILABLE_REAL_FACTORY
    assert hitl1.capabilities == frozenset({NodeCapability.REQUEST_BUNDLE})
    assert NodeCapability.BOOTSTRAP_BUNDLE not in hitl1.capabilities
    assert NodeCapability.WORK_UNIT_CONTROLLER not in hitl1.capabilities


def test_hitl1_route_contract_and_topology_include_followup_and_exhausted() -> None:
    assert set(Hitl1Result.model_fields["route"].annotation.__args__) == {
        "accepted",
        "cancel",
        "needs_followup",
        "exhausted",
    }
    assert TopologyEdge("hitl1", "needs_followup", "hitl1") in NORMALIZED_EDGES
    assert TopologyEdge("hitl1", "exhausted", "blocked") in NORMALIZED_EDGES


def test_route_remains_a_typed_direct_read_of_state_route() -> None:
    assert _route({"route": "pass"}) == "pass"
    assert _route({"route": "repair"}) == "repair"
    with pytest.raises(ValueError, match="typed_route_missing"):
        _route({})
    with pytest.raises(ValueError, match="typed_route_missing"):
        _route({"route": None})


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
    test_node = replace(specs["readiness"], real_factory=_fake_factory)
    modes = {name: "fake" for name in LOGICAL_NODES} | {"readiness": "real"}
    mixed = build_research_graph(implementation_modes=modes, spec_overrides={"readiness": test_node}).compile()
    fake = build_research_graph().compile()
    assert {(edge.source, edge.target) for edge in mixed.get_graph().edges} == {
        (edge.source, edge.target) for edge in fake.get_graph().edges
    }


def test_mixed_real_hitl2_chain_resolves_and_compiles() -> None:
    """Mixed mode with hitl2 real chain selects real factories and compiles."""
    specs = load_research_node_specs()
    real_names = {
        "bootstrap",
        "hitl1",
        "topic_planning",
        "wave0",
        "targeted_evidence",
        "wave1",
        "wave2_synthesis",
        "hitl2",
    }
    modes = {name: ("real" if name in real_names else "fake") for name in LOGICAL_NODES}
    resolved = resolve_implementations(specs, modes)
    for name in real_names:
        assert resolved[name] is specs[name].real_factory
    build_research_graph(implementation_modes=modes).compile()


def test_mixed_real_bootstrap_resolves_and_preserves_shape() -> None:
    specs = load_research_node_specs()
    # Change 05 ships the real bootstrap factory (no longer the unavailable sentinel).
    assert specs["bootstrap"].real_factory is not UNAVAILABLE_REAL_FACTORY
    modes = {name: "fake" for name in LOGICAL_NODES} | {"bootstrap": "real"}
    resolved = resolve_implementations(specs, modes)
    assert resolved["bootstrap"] is specs["bootstrap"].real_factory
    for name in LOGICAL_NODES:
        if name != "bootstrap":
            assert resolved[name] is specs[name].fake_factory
    mixed = build_research_graph(implementation_modes=modes).compile()
    fake = build_research_graph().compile()
    assert {(edge.source, edge.target) for edge in mixed.get_graph().edges} == {
        (edge.source, edge.target) for edge in fake.get_graph().edges
    }


def test_mixed_real_bootstrap_and_hitl1_resolves() -> None:
    specs = load_research_node_specs()
    modes = {name: "fake" for name in LOGICAL_NODES} | {"bootstrap": "real", "hitl1": "real"}
    resolved = resolve_implementations(specs, modes)
    assert resolved["bootstrap"] is specs["bootstrap"].real_factory
    assert resolved["hitl1"] is specs["hitl1"].real_factory
    for name in LOGICAL_NODES:
        if name not in {"bootstrap", "hitl1"}:
            assert resolved[name] is specs[name].fake_factory
    build_research_graph(implementation_modes=modes).compile()


def test_mixed_real_wave0_chain_resolves_and_compiles() -> None:
    """Mixed mode with the four-real chain selects all four real factories and compiles.

    @impl WAN-005
    @impl PRS-003
    """
    specs = load_research_node_specs()
    modes = {name: "fake" for name in LOGICAL_NODES} | {
        "bootstrap": "real",
        "hitl1": "real",
        "topic_planning": "real",
        "wave0": "real",
    }
    resolved = resolve_implementations(specs, modes)
    for name in ("bootstrap", "hitl1", "topic_planning", "wave0"):
        assert resolved[name] is specs[name].real_factory, f"{name} should use real factory"
    for name in LOGICAL_NODES:
        if name not in {"bootstrap", "hitl1", "topic_planning", "wave0"}:
            assert resolved[name] is specs[name].fake_factory, f"{name} should use fake factory"
    # Graph compiles without error — topology shape preserved.
    build_research_graph(implementation_modes=modes).compile()


def test_mixed_real_wave1_chain_resolves_and_compiles() -> None:
    """Mixed mode with the six-real chain selects all six real factories and compiles.

    @impl WON-005
    """
    specs = load_research_node_specs()
    modes = {name: "fake" for name in LOGICAL_NODES} | {
        "bootstrap": "real",
        "hitl1": "real",
        "topic_planning": "real",
        "wave0": "real",
        "targeted_evidence": "real",
        "wave1": "real",
    }
    resolved = resolve_implementations(specs, modes)
    for name in ("bootstrap", "hitl1", "topic_planning", "wave0", "targeted_evidence", "wave1"):
        assert resolved[name] is specs[name].real_factory, f"{name} should use real factory"
    for name in LOGICAL_NODES:
        if name not in {"bootstrap", "hitl1", "topic_planning", "wave0", "targeted_evidence", "wave1"}:
            assert resolved[name] is specs[name].fake_factory, f"{name} should use fake factory"
    build_research_graph(implementation_modes=modes).compile()


def test_mixed_real_wave1_chain_preserves_topology_shape() -> None:
    """Graph shape is identical for full-fake and mixed wave1-chain maps."""
    fake_graph = build_research_graph().compile()
    mixed_modes = {name: "fake" for name in LOGICAL_NODES} | {
        "bootstrap": "real",
        "hitl1": "real",
        "topic_planning": "real",
        "wave0": "real",
        "targeted_evidence": "real",
        "wave1": "real",
    }
    mixed_graph = build_research_graph(implementation_modes=mixed_modes).compile()
    assert {(e.source, e.target) for e in mixed_graph.get_graph().edges} == {
        (e.source, e.target) for e in fake_graph.get_graph().edges
    }


def test_mixed_real_wave2_chain_resolves_and_compiles() -> None:
    """Mixed mode with seven-real chain (through wave2) selects all real factories."""
    specs = load_research_node_specs()
    modes = {name: "fake" for name in LOGICAL_NODES} | {
        "bootstrap": "real",
        "hitl1": "real",
        "topic_planning": "real",
        "wave0": "real",
        "targeted_evidence": "real",
        "wave1": "real",
        "wave2_synthesis": "real",
    }
    resolved = resolve_implementations(specs, modes)
    expected = {"bootstrap", "hitl1", "topic_planning", "wave0", "targeted_evidence", "wave1", "wave2_synthesis"}
    for name in expected:
        assert resolved[name] is specs[name].real_factory
    build_research_graph(implementation_modes=modes).compile()


def test_mixed_real_wave0_chain_preserves_topology_shape() -> None:
    """Graph shape is identical for full-fake and mixed wave0-chain maps.

    @impl WAN-005
    """
    fake_graph = build_research_graph().compile()
    mixed_modes = {name: "fake" for name in LOGICAL_NODES} | {
        "bootstrap": "real",
        "hitl1": "real",
        "topic_planning": "real",
        "wave0": "real",
    }
    mixed_graph = build_research_graph(implementation_modes=mixed_modes).compile()
    assert {(e.source, e.target) for e in mixed_graph.get_graph().edges} == {
        (e.source, e.target) for e in fake_graph.get_graph().edges
    }
