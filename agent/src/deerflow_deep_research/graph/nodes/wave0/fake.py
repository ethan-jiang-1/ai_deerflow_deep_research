from deerflow_deep_research.domain.node_spec import NodeBuildDependencies
from deerflow_deep_research.engine.fake_control import attempt_id, bounded_repair_update, choose_fixture

from .subgraph import build_wave0_subgraph


def build_fake(_dependencies: NodeBuildDependencies):
    subgraph = build_wave0_subgraph()

    async def run(state):
        fan_in = await subgraph.ainvoke({"branch_prefix": attempt_id(state, "wave0"), "branch_results": ()})
        route = choose_fixture(state, "wave0")
        results = tuple(item.model_dump(mode="json") for item in fan_in["normalized_results"])
        return bounded_repair_update(state, "wave0", route) | {"wave0_results": results}

    return run
