from deerflow_deep_research.domain.node_spec import NodeBuildDependencies
from deerflow_deep_research.engine.fake_control import bounded_repair_update, choose_fixture


def build_fake(_dependencies: NodeBuildDependencies):
    async def run(state):
        route = choose_fixture(state, "readiness")
        return bounded_repair_update(state, "readiness", route)

    return run
