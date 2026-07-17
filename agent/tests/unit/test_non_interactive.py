"""Tests for non-interactive policy in HITL nodes.

@impl RUO-002
@impl RUO-001
"""

from __future__ import annotations

import time
from datetime import UTC, datetime

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from deerflow_deep_research.domain.context import GraphContextView, NodeAgentContext
from deerflow_deep_research.domain.lifecycle import LifecycleAction
from deerflow_deep_research.domain.node_spec import NodeBuildDependencies
from deerflow_deep_research.graph.topology import LOGICAL_NODES
from deerflow_deep_research.runtime.human_input import SelectedStartMessage
from deerflow_deep_research.runtime.research import ResearchActionInput, ResearchGraphRecipe, StartResearchHandler
from deerflow_deep_research.runtime.runtime_adapter import TrustedRuntimeEnvelope
from deerflow_deep_research.runtime.work_unit_store import WorkUnitStore


async def test_tool_forwards_non_interactive_policy_to_action_input() -> None:
    """@impl RUO-001"""
    from types import SimpleNamespace

    from langchain_core.messages import AIMessage, HumanMessage

    from deerflow_deep_research.tool import run_deep_research

    policy = {"auto_profile": True, "auto_proceed": True}
    captured = {}

    class Host:
        def is_registered(self, action):
            return action == "start"

        async def run_action(self, *, action, envelope, action_input):
            captured["input"] = action_input
            return {"code": "ok"}

    class Adapter:
        async def adapt(self, runtime, *, initialize_parent_sandbox=True):
            return SimpleNamespace(effective_user_id="alice", outer_thread_id="thread", parent_sandbox=object())

    call_id = "call-start"
    control = AIMessage(content="", tool_calls=[{"name": "deep_research", "args": {"action": "start"}, "id": call_id}])
    user = HumanMessage(content="Research storage", id="human-start")
    runtime = SimpleNamespace(
        state={"messages": [user, control]},
        context={"non_interactive": True, "non_interactive_policy": policy},
        tool_call_id=call_id,
    )
    result = await run_deep_research(
        action="start", probe_id=None, runtime=runtime, adapter=Adapter(), host_factory=lambda: Host()
    )
    assert result == {"code": "ok"}
    assert captured["input"].non_interactive_policy == policy


async def test_start_persists_non_interactive_policy_in_checkpoint(tmp_path) -> None:
    """@impl RUO-001"""
    policy = {"auto_profile": True, "auto_proceed": True}
    research_id = "r_" + "A" * 43

    async def create_store(envelope, *, research_id):
        return WorkUnitStore(
            workspace_host_path=envelope.workspace_host_path,
            research_id=research_id,
            clock=lambda: datetime(2026, 7, 17, tzinfo=UTC),
            monotonic=time.monotonic,
            lock_sleep=time.sleep,
            token_factory=lambda: "0" * 32,
            fault_hook=None,
        )

    recipe = ResearchGraphRecipe.create(
        implementation_modes={name: "fake" for name in LOGICAL_NODES},
        work_unit_store_factory=create_store,
    )
    handler = StartResearchHandler(recipe)
    graph = recipe.builder.compile(checkpointer=InMemorySaver())
    envelope = TrustedRuntimeEnvelope(
        effective_user_id="alice",
        outer_thread_id="thread-1",
        outer_run_id="run-1",
        app_config=type("AppConfig", (), {"checkpointer": None, "database": None})(),
        workspace_host_path=tmp_path / "workspace",
        uploads_host_path=tmp_path / "uploads",
        outputs_host_path=tmp_path / "outputs",
        workspace_virtual_root="/mnt/user-data/workspace",
        uploads_virtual_root="/mnt/user-data/uploads",
        outputs_virtual_root="/mnt/user-data/outputs",
        parent_sandbox=object(),
        progress=None,
    )
    for path in (envelope.workspace_host_path, envelope.uploads_host_path, envelope.outputs_host_path):
        path.mkdir()
    action_input = ResearchActionInput(
        action=LifecycleAction.START,
        research_id=research_id,
        tool_call_id="call-start",
        messages=(),
        start_message=SelectedStartMessage(message_id="human-start", text="Research storage"),
        non_interactive_policy=policy,
    )
    config = {"configurable": {"thread_id": "non-interactive-policy", "checkpoint_ns": ""}}

    result = await handler.execute(
        graph,
        config=config,
        envelope=envelope,
        action_input=action_input,
    )

    assert isinstance(result, Command)
    snapshot = await graph.aget_state(config)
    assert snapshot.values["non_interactive_policy"] == policy


class Store:
    async def write_profile(self, profile):
        from deerflow_deep_research.domain.state import ContentRef

        return ContentRef(
            sandbox_path="workspace/deep-research/r_" + "A" * 43 + "/request/profile.json", content_hash="h_" + "A" * 43
        )


class TestHitl1AutoProfile:
    def test_auto_profile_skips_interrupt(self) -> None:
        import asyncio

        from deerflow_deep_research.graph.nodes.hitl1.node import build_real

        state = {
            "research_id": "r_" + "A" * 43,
            "generation": 0,
            "start_message_id": "msg-start",
            "request_text": "test question",
            "non_interactive_policy": {"auto_profile": True, "auto_proceed": True},
            "consumed_request_ids": (),
            "consumed_message_ids": (),
            "execution_trace": (),
            "phase": "hitl1",
        }
        graph = GraphContextView(
            research_scope_id="r_" + "A" * 43,
            workspace_root="/tmp/ws",
            uploads_root="/tmp/up",
            outputs_root="/tmp/out",
        )
        deps = NodeBuildDependencies(
            graph_context=graph,
            agent_context=NodeAgentContext(
                research_scope_id="r_" + "A" * 43,
                node_name="hitl1",
                attempt_id="a1",
                workspace_root="/tmp/ws",
                attempt_root="/tmp/ws/hitl1",
                policy_name="hitl1-real",
            ),
            capabilities=object(),
            request_bundle=Store(),
        )
        result = asyncio.run(build_real(deps)(state))
        assert result["route"] == "accepted"
        assert result.get("degraded_profile") is True


class TestHitl2AutoProceed:
    def test_auto_proceed_skips_interrupt(self) -> None:
        import asyncio

        from deerflow_deep_research.graph.nodes.hitl2.node import build_real

        state = {
            "research_id": "r_" + "A" * 43,
            "generation": 0,
            "start_message_id": "msg-start",
            "non_interactive_policy": {"auto_profile": True, "auto_proceed": True},
            "accepted_submission_refs": ("ref:1",),
            "consumed_request_ids": (),
            "consumed_message_ids": (),
            "execution_trace": (),
            "phase": "hitl2",
            "synthesis_gaps": (),
        }
        graph = GraphContextView(
            research_scope_id="r_" + "A" * 43,
            workspace_root="/tmp/ws",
            uploads_root="/tmp/up",
            outputs_root="/tmp/out",
        )
        deps = NodeBuildDependencies(
            graph_context=graph,
            agent_context=NodeAgentContext(
                research_scope_id="r_" + "A" * 43,
                node_name="hitl2",
                attempt_id="a1",
                workspace_root="/tmp/ws",
                attempt_root="/tmp/ws/hitl2",
                policy_name="hitl2-real",
            ),
            capabilities=object(),
        )
        result = asyncio.run(build_real(deps)(state))
        assert result["route"] == "proceed"
