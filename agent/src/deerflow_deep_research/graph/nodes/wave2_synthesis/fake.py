from deerflow_deep_research.domain.node_spec import NodeBuildDependencies
from deerflow_deep_research.engine.fake_control import choose_fixture, node_update


def build_fake(_dependencies: NodeBuildDependencies):
    async def run(state):
        return node_update("wave2_synthesis", route=choose_fixture(state, "wave2_synthesis"))

    return run
