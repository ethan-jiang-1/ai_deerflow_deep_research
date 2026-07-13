from deerflow_deep_research.domain.lifecycle import (
    MAX_FAKE_RERUN_GENERATIONS,
    LifecycleStatus,
    TerminalReason,
)
from deerflow_deep_research.domain.node_spec import NodeBuildDependencies
from deerflow_deep_research.domain.state import PhaseStatus
from deerflow_deep_research.engine.fake_control import node_update


def build_fake(_dependencies: NodeBuildDependencies):
    async def run(state):
        generation = int(state.get("generation", 0))
        if generation >= MAX_FAKE_RERUN_GENERATIONS:
            return node_update(
                "rerun",
                route="exhausted",
                terminal_status=LifecycleStatus.BLOCKED.value,
                phase_status=PhaseStatus.TERMINAL.value,
                terminal_reason=TerminalReason.RERUN_EXHAUSTED.value,
            )
        return node_update("rerun", route="next", generation=generation + 1, repair_counts={})

    return run
