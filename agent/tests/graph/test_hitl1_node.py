"""Real HITL1 node behavior.

@impl HIN-001
@impl HIN-002
@impl HIN-003
@impl HIN-004
@impl HIN-005
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from deerflow_deep_research.domain.context import GraphContextView, NodeAgentContext, NodeExecutionResult
from deerflow_deep_research.domain.enums import NodeFinishReason
from deerflow_deep_research.domain.lifecycle import (
    AcceptedHumanResponse,
    InternalCancelDecision,
    LifecycleStatus,
    ResponseKind,
    TerminalReason,
)
from deerflow_deep_research.domain.node_spec import NodeBuildDependencies
from deerflow_deep_research.domain.profile import ResearchProfile
from deerflow_deep_research.domain.state import ContentRef, PhaseStatus
from deerflow_deep_research.graph.nodes.hitl1 import node as hitl1_node

RESEARCH_ID = "r_" + "A" * 43


def _brief_json(**overrides: object) -> str:
    payload: dict[str, object] = {
        "schema_version": 1,
        "brief_summary": "A structured research intake brief.",
        "depth": "standard",
        "audience": "practitioner",
        "format": "detailed_report",
        "cost_tolerance": "moderate",
        "time_budget": "standard",
        "must_answer": ["Q1"],
        "scope_boundaries": "Scope",
        "custom_notes": "",
    }
    payload.update(overrides)
    return json.dumps(payload)


def _state(**overrides: object) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": 2,
        "research_id": RESEARCH_ID,
        "outer_thread_id": "thread-1",
        "start_message_id": "human-start",
        "request_digest": "d_" + "B" * 43,
        "request_text": "Compare storage options",
        "phase": "hitl1",
        "generation": 0,
        "consumed_request_ids": (),
        "consumed_message_ids": (),
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


class _RequestStore:
    def __init__(self) -> None:
        self.writes: list[ResearchProfile] = []

    async def write_profile(self, profile: ResearchProfile) -> ContentRef:
        self.writes.append(profile)
        return ContentRef(
            sandbox_path=f"workspace/deep-research/{RESEARCH_ID}/request/profile.json",
            content_hash="h_" + "A" * 43,
        )


def _result(summary: str, *, finish_reason: NodeFinishReason = NodeFinishReason.SUCCESS) -> NodeExecutionResult:
    return NodeExecutionResult(finish_reason=finish_reason, summary=summary)


def _deps(caps: _Caps, store: _RequestStore | None = None) -> NodeBuildDependencies:
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
            node_name="hitl1",
            attempt_id="g0-hitl1-a1",
            workspace_root=graph.workspace_root,
            attempt_root=f"{graph.workspace_root}/hitl1",
            policy_name="hitl1-profile",
        ),
        capabilities=caps,
        request_bundle=store or _RequestStore(),
    )


def _accepted(request_id: str, value: str, message_id: str = "human-1") -> dict[str, Any]:
    return AcceptedHumanResponse(
        request_id=request_id,
        message_id=message_id,
        value=value,
        response_kind=ResponseKind.TEXT,
    ).model_dump(mode="json")


def _complete_response() -> str:
    return json.dumps(
        {
            "depth": "deep_dive",
            "audience": "domain_expert",
            "format": "annotated_bibliography",
            "cost_tolerance": "extensive",
            "time_budget": "overnight",
            "must_answer": ["Q1", "Q2"],
        }
    )


async def test_first_visit_generates_brief_and_interrupts(monkeypatch: pytest.MonkeyPatch) -> None:
    caps = _Caps(_result(_brief_json()))
    store = _RequestStore()
    seen: list[dict[str, Any]] = []

    def fake_interrupt(value: dict[str, Any]) -> None:
        seen.append(value)
        raise RuntimeError("interrupt")

    monkeypatch.setattr(hitl1_node, "interrupt", fake_interrupt)
    run = hitl1_node.build_real(_deps(caps, store))
    with pytest.raises(RuntimeError, match="interrupt"):
        await run(_state())

    assert len(caps.requests) == 1
    assert "Compare storage options" in caps.requests[0].objective
    assert seen[0]["phase"] == "hitl1"
    assert seen[0]["request"]["mode"] == "text"
    assert json.loads(seen[0]["request"]["context"])["brief_summary"] == "A structured research intake brief."
    assert store.writes == []


async def test_first_visit_retries_once_on_invalid_brief(monkeypatch: pytest.MonkeyPatch) -> None:
    caps = _Caps(_result('{"missing":true}'), _result(_brief_json()))
    seen: list[dict[str, Any]] = []

    def fake_interrupt(value: dict[str, Any]) -> None:
        seen.append(value)
        raise RuntimeError("interrupt")

    monkeypatch.setattr(hitl1_node, "interrupt", fake_interrupt)
    with pytest.raises(RuntimeError, match="interrupt"):
        await hitl1_node.build_real(_deps(caps))(_state())
    assert len(caps.requests) == 2
    assert "Previous output failed validation" in caps.requests[1].objective
    assert seen


async def test_complete_response_writes_profile_and_routes_accepted(monkeypatch: pytest.MonkeyPatch) -> None:
    caps = _Caps(_result(_brief_json()))
    store = _RequestStore()

    def fake_interrupt(value: dict[str, Any]) -> dict[str, Any]:
        return _accepted(value["request"]["request_id"], _complete_response())

    monkeypatch.setattr(hitl1_node, "interrupt", fake_interrupt)
    result = await hitl1_node.build_real(_deps(caps, store))(_state())

    assert result["route"] == "accepted"
    assert result["profile_ref"].sandbox_path.endswith("/request/profile.json")
    assert result["research_depth"] == "deep_dive"
    assert result["target_audience"] == "domain_expert"
    assert result["output_format"] == "annotated_bibliography"
    assert result["cost_tolerance"] == "extensive"
    assert result["time_budget"] == "overnight"
    assert result["must_answer_questions"] == ("Q1", "Q2")
    assert result["pending_profile"] is None
    assert result["profile_followup_round"] == 0
    assert result["consumed_message_ids"] == ("human-1",)
    assert store.writes[0].depth == "deep_dive"


async def test_cancel_routes_without_profile_write(monkeypatch: pytest.MonkeyPatch) -> None:
    caps = _Caps(_result(_brief_json()))
    store = _RequestStore()
    monkeypatch.setattr(
        hitl1_node,
        "interrupt",
        lambda _value: InternalCancelDecision().model_dump(mode="json"),
    )
    result = await hitl1_node.build_real(_deps(caps, store))(_state(pending_profile={"depth": "standard"}))
    assert result["route"] == "cancel"
    assert result["terminal_status"] == LifecycleStatus.CANCELLED.value
    assert result["terminal_reason"] == TerminalReason.USER_CANCELLED.value
    assert result["phase_status"] == PhaseStatus.TERMINAL.value
    assert result["pending_profile"] is None
    assert store.writes == []


async def test_response_mismatch_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(hitl1_node, "interrupt", lambda _value: _accepted("wrong", _complete_response()))
    with pytest.raises(ValueError, match="response_mismatch"):
        await hitl1_node.build_real(_deps(_Caps(_result(_brief_json()))))(_state())


async def test_incomplete_response_checkpoints_followup_and_next_visit_asks_missing_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    caps = _Caps(_result(_brief_json()))
    monkeypatch.setattr(
        hitl1_node,
        "interrupt",
        lambda value: _accepted(value["request"]["request_id"], '{"depth":"quick_overview","audience":"layperson"}'),
    )
    first = await hitl1_node.build_real(_deps(caps))(_state())
    assert first["route"] == "needs_followup"
    assert first["profile_followup_round"] == 1
    assert first["pending_profile"]["depth"] == "quick_overview"
    assert first["consumed_message_ids"] == ("human-1",)

    seen: list[dict[str, Any]] = []

    def followup_interrupt(value: dict[str, Any]) -> None:
        seen.append(value)
        raise RuntimeError("interrupt")

    monkeypatch.setattr(hitl1_node, "interrupt", followup_interrupt)
    followup_state = _state(
        pending_profile=first["pending_profile"],
        profile_followup_round=first["profile_followup_round"],
        consumed_request_ids=first["consumed_request_ids"],
        consumed_message_ids=first["consumed_message_ids"],
        execution_trace=("hitl1",),
    )
    with pytest.raises(RuntimeError, match="interrupt"):
        await hitl1_node.build_real(_deps(_Caps()))(followup_state)
    context = json.loads(seen[0]["request"]["context"])
    assert context["missing_dimensions"] == ["format", "cost_tolerance", "time_budget", "must_answer"]
    assert seen[0]["suspension_cursor"] == "human-1"


async def test_followup_response_merges_checkpointed_progress(monkeypatch: pytest.MonkeyPatch) -> None:
    store = _RequestStore()

    def fake_interrupt(value: dict[str, Any]) -> dict[str, Any]:
        return _accepted(
            value["request"]["request_id"],
            '{"format":"faq","cost_tolerance":"minimal","time_budget":"very_quick","must_answer":["Q2"]}',
            "human-2",
        )

    monkeypatch.setattr(hitl1_node, "interrupt", fake_interrupt)
    result = await hitl1_node.build_real(_deps(_Caps(), store))(
        _state(
            pending_profile={"depth": "quick_overview", "audience": "layperson"},
            profile_followup_round=1,
            execution_trace=("hitl1",),
        )
    )
    assert result["route"] == "accepted"
    assert result["research_depth"] == "quick_overview"
    assert result["target_audience"] == "layperson"
    assert result["output_format"] == "faq"
    assert result["consumed_message_ids"] == ("human-2",)
    assert store.writes[0].audience == "layperson"


async def test_third_incomplete_answer_records_degraded_profile(monkeypatch: pytest.MonkeyPatch) -> None:
    store = _RequestStore()
    monkeypatch.setattr(
        hitl1_node,
        "interrupt",
        lambda value: _accepted(value["request"]["request_id"], '{"depth":"superficial"}', "human-3"),
    )
    result = await hitl1_node.build_real(_deps(_Caps(), store))(
        _state(
            pending_profile={"depth": "standard"},
            profile_followup_round=2,
            execution_trace=("hitl1", "hitl1"),
        )
    )
    assert result["route"] == "accepted"
    assert result["degraded_profile"] is True
    assert result["pending_profile"] is None
    assert store.writes[0].degraded_profile is True


async def test_brief_failure_exhausts_without_interrupt_or_profile_write(monkeypatch: pytest.MonkeyPatch) -> None:
    caps = _Caps(_result("not-json"), _result('{"still":"invalid"}'))
    store = _RequestStore()
    monkeypatch.setattr(hitl1_node, "interrupt", lambda _value: (_ for _ in ()).throw(AssertionError("no interrupt")))
    result = await hitl1_node.build_real(_deps(caps, store))(_state())
    assert result["route"] == "exhausted"
    assert result["terminal_status"] == LifecycleStatus.BLOCKED.value
    assert result["terminal_reason"] == TerminalReason.GATE_BLOCKED.value
    assert store.writes == []


async def test_run_agent_failure_exhausts_without_partial_state(monkeypatch: pytest.MonkeyPatch) -> None:
    for failure in (
        RuntimeError("model unavailable"),
        _result("", finish_reason=NodeFinishReason.FAILED),
    ):
        caps = _Caps(failure)
        monkeypatch.setattr(
            hitl1_node,
            "interrupt",
            lambda _value: (_ for _ in ()).throw(AssertionError("no interrupt")),
        )
        result = await hitl1_node.build_real(_deps(caps))(_state())
        assert result["route"] == "exhausted"
        assert "pending_profile" not in result
        assert "profile_ref" not in result
