from deerflow_deep_research.domain.node_spec import NodeBuildDependencies
from deerflow_deep_research.domain.work_units import WORK_UNIT_GATE_VIEW_KEY, WorkUnitGateView
from deerflow_deep_research.engine.fake_control import node_update


def build_fake(_dependencies: NodeBuildDependencies):
    async def run(state):
        gate_view = WorkUnitGateView(
            drained=True,
            planned_work_ids=(),
            terminal_attempt_by_work_id={},
            accepted_record_by_work_id={},
            failure_summaries=(),
        )
        return {**node_update("targeted_evidence", route="next"), WORK_UNIT_GATE_VIEW_KEY: gate_view}

    return run
