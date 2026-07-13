"""Graph-owned HITL interrupt contracts (REG-003/004)."""

from __future__ import annotations

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command

from deerflow_deep_research.domain.context import GraphContextView, NodeAgentContext
from deerflow_deep_research.domain.lifecycle import (
    AcceptedHumanResponse,
    DeepResearchControlResult,
    PendingResearchInterrupt,
    ResponseKind,
)
from deerflow_deep_research.domain.node_spec import NodeBuildDependencies
from deerflow_deep_research.domain.state import FakeFixturePlan, ResearchState, fixture_plan_to_checkpoint
from deerflow_deep_research.graph.nodes.hitl1 import NODE_SPEC as HITL1_SPEC
from deerflow_deep_research.graph.nodes.hitl2 import NODE_SPEC as HITL2_SPEC
from deerflow_deep_research.runtime.human_input import HumanInputError, project_suspension


class ForbiddenCapabilities:
    async def run_agent(self, *, context, request):
        raise AssertionError("HITL fake must not invoke agent capability")


def _dependencies(name: str) -> NodeBuildDependencies:
    graph = GraphContextView(
        research_scope_id="r_" + "A" * 43,
        workspace_root="/mnt/user-data/workspace/deep-research/r",
        uploads_root="/mnt/user-data/uploads",
        outputs_root="/mnt/user-data/outputs/deep-research/r",
    )
    return NodeBuildDependencies(
        graph_context=graph,
        agent_context=NodeAgentContext(
            research_scope_id=graph.research_scope_id,
            node_name=name,
            attempt_id=f"g0-{name}-a1",
            workspace_root=graph.workspace_root,
            attempt_root=f"{graph.workspace_root}/{name}",
            policy_name="skeleton",
        ),
        capabilities=ForbiddenCapabilities(),
    )


def _initial() -> dict:
    return {
        "schema_version": 2,
        "research_id": "r_" + "A" * 43,
        "start_message_id": "human-start",
        "request_digest": "d_" + "B" * 43,
        "request_text": "question",
        "fixture_plan": fixture_plan_to_checkpoint(FakeFixturePlan()),
        "phase": "bootstrap",
        "generation": 0,
        "repair_counts": {},
        "wave0_results": (),
        "wave1_results": (),
        "consumed_request_ids": (),
        "consumed_message_ids": (),
        "execution_trace": (),
    }


def _graph(spec):
    builder = StateGraph(ResearchState)
    builder.add_node(spec.logical_name, spec.fake_factory(_dependencies(spec.logical_name)))
    builder.add_edge(START, spec.logical_name)
    builder.add_edge(spec.logical_name, END)
    return builder.compile(checkpointer=InMemorySaver())


@pytest.mark.asyncio
async def test_hitl1_interrupt_is_checkpointed_and_resume_records_consumption() -> None:
    graph = _graph(HITL1_SPEC)
    config = {"configurable": {"thread_id": "hitl1-test"}}
    await graph.ainvoke(_initial(), config=config)
    snapshot = await graph.aget_state(config)
    assert len(snapshot.tasks) == 1
    assert len(snapshot.tasks[0].interrupts) == 1
    descriptor = snapshot.tasks[0].interrupts[0].value
    request = descriptor["request"]
    assert request["source"] == "deep_research"
    assert request["mode"] == "text"
    assert "full_fake" in request["title"]
    assert descriptor["suspension_cursor"] == "human-start"

    response = AcceptedHumanResponse(
        request_id=request["request_id"],
        message_id="human-response-1",
        value="scope answer",
        response_kind=ResponseKind.TEXT,
    )
    result = await graph.ainvoke(Command(resume=response.model_dump(mode="json")), config=config)
    assert result["consumed_request_ids"] == (request["request_id"],)
    assert result["consumed_message_ids"] == ("human-response-1",)
    assert result["execution_trace"] == ("hitl1",)


@pytest.mark.asyncio
async def test_hitl2_request_ids_are_stable_for_retry_and_distinct_for_later_visit() -> None:
    graph = _graph(HITL2_SPEC)
    config = {"configurable": {"thread_id": "hitl2-test"}}
    initial = _initial() | {"execution_trace": ("hitl2",), "consumed_message_ids": ("human-response-1",)}
    await graph.ainvoke(initial, config=config)
    snapshot = await graph.aget_state(config)
    descriptor = snapshot.tasks[0].interrupts[0].value
    request = descriptor["request"]
    assert descriptor["suspension_cursor"] == "human-response-1"
    assert [option["id"] for option in request["options"]] == [
        "proceed",
        "revise_view",
        "repair",
        "rerun",
        "stop",
    ]
    first_id = request["request_id"]
    assert first_id == snapshot.tasks[0].interrupts[0].value["request"]["request_id"]

    another = _graph(HITL2_SPEC)
    other_config = {"configurable": {"thread_id": "hitl2-later"}}
    await another.ainvoke(initial | {"execution_trace": ("hitl2", "hitl2")}, config=other_config)
    later_id = (await another.aget_state(other_config)).tasks[0].interrupts[0].value["request"]["request_id"]
    assert later_id != first_id


@pytest.mark.asyncio
async def test_projector_failure_after_interrupt_commit_does_not_rerun_node() -> None:
    graph = _graph(HITL1_SPEC)
    config = {"configurable": {"thread_id": "projection-fault"}}
    await graph.ainvoke(_initial(), config=config)
    before = await graph.aget_state(config)
    pending = PendingResearchInterrupt.model_validate(_pending_value := before.tasks[0].interrupts[0].value)
    bad = DeepResearchControlResult(
        action="start",
        code="suspended",
        durability="same_process",
        research_id="r_" + "A" * 43,
        status="suspended",
        phase="hitl1",
        generation=0,
        request_id="drh_wrong",
    )
    with pytest.raises(HumanInputError, match="checkpoint_inconsistent"):
        project_suspension(pending=pending, result=bad, tool_call_id="failed-call")
    after = await graph.aget_state(config)
    assert not after.values["execution_trace"]
    assert after.tasks[0].interrupts[0].value == _pending_value

    good = bad.model_copy(update={"request_id": pending.request.request_id})
    command = project_suspension(pending=pending, result=good, tool_call_id="retry-call")
    assert command.update["messages"][0].tool_call_id == "retry-call"
    assert command.update["messages"][0].id == pending.request.request_id
