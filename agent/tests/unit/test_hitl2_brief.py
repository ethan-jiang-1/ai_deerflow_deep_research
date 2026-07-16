"""Red tests for HITL2 deterministic brief builder.

@impl HIT-001
"""

from __future__ import annotations

from deerflow_deep_research.graph.nodes.hitl2.prompts import build_hitl2_brief


class TestBuildHitl2Brief:
    def test_returns_dict_with_expected_keys(self) -> None:
        state = {
            "accepted_submission_refs": ("ref:1", "ref:2"),
            "synthesis_gaps": (
                {"gap_id": "gap:1", "description": "Missing X", "priority": 3, "search_required": True},
            ),
        }
        brief = build_hitl2_brief(state)
        assert isinstance(brief, dict)
        assert "confirmed_count" in brief
        assert "pending_gaps" in brief
        assert "available_actions" in brief

    def test_empty_state_produces_honest_brief(self) -> None:
        state = {}
        brief = build_hitl2_brief(state)
        assert brief["confirmed_count"] == 0
        assert brief["pending_gaps"] == 0

    def test_brief_includes_available_actions(self) -> None:
        state = {"accepted_submission_refs": ("ref:1",)}
        brief = build_hitl2_brief(state)
        actions = brief["available_actions"]
        assert "proceed" in actions
        assert "stop" in actions

    def test_brief_counts_gaps_correctly(self) -> None:
        state = {
            "accepted_submission_refs": ("a", "b", "c"),
            "synthesis_gaps": (
                {"gap_id": "g1", "description": "x", "priority": 1, "search_required": True},
                {"gap_id": "g2", "description": "y", "priority": 5, "search_required": False},
                {"gap_id": "g3", "description": "z", "priority": 3, "search_required": True},
            ),
        }
        brief = build_hitl2_brief(state)
        assert brief["confirmed_count"] == 3
        assert brief["pending_gaps"] == 3
