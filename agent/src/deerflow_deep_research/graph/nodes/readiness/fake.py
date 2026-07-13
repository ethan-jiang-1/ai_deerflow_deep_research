from deerflow_deep_research.domain.node_spec import NodeBuildDependencies
from deerflow_deep_research.engine.fake_control import node_update


def build_fake(_dependencies: NodeBuildDependencies):
    async def run(state):
        return node_update("readiness")

    return run
