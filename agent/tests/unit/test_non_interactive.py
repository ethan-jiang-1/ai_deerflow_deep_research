"""Tests for non-interactive policy in HITL nodes.

@impl RUO-002
"""

from __future__ import annotations

from deerflow_deep_research.domain.context import GraphContextView, NodeAgentContext
from deerflow_deep_research.domain.node_spec import NodeBuildDependencies


async def test_tool_forwards_non_interactive_policy_to_action_input() -> None:
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
