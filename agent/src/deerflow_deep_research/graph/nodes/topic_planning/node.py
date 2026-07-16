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
    MAX_TOPIC_TITLE_CHARS,
    MAX_TOPICS,
    MaterializedTopic,
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


def _synthesize_fallback_plan(coverage_questions: tuple[str, ...]) -> MaterializedTopics:
    """Return a minimal valid plan when the LLM can't produce parseable output."""
    if not coverage_questions:
        coverage_questions = ("Investigate the research question",)
    return MaterializedTopics(
        topics=tuple(
            MaterializedTopic(
                topic_id=f"t-{i:02d}",
                slug=f"topic-{i:02d}",
                title=q[: MAX_TOPIC_TITLE_CHARS] if len(q) > MAX_TOPIC_TITLE_CHARS else q,
                scope="Broad investigation using available sources",
                must_answer_bindings=(q,) if q else (),
            )
            for i, q in enumerate(coverage_questions[:MAX_TOPICS])
        ),
        coverage={},
    )


async def _generate_plan(
    inputs: PlannerInputs,
    *,
    run_agent,
    agent_context,
) -> MaterializedTopics:
    """Call the planner with retries; fall back to a synthesised plan on failure."""
    repair_error: str | None = None
    for _attempt in range(4):
        try:
            result = await run_agent(
                context=agent_context,
                request=build_planner_prompt(inputs, repair_error=repair_error),
            )
        except Exception:
            return _synthesize_fallback_plan(inputs.coverage_questions)
        if not isinstance(result, NodeExecutionResult) or result.finish_reason is not NodeFinishReason.SUCCESS:
            continue
        try:
            plan: TopicPlan = parse_plan_output(result.summary)
            return materialize_topic_plan(plan, inputs.coverage_questions)
        except (TypeError, ValueError) as exc:
            repair_error = type(exc).__name__
    return _synthesize_fallback_plan(inputs.coverage_questions)


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
