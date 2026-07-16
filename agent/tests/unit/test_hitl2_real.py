"""Red tests for real HITL2 factory with interrupt pipeline.

@impl HIT-002
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from deerflow_deep_research.domain.context import GraphContextView, NodeAgentContext
from deerflow_deep_research.domain.lifecycle import HumanInputMode, LifecycleStatus
from deerflow_deep_research.domain.node_spec import NodeBuildDependencies
from deerflow_deep_research.graph.nodes.hitl2.node import build_real

_STATE = {
    "research_id": "r_" + "A" * 43,
    "generation": 0,
    "start_message_id": "msg-start",
    "accepted_submission_refs": ("ref:1", "ref:2", "ref:3"),
    "synthesis_gaps": (
        {"gap_id": "gap:1", "description": "Missing evidence X", "priority": 3, "search_required": True},
    ),
    "consumed_request_ids": (),
    "consumed_message_ids": (),
    "execution_trace": (),
    "phase": "wave2_synthesis",
}


def _deps():
    graph = GraphContextView(
        research_scope_id=_STATE["research_id"],
        workspace_root="/mnt/user-data/workspace/deep-research/r",
        uploads_root="/mnt/user-data/uploads",
        outputs_root="/mnt/user-data/outputs/deep-research/r",
    )
    return NodeBuildDependencies(
        graph_context=graph,
        agent_context=NodeAgentContext(
            research_scope_id=graph.research_scope_id,
            node_name="hitl2",
            attempt_id="g0-hitl2-a1",
            workspace_root=graph.workspace_root,
            attempt_root=f"{graph.workspace_root}/hitl2",
            policy_name="skeleton-hitl2",
        ),
        capabilities=object(),
    )


def _response(decision: str = "proceed"):
    """Build a valid resume payload matching the expected format."""
    # The request_id is generated inside the node; we extract it from the
    # mocked interrupt call and build a matching response by using a simple
    # side-effect that reads the descriptor.
    captured: dict = {}

    def side_effect(descriptor: dict) -> dict:
        captured["descriptor"] = descriptor
        captured["request_id"] = descriptor["request"]["request_id"]
        return {
            "request_id": captured["request_id"],
            "response_kind": "option",
            "option_id": decision,
            "value": decision,
            "message_id": "msg-response-1",
        }

    return side_effect, captured


class TestRealHitl2Factory:
    def test_interrupt_called_with_choice_mode(self) -> None:
        side_effect, captured = _response("proceed")
        with patch("deerflow_deep_research.graph.nodes.hitl2.node.interrupt", side_effect=side_effect):
            import asyncio

            result = asyncio.run(build_real(_deps())(_STATE))
            assert captured["descriptor"]["request"]["mode"] == HumanInputMode.CHOICE.value
            assert result["route"] == "proceed"

    def test_proceed_route(self) -> None:
        side_effect, _ = _response("proceed")
        with patch("deerflow_deep_research.graph.nodes.hitl2.node.interrupt", side_effect=side_effect):
            import asyncio

            result = asyncio.run(build_real(_deps())(_STATE))
            assert result["route"] == "proceed"

    def test_revise_view_route(self) -> None:
        side_effect, _ = _response("revise_view")
        with patch("deerflow_deep_research.graph.nodes.hitl2.node.interrupt", side_effect=side_effect):
            import asyncio

            result = asyncio.run(build_real(_deps())(_STATE))
            assert result["route"] == "revise_view"

    def test_repair_route(self) -> None:
        side_effect, _ = _response("repair")
        with patch("deerflow_deep_research.graph.nodes.hitl2.node.interrupt", side_effect=side_effect):
            import asyncio

            result = asyncio.run(build_real(_deps())(_STATE))
            assert result["route"] == "repair"

    def test_rerun_route(self) -> None:
        side_effect, _ = _response("rerun")
        with patch("deerflow_deep_research.graph.nodes.hitl2.node.interrupt", side_effect=side_effect):
            import asyncio

            result = asyncio.run(build_real(_deps())(_STATE))
            assert result["route"] == "rerun"

    def test_stop_route_sets_terminal(self) -> None:
        side_effect, _ = _response("stop")
        with patch("deerflow_deep_research.graph.nodes.hitl2.node.interrupt", side_effect=side_effect):
            import asyncio

            result = asyncio.run(build_real(_deps())(_STATE))
            assert result["route"] == "stop"
            assert result.get("terminal_status") == LifecycleStatus.STOPPED.value

    def test_cancel_handling(self) -> None:
        with patch("deerflow_deep_research.graph.nodes.hitl2.node.interrupt", return_value={"kind": "internal_cancel"}):
            import asyncio

            result = asyncio.run(build_real(_deps())(_STATE))
            assert result["route"] == "cancel"

    def test_stale_request_id_rejected(self) -> None:
        with patch("deerflow_deep_research.graph.nodes.hitl2.node.interrupt") as m:
            m.return_value = {
                "request_id": "wrong-id",
                "response_kind": "option",
                "option_id": "proceed",
                "value": "proceed",
                "message_id": "msg-x",
            }
            import asyncio

            with pytest.raises(ValueError, match="response_mismatch"):
                asyncio.run(build_real(_deps())(_STATE))
