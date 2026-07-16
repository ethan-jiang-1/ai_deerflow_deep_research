"""Tests for non-interactive policy in HITL nodes.

@impl RUO-002
"""

from __future__ import annotations

import pytest
from unittest.mock import patch

from deerflow_deep_research.domain.context import GraphContextView, NodeAgentContext
from deerflow_deep_research.domain.node_spec import NodeBuildDependencies


class Store:
    async def write_profile(self, profile):
        from deerflow_deep_research.domain.state import ContentRef
        return ContentRef(sandbox_path="workspace/deep-research/r_" + "A" * 43 + "/request/profile.json",
                          content_hash="h_" + "A" * 43)


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
                node_name="hitl1", attempt_id="a1",
                workspace_root="/tmp/ws", attempt_root="/tmp/ws/hitl1",
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
                node_name="hitl2", attempt_id="a1",
                workspace_root="/tmp/ws", attempt_root="/tmp/ws/hitl2",
                policy_name="hitl2-real",
            ),
            capabilities=object(),
        )
        result = asyncio.run(build_real(deps)(state))
        assert result["route"] == "proceed"
