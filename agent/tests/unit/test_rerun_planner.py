"""Red tests for rerun planner functions.

@impl REN-001, REN-002, REN-003, REN-004
"""

from __future__ import annotations

import pytest

from deerflow_deep_research.graph.nodes.rerun.contracts import RerunScope


class TestBuildRerunScope:
    def test_full_scope_from_payload(self) -> None:
        from deerflow_deep_research.graph.nodes.rerun.planner import build_rerun_scope

        state = {
            "hitl2_rerun_payload": {"scope": "full", "reason": "rethink methodology"},
            "topic_registry": (),
        }
        scope = build_rerun_scope(state)
        assert scope.scope == "full"
        assert scope.reason == "rethink methodology"
        assert scope.target_topic_ids == ()
        assert scope.retain_topic_ids == ()

    def test_topic_scope_with_named_targets(self) -> None:
        from deerflow_deep_research.graph.nodes.rerun.planner import build_rerun_scope

        state = {
            "hitl2_rerun_payload": {
                "scope": "topic",
                "reason": "weak sources",
                "target_topic_ids": ["methodology", "market-size"],
            },
            "topic_registry": (
                {"topic_id": "methodology"},
                {"topic_id": "market-size"},
                {"topic_id": "competitors"},
            ),
        }
        scope = build_rerun_scope(state)
        assert scope.scope == "topic"
        assert scope.target_topic_ids == ("methodology", "market-size")
        assert scope.retain_topic_ids == ("competitors",)

    def test_finding_scope_with_named_findings(self) -> None:
        from deerflow_deep_research.graph.nodes.rerun.planner import build_rerun_scope

        state = {
            "hitl2_rerun_payload": {
                "scope": "finding",
                "reason": "verify claims",
                "target_finding_ids": ["F-003", "F-007"],
            },
            "topic_registry": (),
        }
        scope = build_rerun_scope(state)
        assert scope.scope == "finding"
        assert scope.target_finding_ids == ("F-003", "F-007")

    def test_none_payload_defaults_to_full(self) -> None:
        from deerflow_deep_research.graph.nodes.rerun.planner import build_rerun_scope

        state = {
            "hitl2_rerun_payload": None,
            "topic_registry": (),
        }
        scope = build_rerun_scope(state)
        assert scope.scope == "full"

    def test_missing_payload_key_defaults_to_full(self) -> None:
        from deerflow_deep_research.graph.nodes.rerun.planner import build_rerun_scope

        state = {
            "topic_registry": (),
            # hitl2_rerun_payload not present
        }
        scope = build_rerun_scope(state)
        assert scope.scope == "full"

    def test_invalid_scope_key_raises(self) -> None:
        from deerflow_deep_research.graph.nodes.rerun.planner import build_rerun_scope

        state = {
            "hitl2_rerun_payload": {"scope": "nonexistent", "reason": ""},
            "topic_registry": (),
        }
        with pytest.raises(ValueError, match="invalid_rerun_scope"):
            build_rerun_scope(state)

    def test_invalid_target_topic_ids_default_to_full(self) -> None:
        from deerflow_deep_research.graph.nodes.rerun.planner import build_rerun_scope

        state = {
            "hitl2_rerun_payload": {
                "scope": "topic",
                "reason": "test",
                "target_topic_ids": ["nonexistent"],
            },
            "topic_registry": ({"topic_id": "real-topic"},),
        }
        scope = build_rerun_scope(state)
        assert scope.scope == "full"

    def test_returned_scope_does_not_contain_generation(self) -> None:
        from deerflow_deep_research.graph.nodes.rerun.planner import build_rerun_scope

        state = {
            "hitl2_rerun_payload": {"scope": "full", "reason": "test"},
            "topic_registry": (),
        }
        scope = build_rerun_scope(state)
        assert not hasattr(scope, "generation")


class TestApplyInvalidation:
    def test_clears_derived_refs(self) -> None:
        from deerflow_deep_research.graph.nodes.rerun.planner import apply_invalidation

        scope = RerunScope(scope="full", reason="test")
        result = apply_invalidation(scope)
        assert result["synthesis_ref"] is None
        assert result["decision_brief_ref"] is None
        assert result["report_refs"] == ()
        assert result["repair_counts"] == {}
        assert result["hitl2_rerun_payload"] is None

    def test_does_not_change_passed_dict(self) -> None:
        """apply_invalidation returns a new dict, doesn't mutate input."""
        from deerflow_deep_research.graph.nodes.rerun.planner import apply_invalidation

        scope = RerunScope(scope="full", reason="test")
        result = apply_invalidation(scope)
        assert "synthesis_ref" in result
        # The function returns a new dict; doesn't mutate input


class TestApplyGenerationIncrement:
    def test_increments_from_0_to_1(self) -> None:
        from deerflow_deep_research.graph.nodes.rerun.planner import apply_generation_increment

        state = {"generation": 0}
        result = apply_generation_increment(state)
        assert result["generation"] == 1
        assert result["parent_generation"] == 0

    def test_increments_from_1_to_2(self) -> None:
        from deerflow_deep_research.graph.nodes.rerun.planner import apply_generation_increment

        state = {"generation": 1}
        result = apply_generation_increment(state)
        assert result["generation"] == 2
        assert result["parent_generation"] == 1


class TestDetermineRerunRoute:
    def test_full_to_topic_planning(self) -> None:
        from deerflow_deep_research.graph.nodes.rerun.planner import determine_rerun_route

        scope = RerunScope(scope="full", reason="test")
        route = determine_rerun_route(scope, generation=1, max_rerun_generations=2)
        assert route == "topic_planning"

    def test_topic_to_wave0(self) -> None:
        from deerflow_deep_research.graph.nodes.rerun.planner import determine_rerun_route

        scope = RerunScope(scope="topic", reason="test", target_topic_ids=("B",), retain_topic_ids=("A", "C"))
        route = determine_rerun_route(scope, generation=1, max_rerun_generations=2)
        assert route == "wave0"

    def test_finding_stale_sources_to_wave0(self) -> None:
        from deerflow_deep_research.graph.nodes.rerun.planner import determine_rerun_route

        scope = RerunScope(scope="finding", reason="test", target_finding_ids=("F-001",))
        # Default: ambiguous → wave0 (conservative)
        route = determine_rerun_route(scope, generation=1, max_rerun_generations=2)
        assert route == "wave0"

    def test_generation_at_ceiling_exhausted(self) -> None:
        from deerflow_deep_research.graph.nodes.rerun.planner import determine_rerun_route

        scope = RerunScope(scope="full", reason="last try")
        route = determine_rerun_route(scope, generation=2, max_rerun_generations=2)
        assert route == "exhausted"

    def test_generation_below_ceiling_not_exhausted(self) -> None:
        from deerflow_deep_research.graph.nodes.rerun.planner import determine_rerun_route

        scope = RerunScope(scope="full", reason="test")
        route = determine_rerun_route(scope, generation=1, max_rerun_generations=2)
        assert route != "exhausted"


class TestGateStateReset:
    def test_resets_gate_state_for_all_phases(self) -> None:
        from deerflow_deep_research.graph.nodes.rerun.planner import reset_gate_state_for_scope

        state = {
            "gate_attempts_by_phase": {"wave0": 2, "wave1": 3, "wave2_synthesis": 1},
            "repair_budget_by_phase": {"wave0": 3, "wave1": 1},
        }
        scope = RerunScope(scope="full", reason="test")
        result = reset_gate_state_for_scope(state, scope)
        # FULL: all phases reset
        assert result["gate_attempts_by_phase"] == {}
        assert result["repair_budget_by_phase"] == {}
