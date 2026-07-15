"""Real topic planning node.

@impl TOP-001
@impl TOP-002
@impl TOP-003
@impl TOP-004
@impl TOP-005
"""

from __future__ import annotations

from deerflow_deep_research.domain.context import NodeExecutionResult
from deerflow_deep_research.domain.enums import NodeFinishReason
from deerflow_deep_research.domain.lifecycle import LifecycleStatus, TerminalReason
from deerflow_deep_research.domain.node_spec import NodeBuildDependencies
from deerflow_deep_research.domain.state import PhaseStatus
from deerflow_deep_research.domain.topics import (
    MaterializedTopics,
    TopicPlan,
    materialize_topic_plan,
    materialized_topics_state,
    parse_plan_output,
)
from deerflow_deep_research.engine.fake_control import node_update
from deerflow_deep_research.graph.nodes.topic_planning.prompts import (
    PlannerInputs,
    build_planner_prompt,
    planner_inputs_from_state,
)


def _exhausted_update() -> dict[str, object]:
    return node_update(
        "topic_planning",
        route="exhausted",
        terminal_status=LifecycleStatus.BLOCKED.value,
        phase_status=PhaseStatus.TERMINAL.value,
        terminal_reason=TerminalReason.GATE_BLOCKED.value,
    )


async def _generate_plan(
    inputs: PlannerInputs,
    *,
    run_agent,
    agent_context,
) -> MaterializedTopics | None:
    """Call the planner once, with at most one repair; return a materialized registry."""
    repair_error: str | None = None
    for _attempt in range(2):
        try:
            result = await run_agent(
                context=agent_context,
                request=build_planner_prompt(inputs, repair_error=repair_error),
            )
        except Exception:
            return None
        if not isinstance(result, NodeExecutionResult) or result.finish_reason is not NodeFinishReason.SUCCESS:
            return None
        try:
            plan: TopicPlan = parse_plan_output(result.summary)
            return materialize_topic_plan(plan, inputs.coverage_questions)
        except (TypeError, ValueError) as exc:
            repair_error = type(exc).__name__
    return None


def build_real(dependencies: NodeBuildDependencies):
    async def run(state):
        inputs = planner_inputs_from_state(state)
        materialized = await _generate_plan(
            inputs,
            run_agent=dependencies.capabilities.run_agent,
            agent_context=dependencies.agent_context,
        )
        if materialized is None:
            return _exhausted_update()
        return node_update("topic_planning", route="next", **materialized_topics_state(materialized))

    return run


__all__ = ["build_real"]
