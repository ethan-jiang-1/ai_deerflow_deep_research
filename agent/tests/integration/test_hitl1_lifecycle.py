"""Mixed real-bootstrap/real-HITL1 lifecycle coverage.

@impl HIN-001
@impl HIN-002
@impl HIN-003
@impl HIN-004
@impl HIN-005
@impl REG-005
"""

from __future__ import annotations

import json
import secrets
import time
from datetime import UTC, datetime
from pathlib import Path

import pytest
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from deerflow_deep_research.domain.bootstrap import BootstrapMarker
from deerflow_deep_research.domain.context import NodeAgentContext, NodeExecutionRequest, NodeExecutionResult
from deerflow_deep_research.domain.enums import NodeFinishReason
from deerflow_deep_research.domain.lifecycle import (
    LifecycleAction,
    ResponseKind,
)
from deerflow_deep_research.graph.topology import LOGICAL_NODES
from deerflow_deep_research.runtime.bootstrap_bundle import BootstrapBundleStore
from deerflow_deep_research.runtime.human_input import SelectedStartMessage
from deerflow_deep_research.runtime.request_bundle import RequestBundleStore
from deerflow_deep_research.runtime.research import (
    ResearchActionInput,
    ResearchGraphRecipe,
    ResumeResearchHandler,
    StartResearchHandler,
    derive_research_id,
)
from deerflow_deep_research.runtime.runtime_adapter import TrustedRuntimeEnvelope
from deerflow_deep_research.runtime.work_unit_store import WorkUnitStore

_FULL_FAKE = {name: "fake" for name in LOGICAL_NODES}
_MIXED_HITL1 = _FULL_FAKE | {"bootstrap": "real", "hitl1": "real"}


class FakeAppConfig:
    checkpointer = None
    database = None


class _Sandbox:
    id = "sandbox-1"
    sandbox_id = "sandbox-1"


class _ReplayBridge:
    def __init__(self, summaries: list[object]) -> None:
        self._summaries = summaries
        self.calls: list[NodeExecutionRequest] = []

    async def run_agent(
        self,
        *,
        context: NodeAgentContext,
        request: NodeExecutionRequest,
    ) -> NodeExecutionResult:
        self.calls.append(request)
        if not self._summaries:
            raise AssertionError("unexpected bridge invocation")
        item = self._summaries.pop(0)
        if isinstance(item, BaseException):
            raise item
        if isinstance(item, NodeExecutionResult):
            return item
        return NodeExecutionResult(finish_reason=NodeFinishReason.SUCCESS, summary=str(item))


class _BridgeFactory:
    def __init__(self, *summaries: object) -> None:
        self.summaries = list(summaries)
        self.bridges: list[_ReplayBridge] = []

    def __call__(self, **_kwargs: object) -> _ReplayBridge:
        bridge = _ReplayBridge(self.summaries)
        self.bridges.append(bridge)
        return bridge

    @property
    def calls(self) -> list[NodeExecutionRequest]:
        return [request for bridge in self.bridges for request in bridge.calls]


def _brief_json(**overrides: object) -> str:
    payload: dict[str, object] = {
        "schema_version": 1,
        "brief_summary": "A structured profile brief.",
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


def _envelope(tmp_path: Path, *, thread: str = "thread-1") -> TrustedRuntimeEnvelope:
    workspace = tmp_path / "alice" / thread / "workspace"
    uploads = tmp_path / "alice" / thread / "uploads"
    outputs = tmp_path / "alice" / thread / "outputs"
    workspace.mkdir(parents=True, exist_ok=True)
    uploads.mkdir(parents=True, exist_ok=True)
    outputs.mkdir(parents=True, exist_ok=True)
    return TrustedRuntimeEnvelope(
        effective_user_id="alice",
        outer_thread_id=thread,
        outer_run_id="run-1",
        app_config=FakeAppConfig(),
        workspace_host_path=workspace,
        uploads_host_path=uploads,
        outputs_host_path=outputs,
        workspace_virtual_root="/mnt/user-data/workspace",
        uploads_virtual_root="/mnt/user-data/uploads",
        outputs_virtual_root="/mnt/user-data/outputs",
        parent_sandbox=_Sandbox(),
        progress=None,
    )


def _patch_stores(monkeypatch: pytest.MonkeyPatch) -> None:
    async def wu_create(_cls, envelope, *, research_id, **_kwargs):
        return WorkUnitStore(
            workspace_host_path=envelope.workspace_host_path,
            research_id=research_id,
            clock=lambda: datetime(2026, 7, 14, tzinfo=UTC),
            monotonic=time.monotonic,
            lock_sleep=time.sleep,
            token_factory=lambda: secrets.token_hex(16),
            fault_hook=None,
        )

    async def bb_create(_cls, envelope, *, research_id, **_kwargs):
        return BootstrapBundleStore(workspace_host_path=envelope.workspace_host_path, research_id=research_id)

    async def rb_create(_cls, envelope, *, research_id, **_kwargs):
        return RequestBundleStore(workspace_host_path=envelope.workspace_host_path, research_id=research_id)

    monkeypatch.setattr(WorkUnitStore, "create", classmethod(wu_create))
    monkeypatch.setattr(BootstrapBundleStore, "create", classmethod(bb_create))
    monkeypatch.setattr(RequestBundleStore, "create", classmethod(rb_create))


def _profile_file(envelope: TrustedRuntimeEnvelope, research_id: str) -> Path:
    return envelope.workspace_host_path / "deep-research" / research_id / "request" / "profile.json"


def _marker_file(envelope: TrustedRuntimeEnvelope, research_id: str) -> Path:
    return envelope.workspace_host_path / "deep-research" / research_id / "request" / "marker.json"


def _messages_response(request_id: str, value: str, message_id: str) -> HumanMessage:
    return HumanMessage(
        content=value,
        id=message_id,
        additional_kwargs={
            "human_input_response": {
                "version": 1,
                "kind": "human_input_response",
                "source": "deep_research",
                "request_id": request_id,
                "response_kind": ResponseKind.TEXT.value,
                "value": value,
            }
        },
    )


def _option_response(request_id: str, value: str, message_id: str) -> HumanMessage:
    return HumanMessage(
        content=value,
        id=message_id,
        additional_kwargs={
            "human_input_response": {
                "version": 1,
                "kind": "human_input_response",
                "source": "deep_research",
                "request_id": request_id,
                "response_kind": "option",
                "option_id": value,
                "value": value,
            }
        },
    )


def _command_payload(result: object) -> tuple[dict[str, object], dict[str, object]]:
    assert isinstance(result, Command)
    message = result.update["messages"][0]
    return json.loads(message.content), message.artifact["human_input"]


def _handlers(recipe: ResearchGraphRecipe) -> tuple[StartResearchHandler, ResumeResearchHandler, object, InMemorySaver]:
    start = StartResearchHandler(recipe)
    resume = ResumeResearchHandler(recipe)
    saver = InMemorySaver()
    graph = recipe.builder.compile(checkpointer=saver)
    return start, resume, graph, saver


def _start_input(research_id: str, user: HumanMessage) -> ResearchActionInput:
    return ResearchActionInput(
        action=LifecycleAction.START,
        research_id=research_id,
        tool_call_id="call-start",
        messages=(user,),
        start_message=SelectedStartMessage(message_id=str(user.id), text=str(user.content)),
    )


def _resume_input(research_id: str, messages: tuple[HumanMessage, ...], call_id: str) -> ResearchActionInput:
    return ResearchActionInput(
        action=LifecycleAction.RESUME,
        research_id=research_id,
        tool_call_id=call_id,
        messages=messages,
    )


async def _start_graph(start: StartResearchHandler, graph, envelope: TrustedRuntimeEnvelope, user: HumanMessage):
    research_id = derive_research_id(
        effective_user_id=envelope.effective_user_id, outer_thread_id=envelope.outer_thread_id
    )
    action_input = _start_input(research_id, user)
    config = {"configurable": {"thread_id": start.derive_namespace(envelope, action_input), "checkpoint_ns": ""}}
    result = await start.execute(graph, config=config, envelope=envelope, action_input=action_input)
    return research_id, config, result


async def test_mixed_hitl1_complete_profile_lifecycle(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _patch_stores(monkeypatch)
    bridge_factory = _BridgeFactory(_brief_json(), _brief_json())
    recipe = ResearchGraphRecipe.create(implementation_modes=_MIXED_HITL1, node_agent_bridge_factory=bridge_factory)
    start, resume, graph, _saver = _handlers(recipe)
    envelope = _envelope(tmp_path)
    user = HumanMessage(content="Compare storage options", id="human-start")

    research_id, config, started = await _start_graph(start, graph, envelope, user)
    start_result, hitl1 = _command_payload(started)
    assert start_result["code"] == "suspended"
    assert hitl1["source"] == "deep_research"
    assert hitl1["mode"] == "text"
    assert (
        BootstrapMarker.from_canonical_json(_marker_file(envelope, research_id).read_bytes()).research_id == research_id
    )

    profile_answer = json.dumps(
        {
            "depth": "deep_dive",
            "audience": "domain_expert",
            "format": "annotated_bibliography",
            "cost_tolerance": "extensive",
            "time_budget": "overnight",
            "must_answer": ["Q1", "Q2"],
        }
    )
    response = _messages_response(str(hitl1["request_id"]), profile_answer, "human-profile")
    resumed = await resume.execute(
        graph,
        config=config,
        envelope=envelope,
        action_input=_resume_input(research_id, (user, response), "call-resume-1"),
    )
    resume_result, hitl2 = _command_payload(resumed)
    assert resume_result["code"] == "suspended"
    assert hitl2["mode"] == "choice"

    snapshot = await graph.aget_state(config)
    values = snapshot.values
    assert values["profile_ref"].sandbox_path.endswith("/request/profile.json")
    assert values["research_depth"] == "deep_dive"
    assert values["target_audience"] == "domain_expert"
    assert values["output_format"] == "annotated_bibliography"
    assert values["cost_tolerance"] == "extensive"
    assert values["time_budget"] == "overnight"
    assert tuple(values["must_answer_questions"]) == ("Q1", "Q2")
    assert values["degraded_profile"] is False
    assert values["pending_profile"] is None
    assert json.loads(_profile_file(envelope, research_id).read_text())["depth"] == "deep_dive"

    proceed = _option_response(str(hitl2["request_id"]), "proceed", "human-proceed")
    completed = await resume.execute(
        graph,
        config=config,
        envelope=envelope,
        action_input=_resume_input(research_id, (user, response, proceed), "call-resume-2"),
    )
    assert completed["code"] == "completed"
    assert completed["implementation_mode"] == "full_fake"
    files = {
        path.relative_to(envelope.workspace_host_path).as_posix()
        for path in envelope.workspace_host_path.rglob("*")
        if path.is_file()
    }
    assert any(path.endswith("/request/profile.json") for path in files)
    assert not any(path.startswith(f"deep-research/{research_id}/synthesis/") for path in files)
    assert not any(path.startswith(f"deep-research/{research_id}/final/") for path in files)


async def test_mixed_hitl1_followup_survives_recompile(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _patch_stores(monkeypatch)
    bridge_factory = _BridgeFactory(_brief_json(), _brief_json())
    recipe = ResearchGraphRecipe.create(implementation_modes=_MIXED_HITL1, node_agent_bridge_factory=bridge_factory)
    start, resume, graph, saver = _handlers(recipe)
    envelope = _envelope(tmp_path)
    user = HumanMessage(content="Compare storage options", id="human-start")
    research_id, config, started = await _start_graph(start, graph, envelope, user)
    _start_result, hitl1 = _command_payload(started)

    incomplete = _messages_response(
        str(hitl1["request_id"]),
        '{"depth":"quick_overview","audience":"layperson"}',
        "human-partial",
    )
    followup = await resume.execute(
        graph,
        config=config,
        envelope=envelope,
        action_input=_resume_input(research_id, (user, incomplete), "call-resume-partial"),
    )
    _follow_result, hitl1_followup = _command_payload(followup)
    assert hitl1_followup["request_id"] != hitl1["request_id"]
    follow_context = json.loads(hitl1_followup["context"])
    assert follow_context["missing_dimensions"] == ["format", "cost_tolerance", "time_budget", "must_answer"]

    snapshot = await graph.aget_state(config)
    assert snapshot.values["pending_profile"]["depth"] == "quick_overview"
    assert snapshot.values["profile_followup_round"] == 1

    restarted_graph = recipe.builder.compile(checkpointer=saver)
    complete = _messages_response(
        str(hitl1_followup["request_id"]),
        '{"format":"faq","cost_tolerance":"minimal","time_budget":"very_quick","must_answer":["Q2"]}',
        "human-followup",
    )
    resumed = await resume.execute(
        restarted_graph,
        config=config,
        envelope=envelope,
        action_input=_resume_input(research_id, (user, incomplete, complete), "call-resume-followup"),
    )
    _resume_result, hitl2 = _command_payload(resumed)
    assert hitl2["mode"] == "choice"
    values = (await restarted_graph.aget_state(config)).values
    assert values["research_depth"] == "quick_overview"
    assert values["target_audience"] == "layperson"
    assert values["output_format"] == "faq"
    assert values["pending_profile"] is None


async def test_mixed_hitl1_double_invalid_brief_blocks_without_profile(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _patch_stores(monkeypatch)
    bridge_factory = _BridgeFactory("not-json", '{"still":"invalid"}')
    recipe = ResearchGraphRecipe.create(implementation_modes=_MIXED_HITL1, node_agent_bridge_factory=bridge_factory)
    start, _resume, graph, _saver = _handlers(recipe)
    envelope = _envelope(tmp_path)
    user = HumanMessage(content="Compare storage options", id="human-start")

    research_id, config, result = await _start_graph(start, graph, envelope, user)
    assert isinstance(result, dict)
    assert result["code"] == "blocked"
    assert result["status"] == "blocked"
    assert not _profile_file(envelope, research_id).exists()
    snapshot = await graph.aget_state(config)
    assert not snapshot.tasks[0].interrupts if snapshot.tasks else True


async def test_full_fake_lifecycle_does_not_construct_real_hitl1_capabilities(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _patch_stores(monkeypatch)

    def forbidden_bridge(**_kwargs: object) -> object:
        raise AssertionError("full fake must not construct bridge")

    async def forbidden_request_store(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("full fake must not construct request bundle")

    recipe = ResearchGraphRecipe.create(
        implementation_modes=_FULL_FAKE,
        node_agent_bridge_factory=forbidden_bridge,
        request_bundle_store_factory=forbidden_request_store,
    )
    start, resume, graph, _saver = _handlers(recipe)
    envelope = _envelope(tmp_path)
    user = HumanMessage(content="question", id="human-start")
    research_id, config, started = await _start_graph(start, graph, envelope, user)
    _start_result, hitl1 = _command_payload(started)
    response = _messages_response(str(hitl1["request_id"]), "profile", "human-profile")
    resumed = await resume.execute(
        graph,
        config=config,
        envelope=envelope,
        action_input=_resume_input(research_id, (user, response), "call-resume"),
    )
    _resume_result, hitl2 = _command_payload(resumed)
    assert hitl2["mode"] == "choice"
    assert not _profile_file(envelope, research_id).exists()
