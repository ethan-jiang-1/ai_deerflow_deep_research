"""Red tests for Wave1 worker output contracts.

@impl WON-002
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from deerflow_deep_research.domain.wave1 import (
    OpenQuestionState,
    Wave1WorkerOutput,
)
from deerflow_deep_research.domain.work_units import canonical_json_bytes


class TestWave1WorkerOutput:
    def test_valid_empty_minimal(self) -> None:
        result = Wave1WorkerOutput(schema_version=1)
        assert result.schema_version == 1
        assert result.sources == ()
        assert result.claims == ()

    def test_valid_with_single_source_and_claim(self) -> None:
        result = Wave1WorkerOutput(
            schema_version=1,
            sources=(
                {
                    "source_id": "source:w1a",
                    "canonical_url": "https://example.com/a",
                    "title": "Example A",
                },
            ),
            claims=(
                {
                    "claim_id": "claim:w1_test001",
                    "statement": "A test claim.",
                    "support_refs": ("source:w1a",),
                    "counter_refs": (),
                },
            ),
        )
        assert result.source_ids == ("source:w1a",)
        assert result.claims[0].support_refs == ("source:w1a",)

    def test_source_ids_are_derived_when_omitted(self) -> None:
        result = Wave1WorkerOutput(
            schema_version=1,
            sources=(
                {
                    "source_id": "source:w1b",
                    "canonical_url": "https://example.com/b",
                    "title": "Old",
                },
            ),
        )
        assert result.source_ids == ("source:w1b",)

    def test_open_question_with_state(self) -> None:
        result = Wave1WorkerOutput(
            schema_version=1,
            open_questions=(
                {
                    "question_id": "q:w1_open001",
                    "question": "What about X?",
                    "state": "deferred",
                },
            ),
        )
        assert result.open_questions[0].state == OpenQuestionState.DEFERRED

    def test_rejects_unknown_field(self) -> None:
        with pytest.raises(ValidationError):
            Wave1WorkerOutput(schema_version=1, bogus="x")  # type: ignore[call-arg]

    def test_rejects_invalid_schema_version(self) -> None:
        with pytest.raises(ValidationError):
            Wave1WorkerOutput(schema_version=2)

    def test_rejects_mismatched_source_ids(self) -> None:
        with pytest.raises(ValidationError):
            Wave1WorkerOutput(
                schema_version=1,
                sources=(
                    {
                        "source_id": "source:w1a",
                        "canonical_url": "https://example.com/a",
                        "title": "A",
                    },
                ),
                source_ids=("source:w1b",),
            )

    def test_canonical_json_roundtrip(self) -> None:
        result = Wave1WorkerOutput(
            schema_version=1,
            sources=(
                {
                    "source_id": "source:w1c",
                    "canonical_url": "https://example.com/c",
                    "title": "C",
                },
            ),
            claims=(
                {
                    "claim_id": "claim:w1_c001",
                    "statement": "Claim C.",
                    "support_refs": ("source:w1c",),
                    "counter_refs": (),
                },
            ),
            open_questions=(
                {
                    "question_id": "q:w1_q001",
                    "question": "Unanswered.",
                    "state": "targeted_search",
                },
            ),
        )
        raw = canonical_json_bytes(result)
        reloaded = Wave1WorkerOutput.model_validate_json(raw)
        assert reloaded == result
