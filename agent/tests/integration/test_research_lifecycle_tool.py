"""Public lifecycle dispatch and namespace semantics (RUI-006/REG-004/005)."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.types import Command
from pydantic import ValidationError

from deerflow_deep_research.runtime.control import build_control_graph_host
from deerflow_deep_research.runtime.research import derive_research_id
from deerflow_deep_research.runtime.runtime_adapter import TrustedRuntimeEnvelope
from deerflow_deep_research.tool import DeepResearchArgs, run_deep_research


class FakeAppConfig:
    checkpointer = None
    database = None


def _envelope(user: str = "alice", thread: str = "thread-1") -> TrustedRuntimeEnvelope:
    return TrustedRuntimeEnvelope(
        effective_user_id=user,
        outer_thread_id=thread,
        outer_run_id="run-1",
        app_config=FakeAppConfig(),
        workspace_host_path=Path("/tmp/users/alice/workspace"),
        uploads_host_path=Path("/tmp/users/alice/uploads"),
        outputs_host_path=Path("/tmp/users/alice/outputs"),
        workspace_virtual_root="/mnt/user-data/workspace",
        uploads_virtual_root="/mnt/user-data/uploads",
        outputs_virtual_root="/mnt/user-data/outputs",
        parent_sandbox=object(),
        progress=None,
    )


class FakeAdapter:
    def __init__(self, envelope=None) -> None:
        self.envelope = envelope or _envelope()
        self.adapted = 0

    async def adapt(self, _runtime):
        self.adapted += 1
        return self.envelope


def _runtime(messages, call_id: str, *, context: dict | None = None):
    return SimpleNamespace(
        state={"messages": list(messages)},
        context=context or {},
        tool_call_id=call_id,
    )


def _call(action: str, call_id: str, **args) -> AIMessage:
    return AIMessage(
        content="",
        tool_calls=[{"name": "deep_research", "args": {"action": action, **args}, "id": call_id}],
    )


def _host():
    return build_control_graph_host(fingerprint_verifier=lambda _app: None)


def _command_payload(command: Command) -> tuple[dict, dict]:
    message = command.update["messages"][0]
    return json.loads(message.content), message.artifact["human_input"]


def test_action_specific_schema_is_strict() -> None:
    assert DeepResearchArgs(action="start").research_id is None
    research_id = "r_" + "A" * 43
    assert DeepResearchArgs(action="resume", research_id=research_id).research_id == research_id
    with pytest.raises(ValidationError):
        DeepResearchArgs(action="start", research_id=research_id)
    with pytest.raises(ValidationError):
        DeepResearchArgs(action="resume")
    with pytest.raises(ValidationError):
        DeepResearchArgs(action="status", research_id="bad")
    with pytest.raises(ValidationError):
        DeepResearchArgs(action="cancel", research_id=research_id, answer="forged")


def test_research_id_is_canonical_stable_and_scope_distinct() -> None:
    first = derive_research_id(effective_user_id="ab", outer_thread_id="c")
    ambiguous = derive_research_id(effective_user_id="a", outer_thread_id="bc")
    assert first != ambiguous
    assert first == derive_research_id(effective_user_id="ab", outer_thread_id="c")
    assert len(first) == 45 and first.startswith("r_")
    assert "ab" not in first and "c" not in first


@pytest.mark.asyncio
async def test_public_memory_lifecycle_start_resume_resume_status() -> None:
    host = _host()
    adapter = FakeAdapter()
    start_user = HumanMessage(content="research question", id="human-start")
    start_ai = _call("start", "call-start")
    start = await run_deep_research(
        action="start",
        probe_id=None,
        runtime=_runtime([start_user, start_ai], "call-start"),
        adapter=adapter,
        host_factory=lambda: host,
    )
    assert isinstance(start, Command)
    start_result, hitl1 = _command_payload(start)
    assert start_result["code"] == "suspended"
    assert start_result["implementation_mode"] == "full_fake"

    response1 = HumanMessage(
        content="formatted",
        id="human-1",
        additional_kwargs={
            "human_input_response": {
                "version": 1,
                "kind": "human_input_response",
                "source": "deep_research",
                "request_id": hitl1["request_id"],
                "response_kind": "text",
                "value": "profile answer",
            }
        },
    )
    resume_ai = _call("resume", "call-resume-1", research_id=start_result["research_id"])
    resumed = await run_deep_research(
        action="resume",
        probe_id=None,
        research_id=start_result["research_id"],
        runtime=_runtime([start_user, start_ai, response1, resume_ai], "call-resume-1"),
        adapter=adapter,
        host_factory=lambda: host,
    )
    assert isinstance(resumed, Command)
    _, hitl2 = _command_payload(resumed)

    response2 = HumanMessage(
        content="formatted",
        id="human-2",
        additional_kwargs={
            "human_input_response": {
                "version": 1,
                "kind": "human_input_response",
                "source": "deep_research",
                "request_id": hitl2["request_id"],
                "response_kind": "option",
                "option_id": "proceed",
                "value": "proceed",
            }
        },
    )
    resume2_ai = _call("resume", "call-resume-2", research_id=start_result["research_id"])
    completed = await run_deep_research(
        action="resume",
        probe_id=None,
        research_id=start_result["research_id"],
        runtime=_runtime([start_user, response1, response2, resume2_ai], "call-resume-2"),
        adapter=adapter,
        host_factory=lambda: host,
    )
    assert completed["code"] == "completed"
    assert completed["status"] == "completed"
    assert completed["implementation_mode"] == "full_fake"
    assert "report" not in str(completed)

    status_ai = _call("status", "call-status", research_id=start_result["research_id"])
    status = await run_deep_research(
        action="status",
        probe_id=None,
        research_id=start_result["research_id"],
        runtime=_runtime([status_ai], "call-status"),
        adapter=adapter,
        host_factory=lambda: host,
    )
    assert status["code"] == "status_ok"
    assert status["status"] == "completed"

    fresh = HumanMessage(content="proceed", id="human-fresh")
    invalid = await run_deep_research(
        action="resume",
        probe_id=None,
        research_id=start_result["research_id"],
        runtime=_runtime([fresh, _call("resume", "call-after-terminal")], "call-after-terminal"),
        adapter=adapter,
        host_factory=lambda: host,
    )
    assert invalid["code"] == "invalid_transition"


@pytest.mark.asyncio
async def test_retained_memory_host_keeps_probe_visits_isolated_from_research() -> None:
    host = _host()
    adapter = FakeAdapter()
    probe_runtime = _runtime([], "probe-call")
    before = await run_deep_research(
        action="infra_probe",
        probe_id="p1",
        runtime=probe_runtime,
        adapter=adapter,
        host_factory=lambda: host,
    )
    user = HumanMessage(content="research question", id="human-start")
    started = await run_deep_research(
        action="start",
        probe_id=None,
        runtime=_runtime([user, _call("start", "call-start")], "call-start"),
        adapter=adapter,
        host_factory=lambda: host,
    )
    after = await run_deep_research(
        action="infra_probe",
        probe_id="p1",
        runtime=probe_runtime,
        adapter=adapter,
        host_factory=lambda: host,
    )

    control, _request = _command_payload(started)
    assert control["durability"] == "same_process"
    assert before["previous_visit"] is None and before["current_visit"] == 1
    assert after["previous_visit"] == 1 and after["current_visit"] == 2


@pytest.mark.asyncio
async def test_early_dispatch_refusals_do_not_mutate_lifecycle() -> None:
    host = _host()
    adapter = FakeAdapter()
    user = HumanMessage(content="question", id="human-start")
    sibling_ai = AIMessage(
        content="",
        tool_calls=[
            {"name": "deep_research", "args": {"action": "start"}, "id": "call-start"},
            {"name": "other", "args": {}, "id": "other-call"},
        ],
    )
    denied = await run_deep_research(
        action="start",
        probe_id=None,
        runtime=_runtime([user, sibling_ai], "call-start"),
        adapter=adapter,
        host_factory=lambda: host,
    )
    assert denied["code"] == "exclusive_control_call_required"
    assert adapter.adapted == 0

    normal_ai = _call("start", "call-start")
    noninteractive = await run_deep_research(
        action="start",
        probe_id=None,
        runtime=_runtime([user, normal_ai], "call-start", context={"non_interactive": True}),
        adapter=adapter,
        host_factory=lambda: host,
    )
    assert noninteractive["code"] == "interactive_required"

    im_denied = await run_deep_research(
        action="start",
        probe_id=None,
        runtime=_runtime([user, normal_ai], "call-start", context={"channel_user_id": "secret-channel-user"}),
        adapter=adapter,
        host_factory=lambda: host,
    )
    assert im_denied["code"] == "human_input_transport_unavailable"
    assert "secret-channel-user" not in str(im_denied)


@pytest.mark.asyncio
async def test_interaction_refusals_preserve_status_and_cancel_controls() -> None:
    host = _host()
    adapter = FakeAdapter()
    user = HumanMessage(content="question", id="human-start")
    started = await run_deep_research(
        action="start",
        probe_id=None,
        runtime=_runtime([user, _call("start", "call-start")], "call-start"),
        adapter=adapter,
        host_factory=lambda: host,
    )
    result, _request = _command_payload(started)
    research_id = result["research_id"]

    for context, expected in (
        ({"non_interactive": True}, "interactive_required"),
        ({"channel_name": "known-im"}, "human_input_transport_unavailable"),
    ):
        denied = await run_deep_research(
            action="resume",
            probe_id=None,
            research_id=research_id,
            runtime=_runtime(
                [
                    HumanMessage(content="answer", id=f"answer-{expected}"),
                    _call("resume", f"resume-{expected}", research_id=research_id),
                ],
                f"resume-{expected}",
                context=context,
            ),
            adapter=adapter,
            host_factory=lambda: host,
        )
        assert denied["code"] == expected

        status = await run_deep_research(
            action="status",
            probe_id=None,
            research_id=research_id,
            runtime=_runtime(
                [_call("status", f"status-{expected}", research_id=research_id)],
                f"status-{expected}",
                context=context,
            ),
            adapter=adapter,
            host_factory=lambda: host,
        )
        assert status["code"] == "status_ok"
        assert status["status"] == "suspended"

    cancelled = await run_deep_research(
        action="cancel",
        probe_id=None,
        research_id=research_id,
        runtime=_runtime(
            [_call("cancel", "cancel-known-im", research_id=research_id)],
            "cancel-known-im",
            context={"channel_name": "known-im", "non_interactive": True},
        ),
        adapter=adapter,
        host_factory=lambda: host,
    )
    assert cancelled["code"] == "cancelled"


@pytest.mark.asyncio
async def test_new_thread_gets_an_independent_research_namespace() -> None:
    host = _host()
    first_adapter = FakeAdapter(_envelope(thread="thread-1"))
    second_adapter = FakeAdapter(_envelope(thread="thread-2"))
    first_user = HumanMessage(content="first question", id="human-first")
    second_user = HumanMessage(content="second question", id="human-second")
    first = await run_deep_research(
        action="start",
        probe_id=None,
        runtime=_runtime([first_user, _call("start", "call-first")], "call-first"),
        adapter=first_adapter,
        host_factory=lambda: host,
    )
    second = await run_deep_research(
        action="start",
        probe_id=None,
        runtime=_runtime([second_user, _call("start", "call-second")], "call-second"),
        adapter=second_adapter,
        host_factory=lambda: host,
    )
    first_result, _ = _command_payload(first)
    second_result, _ = _command_payload(second)
    assert first_result["research_id"] != second_result["research_id"]


@pytest.mark.asyncio
async def test_same_start_reprojects_and_different_message_conflicts() -> None:
    host = _host()
    adapter = FakeAdapter()
    user = HumanMessage(content="question", id="human-start")
    first = await run_deep_research(
        action="start",
        probe_id=None,
        runtime=_runtime([user, _call("start", "call-1")], "call-1"),
        adapter=adapter,
        host_factory=lambda: host,
    )
    first_result, first_request = _command_payload(first)
    retry = await run_deep_research(
        action="start",
        probe_id=None,
        runtime=_runtime([user, _call("start", "call-2")], "call-2"),
        adapter=adapter,
        host_factory=lambda: host,
    )
    retry_result, retry_request = _command_payload(retry)
    assert retry_result["research_id"] == first_result["research_id"]
    assert retry_request["request_id"] == first_request["request_id"]
    assert retry.update["messages"][0].tool_call_id == "call-2"

    another = HumanMessage(content="another question", id="human-new")
    conflict = await run_deep_research(
        action="start",
        probe_id=None,
        runtime=_runtime([another, _call("start", "call-3")], "call-3"),
        adapter=adapter,
        host_factory=lambda: host,
    )
    assert conflict["code"] == "thread_research_exists"
    assert conflict["research_id"] == first_result["research_id"]


@pytest.mark.asyncio
async def test_consumed_resume_reprojects_next_interrupt_and_cancel_is_idempotent() -> None:
    host = _host()
    adapter = FakeAdapter()
    user = HumanMessage(content="question", id="human-start")
    started = await run_deep_research(
        action="start",
        probe_id=None,
        runtime=_runtime([user, _call("start", "call-start")], "call-start"),
        adapter=adapter,
        host_factory=lambda: host,
    )
    started_result, hitl1 = _command_payload(started)
    response = HumanMessage(
        content="profile",
        id="human-response",
        additional_kwargs={
            "human_input_response": {
                "version": 1,
                "kind": "human_input_response",
                "source": "deep_research",
                "request_id": hitl1["request_id"],
                "response_kind": "text",
                "value": "profile",
            }
        },
    )
    resumed = await run_deep_research(
        action="resume",
        probe_id=None,
        research_id=started_result["research_id"],
        runtime=_runtime([user, response, _call("resume", "call-resume-1")], "call-resume-1"),
        adapter=adapter,
        host_factory=lambda: host,
    )
    _, hitl2 = _command_payload(resumed)
    replay = await run_deep_research(
        action="resume",
        probe_id=None,
        research_id=started_result["research_id"],
        runtime=_runtime([user, response, _call("resume", "call-replay")], "call-replay"),
        adapter=adapter,
        host_factory=lambda: host,
    )
    _, replayed_hitl2 = _command_payload(replay)
    assert replayed_hitl2["request_id"] == hitl2["request_id"]
    assert replay.update["messages"][0].tool_call_id == "call-replay"

    cancelled = await run_deep_research(
        action="cancel",
        probe_id=None,
        research_id=started_result["research_id"],
        runtime=_runtime([_call("cancel", "call-cancel")], "call-cancel"),
        adapter=adapter,
        host_factory=lambda: host,
    )
    assert cancelled["code"] == "cancelled"
    assert cancelled["status"] == "cancelled"
    repeated = await run_deep_research(
        action="cancel",
        probe_id=None,
        research_id=started_result["research_id"],
        runtime=_runtime([_call("cancel", "call-cancel-2")], "call-cancel-2"),
        adapter=adapter,
        host_factory=lambda: host,
    )
    assert repeated["code"] == "cancelled"


@pytest.mark.asyncio
async def test_wrong_scope_is_indistinguishable_from_absence_and_fresh_terminal_resume_is_invalid() -> None:
    host = _host()
    original_adapter = FakeAdapter()
    user = HumanMessage(content="question", id="human-start")
    started = await run_deep_research(
        action="start",
        probe_id=None,
        runtime=_runtime([user, _call("start", "call-start")], "call-start"),
        adapter=original_adapter,
        host_factory=lambda: host,
    )
    result, _ = _command_payload(started)
    wrong_adapter = FakeAdapter(_envelope(thread="other-thread"))
    wrong = await run_deep_research(
        action="status",
        probe_id=None,
        research_id=result["research_id"],
        runtime=_runtime([_call("status", "call-wrong")], "call-wrong"),
        adapter=wrong_adapter,
        host_factory=lambda: host,
    )
    absent = await run_deep_research(
        action="status",
        probe_id=None,
        research_id="r_" + "Z" * 43,
        runtime=_runtime([_call("status", "call-absent")], "call-absent"),
        adapter=original_adapter,
        host_factory=lambda: host,
    )
    assert wrong["code"] == absent["code"] == "research_not_found"
    assert "research_id" not in wrong and "research_id" not in absent
