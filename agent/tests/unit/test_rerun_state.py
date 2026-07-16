"""Red tests for rerun-related state fields on ResearchCheckpoint.

@impl REN-001, REN-002, REN-003
"""

from __future__ import annotations

from deerflow_deep_research.domain.state import ResearchCheckpoint


class TestRerunStateFields:
    def test_hitl2_rerun_payload_defaults_to_none(self) -> None:
        ck = ResearchCheckpoint(
            research_id="r_" + "A" * 43,
            outer_thread_id="thread-1",
            generation=0,
        )
        assert ck.hitl2_rerun_payload is None

    def test_rerun_scope_defaults_to_empty(self) -> None:
        ck = ResearchCheckpoint(
            research_id="r_" + "A" * 43,
            outer_thread_id="thread-1",
            generation=0,
        )
        assert ck.rerun_scope == ""

    def test_rerun_reason_defaults_to_empty(self) -> None:
        ck = ResearchCheckpoint(
            research_id="r_" + "A" * 43,
            outer_thread_id="thread-1",
            generation=0,
        )
        assert ck.rerun_reason == ""

    def test_parent_generation_defaults_to_minus_one(self) -> None:
        ck = ResearchCheckpoint(
            research_id="r_" + "A" * 43,
            outer_thread_id="thread-1",
            generation=0,
        )
        assert ck.parent_generation == -1

    def test_active_topic_filter_defaults_to_empty(self) -> None:
        ck = ResearchCheckpoint(
            research_id="r_" + "A" * 43,
            outer_thread_id="thread-1",
            generation=0,
        )
        assert ck.active_topic_filter == ()

    def test_hitl2_rerun_payload_can_be_set(self) -> None:
        ck = ResearchCheckpoint(
            research_id="r_" + "A" * 43,
            outer_thread_id="thread-1",
            generation=0,
            hitl2_rerun_payload={"scope": "topic", "reason": "weak sources", "target_topic_ids": ["B"]},
        )
        assert ck.hitl2_rerun_payload == {"scope": "topic", "reason": "weak sources", "target_topic_ids": ["B"]}

    def test_active_topic_filter_can_be_set(self) -> None:
        ck = ResearchCheckpoint(
            research_id="r_" + "A" * 43,
            outer_thread_id="thread-1",
            generation=0,
            active_topic_filter=("topic-a", "topic-b"),
        )
        assert ck.active_topic_filter == ("topic-a", "topic-b")

    def test_fields_roundtrip_through_serialization(self) -> None:
        """New fields survive a serialization roundtrip."""

        ck = ResearchCheckpoint(
            research_id="r_" + "A" * 43,
            outer_thread_id="thread-1",
            generation=1,
            parent_generation=0,
            rerun_scope="full",
            rerun_reason="test reason",
            active_topic_filter=("B",),
            hitl2_rerun_payload={"scope": "full", "reason": "test"},
        )
        # Serialize via dataclass asdict
        from dataclasses import asdict

        data = asdict(ck)
        # Reconstruct
        reconstructed = ResearchCheckpoint(**data)
        assert reconstructed.generation == 1
        assert reconstructed.parent_generation == 0
        assert reconstructed.rerun_scope == "full"
        assert reconstructed.rerun_reason == "test reason"
        assert reconstructed.active_topic_filter == ("B",)
        assert reconstructed.hitl2_rerun_payload == {"scope": "full", "reason": "test"}
