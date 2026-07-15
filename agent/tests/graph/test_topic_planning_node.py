"""Real topic planning node behavior.

@impl TOP-001
@impl TOP-002
@impl TOP-003
@impl TOP-004
"""

from __future__ import annotations

import json
from typing import Any

from deerflow_deep_research.domain.context import GraphContextView, NodeAgentContext, NodeExecutionResult
from deerflow_deep_research.domain.enums import NodeFinishReason
from deerflow_deep_research.domain.lifecycle import LifecycleStatus, TerminalReason
from deerflow_deep_research.domain.node_spec import NodeBuildDependencies
from deerflow_deep_research.domain.state import PhaseStatus
from deerflow_deep_research.graph.nodes.topic_planning import node as topic_planning_node

RESEARCH_ID = "r_" + "A" * 43


def _topic(title: str, scope: str, *bindings: str) -> dict[str, object]:
    return {
        "title": title,
        "scope": scope,
        "must_answer_bindings": list(bindings),
        "search_dimensions": [],
        "exclusions": [],
    }


def _plan_json(*topics: dict[str, object]) -> str:
    return json.dumps({"schema_version": 1, "topics": list(topics)})


def _state(**overrides: object) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": 2,
        "research_id": RESEARCH_ID,
        "outer_thread_id": "thread-1",
        "request_text": "Compare storage options",
        "research_depth": "deep_dive",
        "target_audience": "domain_expert",
        "output_format": "annotated_bibliography",
        "cost_tolerance": "extensive",
        "time_budget": "overnight",
        "must_answer_questions": ("Q1", "Q2"),
        "degraded_profile": False,
        "phase": "topic_planning",
        "generation": 0,
        "execution_trace": (),
    }
    payload.update(overrides)
    return payload


class _Caps:
    def __init__(self, *results: object) -> None:
        self._results = list(results)
        self.requests: list[object] = []

    async def run_agent(self, *, context: NodeAgentContext, request: object) -> NodeExecutionResult:
        self.requests.append(request)
        if not self._results:
            raise AssertionError("unexpected run_agent")
        result = self._results.pop(0)
        if isinstance(result, BaseException):
            raise result
        return result  # type: ignore[return-value]


def _result(summary: str, *, finish_reason: NodeFinishReason = NodeFinishReason.SUCCESS) -> NodeExecutionResult:
    return NodeExecutionResult(finish_reason=finish_reason, summary=summary)


def _deps(caps: _Caps) -> NodeBuildDependencies:
    graph = GraphContextView(
        research_scope_id=RESEARCH_ID,
        workspace_root=f"/mnt/user-data/workspace/deep-research/{RESEARCH_ID}",
        uploads_root="/mnt/user-data/uploads",
        outputs_root=f"/mnt/user-data/outputs/deep-research/{RESEARCH_ID}",
    )
    return NodeBuildDependencies(
        graph_context=graph,
        agent_context=NodeAgentContext(
            research_scope_id=RESEARCH_ID,
            node_name="topic_planning",
            attempt_id="g0-tp-a1",
            workspace_root=graph.workspace_root,
            attempt_root=f"{graph.workspace_root}/topic_planning",
            policy_name="topic-planning",
        ),
        capabilities=caps,
    )


def _covering_plan() -> str:
    return _plan_json(
        _topic("Batteries", "Grid battery economics", "Q1"),
        _topic("Solar", "Utility-scale solar economics", "Q2"),
    )


async def test_valid_plan_routes_next_and_records_registry() -> None:
    caps = _Caps(_result(_covering_plan()))
    result = await topic_planning_node.build_real(_deps(caps))(_state())
    assert result["route"] == "next"
    assert result["topic_refs"] == ("batteries", "solar")
    assert len(result["topic_registry"]) == 2
    assert result["topic_registry"][0]["topic_id"] == "batteries"
    assert len(caps.requests) == 1
    assert "deep_dive" in caps.requests[0].objective


async def test_invalid_plan_retries_once_then_records() -> None:
    caps = _Caps(_result("not-json"), _result(_covering_plan()))
    result = await topic_planning_node.build_real(_deps(caps))(_state())
    assert result["route"] == "next"
    assert result["topic_refs"] == ("batteries", "solar")
    assert len(caps.requests) == 2
    assert "previous plan failed validation" in caps.requests[1].objective.lower()


async def test_repeated_invalid_plan_exhausts_without_topic_state() -> None:
    caps = _Caps(_result("not-json"), _result('{"still":"invalid"}'))
    result = await topic_planning_node.build_real(_deps(caps))(_state())
    assert result["route"] == "exhausted"
    assert result["terminal_status"] == LifecycleStatus.BLOCKED.value
    assert result["terminal_reason"] == TerminalReason.GATE_BLOCKED.value
    assert result["phase_status"] == PhaseStatus.TERMINAL.value
    assert "topic_refs" not in result
    assert "topic_registry" not in result


async def test_uncovered_question_is_repaired_then_exhausts() -> None:
    # Only Q1 is covered on both attempts; Q2 stays uncovered.
    partial = _plan_json(_topic("Batteries", "Grid battery economics", "Q1"))
    caps = _Caps(_result(partial), _result(partial))
    result = await topic_planning_node.build_real(_deps(caps))(_state())
    assert result["route"] == "exhausted"
    assert "topic_registry" not in result


async def test_run_agent_failure_exhausts_without_topic_state() -> None:
    for failure in (
        RuntimeError("model unavailable"),
        _result("", finish_reason=NodeFinishReason.FAILED),
    ):
        result = await topic_planning_node.build_real(_deps(_Caps(failure)))(_state())
        assert result["route"] == "exhausted"
        assert "topic_refs" not in result
        assert "topic_registry" not in result


async def test_empty_must_answer_uses_request_text_for_coverage() -> None:
    plan = _plan_json(_topic("Storage options", "All storage options", "Compare storage options"))
    caps = _Caps(_result(plan))
    result = await topic_planning_node.build_real(_deps(caps))(_state(must_answer_questions=(), degraded_profile=True))
    assert result["route"] == "next"
    assert result["topic_refs"] == ("storage-options",)
