"""Tests for real readiness node.

@impl REA-001..007
"""

from __future__ import annotations

from deerflow_deep_research.domain.context import GraphContextView, NodeAgentContext
from deerflow_deep_research.domain.lifecycle import LifecycleStatus
from deerflow_deep_research.domain.node_spec import NodeBuildDependencies
from deerflow_deep_research.graph.nodes.readiness.node import build_real

LEDGER_HASH = "h_" + "A" * 43


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
            node_name="readiness",
            attempt_id="g0-readiness-a1",
            workspace_root=graph.workspace_root,
            attempt_root=f"{graph.workspace_root}/readiness",
            policy_name="skeleton-readiness",
        ),
        capabilities=object(),
    )


class TestRealReadiness:
    def test_all_clear_routes_pass(self) -> None:
        import asyncio

        state = {
            "research_id": "r_" + "A" * 43,
            "generation": 0,
            "accepted_submission_refs": ("h_" + "B" * 43, "h_" + "C" * 43),
            "must_answer_questions": ("Q1", "Q2"),
            "consumed_request_ids": ("req_001",),
        }
        result = asyncio.run(build_real(_deps())(state))
        assert result["route"] == "pass"
        assert result["phase"] == "readiness"
        assert result["readiness_blocked_count"] == 0
        assert result["readiness_report_plan"] is not None

    def test_canonical_ledger_hash_passes_provenance(self) -> None:
        import asyncio

        state = {
            "research_id": "r_" + "A" * 43,
            "generation": 0,
            "accepted_submission_refs": (LEDGER_HASH,),
            "must_answer_questions": ("Q1",),
            "consumed_request_ids": ("req_001",),
        }

        result = asyncio.run(build_real(_deps())(state))

        assert result["route"] == "pass"
        assert result["readiness_hard_failures"] == ()

    def test_no_evidence_routes_exhausted(self) -> None:
        import asyncio

        state = {
            "research_id": "r_" + "A" * 43,
            "generation": 0,
            "accepted_submission_refs": (),
            "must_answer_questions": (),
            "consumed_request_ids": (),
        }
        result = asyncio.run(build_real(_deps())(state))
        assert result["route"] == "exhausted"
        assert result["terminal_status"] == LifecycleStatus.BLOCKED.value
        assert len(result["readiness_hard_failures"]) >= 1

    def test_bad_ref_format_detected(self) -> None:
        import asyncio

        state = {
            "research_id": "r_" + "A" * 43,
            "generation": 0,
            "accepted_submission_refs": ("bad-format",),
            "must_answer_questions": (),
            "consumed_request_ids": ("req_001",),
        }
        result = asyncio.run(build_real(_deps())(state))
        failures = result["readiness_hard_failures"]
        assert any(f["code"] == "provenance_invalid_ref" for f in failures)

    def test_no_hitl2_consumption_detected(self) -> None:
        import asyncio

        state = {
            "research_id": "r_" + "A" * 43,
            "generation": 0,
            "accepted_submission_refs": (LEDGER_HASH,),
            "must_answer_questions": (),
            "consumed_request_ids": (),
        }
        result = asyncio.run(build_real(_deps())(state))
        failures = result["readiness_hard_failures"]
        assert any(f["code"] == "hitl2_not_consumed" for f in failures)

    def test_critic_fallback_produces_ready_substantive(self) -> None:
        import asyncio

        state = {
            "research_id": "r_" + "A" * 43,
            "generation": 0,
            "accepted_submission_refs": (LEDGER_HASH,),
            "must_answer_questions": ("Q1", "Q2"),
            "consumed_request_ids": ("req_001",),
        }
        result = asyncio.run(build_real(_deps())(state))
        critic = result["readiness_critic_summary"]
        assert len(critic["per_question"]) == 2
        assert all(pq["verdict"] == "ready_substantive" for pq in critic["per_question"])
        assert result["route"] == "pass"
