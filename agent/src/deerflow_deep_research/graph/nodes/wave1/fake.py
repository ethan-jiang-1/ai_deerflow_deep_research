from deerflow_deep_research.domain.node_spec import NodeBuildDependencies
from deerflow_deep_research.engine.fake_control import attempt_id, node_update

from .subgraph import build_wave1_subgraph


def build_fake(_dependencies: NodeBuildDependencies):
    subgraph = build_wave1_subgraph()

    async def run(state):
        fan_in = await subgraph.ainvoke({"branch_prefix": attempt_id(state, "wave1"), "branch_results": ()})
        results = tuple(item.model_dump(mode="json") for item in fan_in["normalized_results"])
        return node_update("wave1", wave1_results=results)

    return run
