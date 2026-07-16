"""Red tests for max_rerun_generations policy and generation validation.

@impl REN-005
"""

from __future__ import annotations

import pytest

from deerflow_deep_research.domain.node_spec import NodeBuildDependencies
from deerflow_deep_research.domain.state import ResearchCheckpoint
from deerflow_deep_research.graph.nodes.rerun.fake import build_fake


class TestMaxRerunGenerationsPolicy:
    def test_node_build_dependencies_has_default(self) -> None:
        """NodeBuildDependencies carries max_rerun_generations with default 2."""
        from deerflow_deep_research.domain.context import GraphContextView, NodeAgentContext

        deps = NodeBuildDependencies(
            graph_context=GraphContextView(
                research_scope_id="r_" + "A" * 43,
                workspace_root="/tmp/ws",
                uploads_root="/tmp/up",
                outputs_root="/tmp/out",
            ),
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
        # Default should be 2 (from MAX_FAKE_RERUN_GENERATIONS)
        assert deps.max_rerun_generations == 2

    def test_node_build_dependencies_custom_value(self) -> None:
        """max_rerun_generations can be overridden."""
        from deerflow_deep_research.domain.context import GraphContextView, NodeAgentContext

        deps = NodeBuildDependencies(
            graph_context=GraphContextView(
                research_scope_id="r_" + "A" * 43,
                workspace_root="/tmp/ws",
                uploads_root="/tmp/up",
                outputs_root="/tmp/out",
            ),
            agent_context=NodeAgentContext(
                research_scope_id="r_" + "A" * 43,
                node_name="rerun",
                attempt_id="a1",
                workspace_root="/tmp/ws",
                attempt_root="/tmp/ws/rerun",
                policy_name="skeleton-rerun",
            ),
            capabilities=object(),
            max_rerun_generations=3,
        )
        assert deps.max_rerun_generations == 3


class TestGenerationValidation:
    def test_generation_0_valid(self) -> None:
        """Generation 0 is always valid."""
        ck = ResearchCheckpoint(
            research_id="r_" + "A" * 43,
            outer_thread_id="thread-1",
            generation=0,
        )
        assert ck.generation == 0

    def test_generation_1_valid(self) -> None:
        """Generation 1 is valid (first rerun)."""
        ck = ResearchCheckpoint(
            research_id="r_" + "A" * 43,
            outer_thread_id="thread-1",
            generation=1,
        )
        assert ck.generation == 1

    def test_generation_3_valid_no_longer_bounded(self) -> None:
        """Generation 3 is now valid — upper bound removed from __post_init__."""
        ck = ResearchCheckpoint(
            research_id="r_" + "A" * 43,
            outer_thread_id="thread-1",
            generation=3,
        )
        assert ck.generation == 3

    def test_generation_negative_raises(self) -> None:
        """Negative generation is still invalid."""
        with pytest.raises(ValueError, match="generation_invalid"):
            ResearchCheckpoint(
                research_id="r_" + "A" * 43,
                outer_thread_id="thread-1",
                generation=-1,
            )


class TestFakeRerunStillUsesConstant:
    def test_fake_at_generation_0_produces_route_next(self) -> None:
        """Fake rerun at gen 0 still uses MAX_FAKE_RERUN_GENERATIONS check."""
        import asyncio

        state = {
            "generation": 0,
            "research_id": "r_" + "A" * 43,
        }
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

    def test_fake_at_generation_2_exhausted(self) -> None:
        """Fake rerun at gen 2 (>= MAX_FAKE_RERUN_GENERATIONS) routes exhausted."""
        import asyncio

        state = {
            "generation": 2,
            "research_id": "r_" + "A" * 43,
        }
        run = build_fake(
            NodeBuildDependencies(
                graph_context=object(),
                agent_context=object(),
                capabilities=object(),
            )
        )
        result = asyncio.run(run(state))
        assert result["route"] == "exhausted"
