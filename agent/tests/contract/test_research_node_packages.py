"""Canonical change-01 node package surfaces (REG-001/002/004).

@impl GAK-005 — gate evaluation replaces direct fixture-outcome routing
"""

from __future__ import annotations

import importlib

import pytest

from deerflow_deep_research.domain.context import GraphContextView, NodeAgentContext
from deerflow_deep_research.domain.node_spec import UNAVAILABLE_REAL_FACTORY, NodeBuildDependencies
from deerflow_deep_research.domain.state import FakeFixturePlan, fixture_plan_to_checkpoint
from deerflow_deep_research.engine.gate_fixtures import build_fixture_gate_defs
from deerflow_deep_research.engine.gate_kernel import evaluate_gate
from deerflow_deep_research.graph.registry import NodeRegistry
from deerflow_deep_research.graph.topology import LOGICAL_NODES

PACKAGE_PREFIX = "deerflow_deep_research.graph.nodes"
IMPLEMENTED_PACKAGES = LOGICAL_NODES
NON_HITL_PACKAGES = tuple(name for name in LOGICAL_NODES if name not in {"hitl1", "hitl2"})


class ForbiddenCapabilities:
    async def run_agent(self, *, context, request):
        raise AssertionError("full-fake nodes must not invoke agent capability")


def _dependencies(name: str) -> NodeBuildDependencies:
    graph = GraphContextView(
        research_scope_id="r_" + "A" * 43,
        workspace_root="/mnt/user-data/workspace/deep-research/r",
        uploads_root="/mnt/user-data/uploads",
        outputs_root="/mnt/user-data/outputs/deep-research/r",
    )
    return NodeBuildDependencies(
        graph_context=graph,
        agent_context=NodeAgentContext(
            research_scope_id=graph.research_scope_id,
            node_name=name,
            attempt_id=f"g0-{name}-a1",
            workspace_root=graph.workspace_root,
            attempt_root=f"{graph.workspace_root}/{name}",
            policy_name="skeleton",
        ),
        capabilities=ForbiddenCapabilities(),
    )


def _state(plan: FakeFixturePlan | None = None) -> dict:
    return {
        "generation": 0,
        "fixture_plan": plan or FakeFixturePlan(),
        "execution_trace": (),
        "repair_counts": {},
    }


def test_explicit_registry_loads_package_root_only_specs() -> None:
    package_names = tuple(f"{PACKAGE_PREFIX}.{name}" for name in IMPLEMENTED_PACKAGES)
    specs = NodeRegistry(package_prefix=PACKAGE_PREFIX, package_names=package_names).load()
    assert tuple(specs) == IMPLEMENTED_PACKAGES
    for name, spec in specs.items():
        package = importlib.import_module(f"{PACKAGE_PREFIX}.{name}")
        assert package.__all__ == ["NODE_SPEC"]
        assert spec.real_factory is UNAVAILABLE_REAL_FACTORY
        assert spec.logical_name == name


@pytest.mark.asyncio
async def test_deterministic_fake_nodes_follow_typed_fixture_routes_without_capabilities() -> None:
    specs = NodeRegistry(
        package_prefix=PACKAGE_PREFIX,
        package_names=tuple(f"{PACKAGE_PREFIX}.{name}" for name in IMPLEMENTED_PACKAGES),
    ).load()
    for name in NON_HITL_PACKAGES:
        node = specs[name].fake_factory(_dependencies(name))
        result = await node(_state())
        assert result["phase"] == name
        assert result["execution_trace"] == (name,)


@pytest.mark.asyncio
async def test_repair_rerun_and_fake_final_are_bounded_and_content_free() -> None:
    specs = NodeRegistry(
        package_prefix=PACKAGE_PREFIX,
        package_names=tuple(f"{PACKAGE_PREFIX}.{name}" for name in IMPLEMENTED_PACKAGES),
    ).load()

    # Wave node returns work result only; gate evaluation adds routing.
    gate_defs = build_fixture_gate_defs()
    wave = specs["wave0"].fake_factory(_dependencies("wave0"))
    plan = FakeFixturePlan(wave0=("repair", "pass"))
    # The checkpoint stores fixture_plan as a dict of string tuples
    wave_state = _state(plan) | {"fixture_plan": fixture_plan_to_checkpoint(plan)}
    wave_result = await wave(wave_state)
    # Node does NOT write route — gate does
    assert "route" not in wave_result
    assert "repair_counts" not in wave_result
    # Gate evaluation on the same state produces the expected route
    gate_result = evaluate_gate(wave_state, "wave0", gate_defs["wave0"])
    assert gate_result.verdict.value == "repair"
    assert gate_result.attempt == 1
    assert gate_result.route == "repair"

    rerun = specs["rerun"].fake_factory(_dependencies("rerun"))
    assert (await rerun(_state()))["generation"] == 1
    exhausted = _state() | {"generation": 2}
    assert (await rerun(exhausted))["route"] == "exhausted"

    final = specs["final_delivery"].fake_factory(_dependencies("final_delivery"))
    final_result = await final(_state())
    assert final_result["terminal_fixture_marker"] == "full_fake_terminal_fixture"
    assert not ({"finding", "evidence", "citation", "report"} & set(final_result))
