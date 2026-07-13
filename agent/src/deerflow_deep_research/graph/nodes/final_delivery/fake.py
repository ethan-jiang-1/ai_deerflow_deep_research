from deerflow_deep_research.domain.lifecycle import LifecycleStatus, TerminalReason
from deerflow_deep_research.domain.node_spec import NodeBuildDependencies
from deerflow_deep_research.domain.state import PhaseStatus
from deerflow_deep_research.engine.fake_control import node_update


def build_fake(_dependencies: NodeBuildDependencies):
    async def run(state):
        # Node sets terminal-completed fields optimistically.
        # If the gate returns BLOCKED, gate_update overwrites these.
        return node_update(
            "final_delivery",
            terminal_fixture_marker="full_fake_terminal_fixture",
            terminal_status=LifecycleStatus.COMPLETED.value,
            phase_status=PhaseStatus.TERMINAL.value,
            terminal_reason=TerminalReason.COMPLETED.value,
        )

    return run
