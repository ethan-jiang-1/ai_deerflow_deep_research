"""Tests for real final delivery node.

@impl FID-001..005
"""

from __future__ import annotations

from deerflow_deep_research.domain.context import GraphContextView, NodeAgentContext
from deerflow_deep_research.domain.lifecycle import LifecycleStatus
from deerflow_deep_research.domain.node_spec import NodeBuildDependencies
from deerflow_deep_research.graph.nodes.final_delivery.node import build_real


def _deps():
    graph = GraphContextView(
        research_scope_id="r_" + "A" * 43,
        workspace_root="/mnt/user-data/workspace/deep-research/r",
        uploads_root="/mnt/user-data/uploads",
        outputs_root="/mnt/user-data/outputs/deep-research/r",
    )
    return NodeBuildDependencies(
        graph_context=graph,
        agent_context=NodeAgentContext(
            research_scope_id=graph.research_scope_id,
            node_name="final_delivery",
            attempt_id="g0-final-a1",
            workspace_root=graph.workspace_root,
            attempt_root=f"{graph.workspace_root}/final",
            policy_name="skeleton-final-delivery",
        ),
        capabilities=object(),
    )


class TestRealFinalDelivery:
    def test_produces_report_refs_and_completed(self) -> None:
        import asyncio

        state = {
            "research_id": "r_" + "A" * 43,
            "generation": 0,
            "accepted_submission_refs": ("ref:1", "ref:2"),
            "readiness_report_plan": None,
        }
        result = asyncio.run(build_real(_deps())(state))
        assert result["terminal_status"] == LifecycleStatus.COMPLETED.value
        assert len(result["report_refs"]) == 2
        assert result["phase"] == "final_delivery"

    def test_handles_empty_evidence(self) -> None:
        import asyncio

        state = {
            "research_id": "r_" + "A" * 43,
            "generation": 0,
            "accepted_submission_refs": (),
            "readiness_report_plan": None,
        }
        result = asyncio.run(build_real(_deps())(state))
        assert result["terminal_status"] == LifecycleStatus.COMPLETED.value
        assert len(result["report_refs"]) == 2
