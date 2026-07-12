"""Event-loop blocking guard for the full-fake lifecycle runtime."""

from __future__ import annotations

import contextlib
import json
from pathlib import Path
from types import SimpleNamespace

from blockbuster import blockbuster_ctx
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from deerflow_deep_research.runtime.control import build_control_graph_host
from deerflow_deep_research.runtime.runtime_adapter import TrustedRuntimeEnvelope
from deerflow_deep_research.tool import run_deep_research


class Adapter:
    def __init__(self, envelope: TrustedRuntimeEnvelope) -> None:
        self.envelope = envelope

    async def adapt(self, _runtime):
        return self.envelope


def _runtime(messages, call_id: str):
    return SimpleNamespace(state={"messages": list(messages)}, context={}, tool_call_id=call_id)


def _call(action: str, call_id: str, research_id: str | None = None) -> AIMessage:
    args = {"action": action}
    if research_id is not None:
        args["research_id"] = research_id
    return AIMessage(content="", tool_calls=[{"name": "deep_research", "args": args, "id": call_id}])


def _payload(command: Command):
    message = command.update["messages"][0]
    return message, message.artifact["human_input"]


async def test_full_fake_lifecycle_does_not_block_event_loop() -> None:
    saver = InMemorySaver()
    provider_entries = 0
    provider_exits = 0

    @contextlib.asynccontextmanager
    async def provider(_app_config):
        nonlocal provider_entries, provider_exits
        provider_entries += 1
        try:
            yield saver
        finally:
            provider_exits += 1

    app_config = SimpleNamespace(
        checkpointer=SimpleNamespace(type="sqlite", connection_string="virtual-test.db"),
        database=None,
    )
    envelope = TrustedRuntimeEnvelope(
        effective_user_id="alice",
        outer_thread_id="thread-blocking-io",
        outer_run_id="run-1",
        app_config=app_config,
        workspace_host_path=Path("/x/workspace"),
        uploads_host_path=Path("/x/uploads"),
        outputs_host_path=Path("/x/outputs"),
        workspace_virtual_root="/mnt/user-data/workspace",
        uploads_virtual_root="/mnt/user-data/uploads",
        outputs_virtual_root="/mnt/user-data/outputs",
        parent_sandbox=object(),
        progress=None,
    )
    adapter = Adapter(envelope)
    host = build_control_graph_host(
        checkpointer_factory=provider,
        fingerprint_verifier=lambda _app_config: None,
    )
    start_user = HumanMessage(content="research question", id="human-start")

    with blockbuster_ctx(["deerflow_deep_research"]):
        started = await run_deep_research(
            action="start",
            probe_id=None,
            runtime=_runtime([start_user, _call("start", "call-start")], "call-start"),
            adapter=adapter,
            host_factory=lambda: host,
        )
        assert isinstance(started, Command)
        start_message, hitl1 = _payload(started)
        research_id = json.loads(start_message.content)["research_id"]

        response1 = HumanMessage(
            content="profile answer",
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
        resumed = await run_deep_research(
            action="resume",
            probe_id=None,
            research_id=research_id,
            runtime=_runtime([start_user, response1, _call("resume", "call-resume-1", research_id)], "call-resume-1"),
            adapter=adapter,
            host_factory=lambda: host,
        )
        assert isinstance(resumed, Command)
        _message, hitl2 = _payload(resumed)

        response2 = HumanMessage(
            content="proceed",
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
        completed = await run_deep_research(
            action="resume",
            probe_id=None,
            research_id=research_id,
            runtime=_runtime(
                [start_user, response1, response2, _call("resume", "call-resume-2", research_id)],
                "call-resume-2",
            ),
            adapter=adapter,
            host_factory=lambda: host,
        )

    assert completed["code"] == "completed"
    assert completed["implementation_mode"] == "full_fake"
    assert provider_entries == provider_exits == 3
