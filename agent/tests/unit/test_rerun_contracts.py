"""Red tests for rerun node contracts — RerunScope, RerunPlan.

@impl REN-001
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from deerflow_deep_research.domain.lifecycle import FrozenContract
from deerflow_deep_research.graph.nodes.rerun.contracts import RerunPlan, RerunScope


class TestRerunScope:
    def test_valid_full_scope(self) -> None:
        scope = RerunScope(
            scope="full",
            reason="rethink methodology",
            target_topic_ids=(),
            target_finding_ids=(),
            retain_topic_ids=(),
        )
        assert scope.scope == "full"
        assert scope.reason == "rethink methodology"
        assert scope.target_topic_ids == ()
        assert scope.target_finding_ids == ()
        assert scope.retain_topic_ids == ()

    def test_valid_topic_scope(self) -> None:
        scope = RerunScope(
            scope="topic",
            reason="weak sources for methodology",
            target_topic_ids=("methodology", "market-size"),
            target_finding_ids=(),
            retain_topic_ids=("competitors",),
        )
        assert scope.scope == "topic"
        assert scope.target_topic_ids == ("methodology", "market-size")
        assert scope.retain_topic_ids == ("competitors",)

    def test_valid_finding_scope(self) -> None:
        scope = RerunScope(
            scope="finding",
            reason="verify claims",
            target_topic_ids=(),
            target_finding_ids=("F-003", "F-007"),
            retain_topic_ids=("methodology",),
        )
        assert scope.scope == "finding"
        assert scope.target_finding_ids == ("F-003", "F-007")

    def test_invalid_scope_key_raises(self) -> None:
        with pytest.raises(ValidationError):
            RerunScope(
                scope="invalid",
                reason="test",
                target_topic_ids=(),
                target_finding_ids=(),
                retain_topic_ids=(),
            )

    def test_empty_reason_allowed(self) -> None:
        scope = RerunScope(
            scope="full",
            reason="",
            target_topic_ids=(),
            target_finding_ids=(),
            retain_topic_ids=(),
        )
        assert scope.reason == ""

    def test_is_frozen_contract(self) -> None:
        assert issubclass(RerunScope, FrozenContract)


class TestRerunPlan:
    def test_valid_full_rerun_plan(self) -> None:
        scope = RerunScope(
            scope="full",
            reason="rethink",
            target_topic_ids=(),
            target_finding_ids=(),
            retain_topic_ids=(),
        )
        plan = RerunPlan(
            generation=1,
            parent_generation=0,
            scope=scope,
            route="topic_planning",
        )
        assert plan.generation == 1
        assert plan.parent_generation == 0
        assert plan.scope is scope
        assert plan.route == "topic_planning"

    def test_valid_topic_rerun_plan(self) -> None:
        scope = RerunScope(
            scope="topic",
            reason="weak sources",
            target_topic_ids=("B",),
            target_finding_ids=(),
            retain_topic_ids=("A", "C"),
        )
        plan = RerunPlan(
            generation=2,
            parent_generation=1,
            scope=scope,
            route="wave0",
        )
        assert plan.route == "wave0"
        assert plan.generation == 2

    def test_valid_finding_rerun_plan(self) -> None:
        scope = RerunScope(
            scope="finding",
            reason="verify",
            target_topic_ids=(),
            target_finding_ids=("F-001",),
            retain_topic_ids=("A",),
        )
        plan = RerunPlan(
            generation=1,
            parent_generation=0,
            scope=scope,
            route="wave1",
        )
        assert plan.route == "wave1"

    def test_valid_exhausted_plan(self) -> None:
        scope = RerunScope(
            scope="full",
            reason="last try",
            target_topic_ids=(),
            target_finding_ids=(),
            retain_topic_ids=(),
        )
        plan = RerunPlan(
            generation=2,
            parent_generation=1,
            scope=scope,
            route="exhausted",
        )
        assert plan.route == "exhausted"

    def test_invalid_route_raises(self) -> None:
        scope = RerunScope(
            scope="full",
            reason="test",
            target_topic_ids=(),
            target_finding_ids=(),
            retain_topic_ids=(),
        )
        with pytest.raises(ValidationError):
            RerunPlan(
                generation=1,
                parent_generation=0,
                scope=scope,
                route="invalid_route",
            )

    def test_is_frozen_contract(self) -> None:
        assert issubclass(RerunPlan, FrozenContract)

    def test_generation_validation_is_at_checkpoint_level(self) -> None:
        """RerunPlan is an internal assembly artifact; generation >= 0 is
        enforced by ResearchCheckpoint, not by RerunPlan itself."""
        from deerflow_deep_research.domain.state import ResearchCheckpoint

        with pytest.raises(ValueError, match="generation_invalid"):
            ResearchCheckpoint(
                research_id="r_" + "A" * 43,
                outer_thread_id="thread-1",
                generation=-1,
            )
