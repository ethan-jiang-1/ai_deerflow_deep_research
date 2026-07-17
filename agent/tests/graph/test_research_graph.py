"""Complete request-independent fake graph routes.

@impl REG-001
@impl REG-002
@impl REG-003
@impl REG-004
@impl RUO-004
"""

from __future__ import annotations

import asyncio
import time
from datetime import UTC, datetime
from pathlib import Path

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from deerflow_deep_research.domain.context import GraphContextView, NodeAgentContext
from deerflow_deep_research.domain.invocation import GraphInvocationContext, WorkUnitControllerDependencies
from deerflow_deep_research.domain.lifecycle import AcceptedHumanResponse, ResponseKind
from deerflow_deep_research.domain.node_spec import NodeBuildDependencies
from deerflow_deep_research.domain.state import FakeFixturePlan, fixture_plan_to_checkpoint
from deerflow_deep_research.graph.builder import build_research_graph
from deerflow_deep_research.runtime.projection import RuntimeWorkUnitDependencyResolver
from deerflow_deep_research.runtime.work_unit_store import WorkUnitStore

_WORKSPACE: Path | None = None


@pytest.fixture(autouse=True)
def _work_unit_workspace(tmp_path: Path):
    global _WORKSPACE
    _WORKSPACE = tmp_path
    yield
    _WORKSPACE = None


class ForbiddenCapabilities:
    async def run_agent(self, *, context, request):
        raise AssertionError("full fake graph cannot call an agent")


class Resolver:
    def __init__(self, graph_context: GraphContextView) -> None:
        self.graph_context = graph_context
        self.calls: list[tuple[str, str]] = []

    def resolve(self, *, logical_name, attempt_id, policy):
        self.calls.append((logical_name, attempt_id))
        return NodeBuildDependencies(
            graph_context=self.graph_context,
            agent_context=NodeAgentContext(
                research_scope_id=self.graph_context.research_scope_id,
                node_name=logical_name,
                attempt_id=attempt_id,
                workspace_root=self.graph_context.workspace_root,
                attempt_root=f"{self.graph_context.workspace_root}/{attempt_id}",
                policy_name=policy.name,
            ),
            capabilities=ForbiddenCapabilities(),
        )


def _context() -> tuple[GraphInvocationContext, Resolver]:
    graph = GraphContextView(
        research_scope_id="r_" + "A" * 43,
        workspace_root="/mnt/user-data/workspace/deep-research/r",
        uploads_root="/mnt/user-data/uploads",
        outputs_root="/mnt/user-data/outputs/deep-research/r",
    )
    resolver = Resolver(graph)
    assert _WORKSPACE is not None
    store = WorkUnitStore(
        workspace_host_path=_WORKSPACE,
        research_id=graph.research_scope_id,
        clock=lambda: datetime(2026, 7, 14, tzinfo=UTC),
        monotonic=time.monotonic,
        lock_sleep=time.sleep,
        token_factory=lambda: "2" * 32,
        fault_hook=None,
    )
    work_units = WorkUnitControllerDependencies(
        store=store,
        resolver=RuntimeWorkUnitDependencyResolver(graph, resolver, store),
    )
    return GraphInvocationContext(graph, resolver, work_units), resolver


def _initial(plan: FakeFixturePlan | None = None) -> dict:
    return {
        "schema_version": 2,
        "research_id": "r_" + "A" * 43,
        "start_message_id": "human-start",
        "request_digest": "d_" + "B" * 43,
        "request_text": "question",
        "fixture_plan": fixture_plan_to_checkpoint(plan or FakeFixturePlan()),
        "phase": "bootstrap",
        "generation": 0,
        "repair_counts": {},
        "wave0_results": (),
        "wave1_results": (),
        "consumed_request_ids": (),
        "consumed_message_ids": (),
        "execution_trace": (),
    }


def _pending(snapshot):
    return snapshot.tasks[0].interrupts[0].value


def _response(descriptor, message_id: str, value: str, *, option: bool = False) -> dict:
    return AcceptedHumanResponse(
        request_id=descriptor["request"]["request_id"],
        message_id=message_id,
        value=value,
        response_kind=ResponseKind.OPTION if option else ResponseKind.TEXT,
        option_id=value if option else None,
    ).model_dump(mode="json")


@pytest.mark.asyncio
async def test_happy_path_suspends_twice_and_completes_with_fresh_attempt_dependencies() -> None:
    """@impl RUO-004"""
    context, resolver = _context()
    graph = build_research_graph().compile(checkpointer=InMemorySaver())
    config = {"configurable": {"thread_id": "happy"}}

    await graph.ainvoke(_initial(), config=config, context=context)
    first = await graph.aget_state(config)
    assert _pending(first)["phase"] == "hitl1"
    await graph.ainvoke(
        Command(resume=_response(_pending(first), "human-1", "profile")),
        config=config,
        context=context,
    )
    second = await graph.aget_state(config)
    assert _pending(second)["phase"] == "hitl2"
    result = await graph.ainvoke(
        Command(resume=_response(_pending(second), "human-2", "proceed", option=True)),
        config=config,
        context=context,
    )
    assert result["terminal_status"] == "completed"
    assert result["terminal_fixture_marker"] == "full_fake_terminal_fixture"
    assert result["execution_trace"] == (
        "bootstrap",
        "hitl1",
        "topic_planning",
        "wave0",
        "wave1",
        "wave2_synthesis",
        "hitl2",
        "readiness",
        "final_delivery",
    )
    hitl_calls = [(name, attempt) for name, attempt in resolver.calls if name in {"hitl1", "hitl2"}]
    assert hitl_calls == [
        ("hitl1", "g0-hitl1-a1"),
        ("hitl1", "g0-hitl1-a1"),
        ("hitl2", "g0-hitl2-a1"),
        ("hitl2", "g0-hitl2-a1"),
    ]
    assert _WORKSPACE is not None
    files = await asyncio.to_thread(
        lambda: {path.relative_to(_WORKSPACE).as_posix() for path in _WORKSPACE.rglob("*") if path.is_file()}
    )
    assert any(path.endswith("/evidence/submissions.jsonl") for path in files)
    assert any(path.endswith("/evidence/.submissions.lock") for path in files)
    assert all(
        path.endswith(("/work-spec.json", "/result.json", "/outputs/fixture.json"))
        or path.endswith(("/evidence/submissions.jsonl", "/evidence/.submissions.lock"))
        for path in files
    )
    assert not any(
        f"/{subtree}/" in path for path in files for subtree in ("cache", "synthesis", "review", "final", "diagnostics")
    )


@pytest.mark.asyncio
async def test_profile_bypass_and_repair_routes_are_explicit() -> None:
    context, _ = _context()
    plan = FakeFixturePlan(
        bootstrap=("profile_complete",),
        wave0=("repair", "pass"),
        wave1=("repair", "pass"),
        wave2_synthesis=("evidence_needed", "pass"),
    )
    graph = build_research_graph().compile(checkpointer=InMemorySaver())
    config = {"configurable": {"thread_id": "repairs"}}
    await graph.ainvoke(_initial(plan), config=config, context=context)
    state = await graph.aget_state(config)
    trace = state.values["execution_trace"]
    assert "hitl1" not in trace
    assert trace.count("wave0") == 2
    assert trace.count("wave1") == 2
    assert trace.count("wave2_synthesis") == 2
    assert trace.count("targeted_evidence") == 1
    wave0_attempts = [attempt for name, attempt in context.dependency_resolver.calls if name == "wave0"]
    assert [attempt for attempt in wave0_attempts if "_w" not in attempt] == ["g0-wave0-a1", "g0-wave0-a2"]
    assert set(attempt for attempt in wave0_attempts if "_w" in attempt) == {
        "g0_wave0_w0000_a00",
        "g0_wave0_w0001_a00",
        "g0_wave0_w0002_a00",
        "g0_wave0_w0003_a00",
        "g0_wave0_w0004_a00",
        "g0_wave0_w0005_a00",
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("decision", "expected_phase"),
    [("revise_view", "hitl2"), ("repair", "hitl2"), ("rerun", "hitl2"), ("stop", None)],
)
async def test_every_hitl2_decision_uses_declared_route(decision: str, expected_phase: str | None) -> None:
    context, _ = _context()
    graph = build_research_graph().compile(checkpointer=InMemorySaver())
    config = {"configurable": {"thread_id": f"decision-{decision}"}}
    await graph.ainvoke(_initial(FakeFixturePlan(bootstrap=("profile_complete",))), config=config, context=context)
    snapshot = await graph.aget_state(config)
    result = await graph.ainvoke(
        Command(resume=_response(_pending(snapshot), "human-decision", decision, option=True)),
        config=config,
        context=context,
    )
    if decision == "stop":
        assert result["terminal_status"] == "stopped"
        return
    next_snapshot = await graph.aget_state(config)
    assert _pending(next_snapshot)["phase"] == expected_phase
    if decision == "rerun":
        assert next_snapshot.values["generation"] == 1


@pytest.mark.asyncio
async def test_readiness_and_final_repairs_converge_before_completion() -> None:
    context, _ = _context()
    plan = FakeFixturePlan(
        bootstrap=("profile_complete",),
        readiness=("repair_synthesis", "repair_hitl2", "pass"),
        final_delivery=("repair", "evidence_blocked", "pass"),
    )
    graph = build_research_graph().compile(checkpointer=InMemorySaver())
    config = {"configurable": {"thread_id": "late-repairs"}}
    await graph.ainvoke(_initial(plan), config=config, context=context)
    for index in range(3):
        snapshot = await graph.aget_state(config)
        await graph.ainvoke(
            Command(resume=_response(_pending(snapshot), f"human-{index}", "proceed", option=True)),
            config=config,
            context=context,
        )
    result = (await graph.aget_state(config)).values
    assert result["terminal_status"] == "completed"
    assert result["execution_trace"].count("readiness") >= 3
    assert result["execution_trace"].count("final_delivery") == 3


@pytest.mark.asyncio
async def test_readiness_targeted_repair_returns_through_synthesis_and_hitl2() -> None:
    context, _ = _context()
    plan = FakeFixturePlan(
        bootstrap=("profile_complete",),
        readiness=("repair_targeted", "pass"),
    )
    graph = build_research_graph().compile(checkpointer=InMemorySaver())
    config = {"configurable": {"thread_id": "readiness-targeted"}}
    await graph.ainvoke(_initial(plan), config=config, context=context)

    first = await graph.aget_state(config)
    await graph.ainvoke(
        Command(resume=_response(_pending(first), "human-1", "proceed", option=True)),
        config=config,
        context=context,
    )
    second = await graph.aget_state(config)
    assert _pending(second)["phase"] == "hitl2"
    assert second.values["execution_trace"].count("targeted_evidence") == 1
    assert second.values["execution_trace"].count("wave2_synthesis") == 2

    result = await graph.ainvoke(
        Command(resume=_response(_pending(second), "human-2", "proceed", option=True)),
        config=config,
        context=context,
    )
    assert result["terminal_status"] == "completed"
