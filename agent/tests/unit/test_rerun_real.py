"""Red tests for real rerun factory — full lifecycle orchestration.

@impl REN-001..007
"""

from __future__ import annotations

from deerflow_deep_research.domain.context import GraphContextView, NodeAgentContext
from deerflow_deep_research.domain.lifecycle import LifecycleStatus, TerminalReason
from deerflow_deep_research.domain.node_spec import NodeBuildDependencies
from deerflow_deep_research.domain.state import PhaseStatus
from deerflow_deep_research.graph.nodes.rerun.node import build_real


def _deps(**kwargs):
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
            node_name="rerun",
            attempt_id="g0-rerun-a1",
            workspace_root=graph.workspace_root,
            attempt_root=f"{graph.workspace_root}/rerun",
            policy_name="skeleton-rerun",
        ),
        capabilities=object(),
        **kwargs,
    )


def _state(**kwargs):
    return {
        "research_id": "r_" + "A" * 43,
        "generation": 0,
        "hitl2_rerun_payload": None,
        "synthesis_ref": {
            "path": "workspace/deep-research/r/synthesis/findings.json",
            "hash": "h_" + "A" * 43,
            "schema_version": 1,
        },
        "decision_brief_ref": {
            "path": "workspace/deep-research/r/review/decision-brief.md",
            "hash": "h_" + "B" * 43,
            "schema_version": 1,
        },
        "report_refs": (),
        "repair_counts": {"wave0": 1},
        "accepted_submission_refs": ("ref:1", "ref:2"),
        "topic_registry": (
            {"topic_id": "topic-a"},
            {"topic_id": "topic-b"},
        ),
        "gate_attempts_by_phase": {"wave0": 2, "wave1": 1},
        "repair_budget_by_phase": {"wave0": 3},
        "pending_work_ids": ("old-work",),
        "active_topic_filter": (),
        "execution_trace": (),
        **kwargs,
    }


class TestRealRerunFactory:
    def test_full_scope_full_lifecycle(self) -> None:
        import asyncio

        state = _state(
            hitl2_rerun_payload={"scope": "full", "reason": "rethink methodology"},
        )
        run = build_real(_deps())
        result = asyncio.run(run(state))

        assert result["generation"] == 1
        assert result["parent_generation"] == 0
        assert result["rerun_scope"] == "full"
        assert result["rerun_reason"] == "rethink methodology"
        assert result["route"] == "topic_planning"
        assert result["phase_status"] == PhaseStatus.WAITING.value
        # Invalidation
        assert result["synthesis_ref"] is None
        assert result["decision_brief_ref"] is None
        assert result["repair_counts"] == {}
        assert result["hitl2_rerun_payload"] is None
        # FULL: no pending work, empty filter
        assert result["pending_work_ids"] == ()
        assert result["active_topic_filter"] == ()
        # Gate state reset
        assert result["gate_attempts_by_phase"] == {}
        assert result["repair_budget_by_phase"] == {}

    def test_topic_scope_routes_to_wave0(self) -> None:
        import asyncio

        state = _state(
            hitl2_rerun_payload={
                "scope": "topic",
                "reason": "weak sources",
                "target_topic_ids": ["topic-b"],
            },
        )
        run = build_real(_deps())
        result = asyncio.run(run(state))

        assert result["generation"] == 1
        assert result["rerun_scope"] == "topic"
        assert result["route"] == "wave0"
        assert result["active_topic_filter"] == ("topic-b",)

    def test_finding_scope_defaults_to_wave0(self) -> None:
        import asyncio

        state = _state(
            hitl2_rerun_payload={
                "scope": "finding",
                "reason": "verify claims",
                "target_finding_ids": ["F-001"],
            },
        )
        run = build_real(_deps())
        result = asyncio.run(run(state))

        assert result["route"] == "wave0"
        assert result["rerun_scope"] == "finding"

    def test_generation_at_ceiling_exhausted(self) -> None:
        import asyncio

        state = _state(
            generation=2,
            hitl2_rerun_payload={"scope": "full", "reason": "last try"},
        )
        run = build_real(_deps(max_rerun_generations=2))
        result = asyncio.run(run(state))

        assert result["generation"] == 3
        assert result["route"] == "exhausted"
        assert result["terminal_status"] == LifecycleStatus.BLOCKED.value
        assert result["terminal_reason"] == TerminalReason.RERUN_EXHAUSTED.value

    def test_no_payload_defaults_to_full(self) -> None:
        import asyncio

        state = _state()  # hitl2_rerun_payload defaults to None
        run = build_real(_deps())
        result = asyncio.run(run(state))

        assert result["rerun_scope"] == "full"
        assert result["route"] == "topic_planning"

    def test_preserves_accepted_submissions(self) -> None:
        import asyncio

        state = _state(
            accepted_submission_refs=("ref:1", "ref:2", "ref:3"),
        )
        run = build_real(_deps())
        result = asyncio.run(run(state))
        # accepted_submission_refs is NOT in the returned update (unchanged)
        assert "accepted_submission_refs" not in result
