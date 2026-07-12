from deerflow_deep_research.domain.lifecycle import LifecycleStatus, TerminalReason
from deerflow_deep_research.domain.node_spec import NodeBuildDependencies
from deerflow_deep_research.engine.fake_control import bounded_repair_update, choose_fixture


def build_fake(_dependencies: NodeBuildDependencies):
    async def run(state):
        route = choose_fixture(state, "final_delivery")
        update = bounded_repair_update(state, "final_delivery", route)
        if update["route"] == "pass":
            update["terminal_fixture_marker"] = "full_fake_terminal_fixture"
            update["status"] = LifecycleStatus.COMPLETED.value
            update["terminal_reason"] = TerminalReason.COMPLETED.value
        return update

    return run
