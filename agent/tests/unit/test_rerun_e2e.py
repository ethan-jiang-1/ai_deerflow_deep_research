"""E2E tests for rerun: full-fake regression, mixed-graph, contract.

@impl REN-007
"""

from __future__ import annotations

from deerflow_deep_research.domain.context import GraphContextView, NodeAgentContext
from deerflow_deep_research.domain.lifecycle import LifecycleStatus, TerminalReason
from deerflow_deep_research.domain.node_spec import UNAVAILABLE_REAL_FACTORY, NodeBuildDependencies
from deerflow_deep_research.graph.nodes.rerun.fake import build_fake
from deerflow_deep_research.graph.nodes.rerun.node import build_real


class TestFullFakeRerunRegression:
    def test_fake_gen_0_bumps_to_1_routes_next(self) -> None:
        import asyncio

        state = {"generation": 0, "research_id": "r_" + "A" * 43}
        run = build_fake(
            NodeBuildDependencies(
                graph_context=object(),
                agent_context=object(),
                capabilities=object(),
            )
        )
        result = asyncio.run(run(state))
        assert result["generation"] == 1
        assert result["route"] == "next"
        # Fake: no scope fields
        assert "rerun_scope" not in result

    def test_fake_gen_1_bumps_to_2_routes_next(self) -> None:
        import asyncio

        state = {"generation": 1, "research_id": "r_" + "A" * 43}
        run = build_fake(
            NodeBuildDependencies(
                graph_context=object(),
                agent_context=object(),
                capabilities=object(),
            )
        )
        result = asyncio.run(run(state))
        assert result["generation"] == 2
        assert result["route"] == "next"

    def test_fake_gen_2_exhausted(self) -> None:
        import asyncio

        state = {"generation": 2, "research_id": "r_" + "A" * 43}
        run = build_fake(
            NodeBuildDependencies(
                graph_context=object(),
                agent_context=object(),
                capabilities=object(),
            )
        )
        result = asyncio.run(run(state))
        assert result["route"] == "exhausted"
        assert result["terminal_status"] == LifecycleStatus.BLOCKED.value
        assert result["terminal_reason"] == TerminalReason.RERUN_EXHAUSTED.value

    def test_fake_no_scope_no_invalidation_no_workspecs(self) -> None:
        import asyncio

        state = {
            "generation": 0,
            "research_id": "r_" + "A" * 43,
            "synthesis_ref": {"path": "x", "hash": "h_" + "A" * 43, "schema_version": 1},
            "repair_counts": {"wave0": 5},
        }
        run = build_fake(
            NodeBuildDependencies(
                graph_context=object(),
                agent_context=object(),
                capabilities=object(),
            )
        )
        result = asyncio.run(run(state))
        # Fake: no invalidation of synthesis_ref
        assert "synthesis_ref" not in result
        # Fake: repair_counts RESET to {} (fake behavior)
        assert result["repair_counts"] == {}


class TestRealNodeSpecContract:
    def test_build_real_no_longer_unavailable(self) -> None:
        """Real factory is no longer the sentinel."""
        assert build_real is not UNAVAILABLE_REAL_FACTORY

    def test_build_real_returns_callable(self) -> None:
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
                node_name="rerun",
                attempt_id="a1",
                workspace_root="/tmp/ws",
                attempt_root="/tmp/ws/rerun",
                policy_name="skeleton-rerun",
            ),
            capabilities=object(),
        )
        factory = build_real(deps)
        assert callable(factory)
