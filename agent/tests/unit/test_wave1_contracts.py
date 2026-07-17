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

    def test_provider_ids_and_question_state_are_normalized(self) -> None:
        result = Wave1WorkerOutput(
            schema_version=1,
            claims=(
                {
                    "claim_id": "claim 1",
                    "statement": "A provider-shaped claim.",
                    "support_refs": (),
                    "counter_refs": (),
                },
            ),
            open_questions=(
                {
                    "question_id": "question 1",
                    "question": "What remains unknown?",
                    "state": "needs_more_research",
                },
            ),
        )

        assert result.claims[0].claim_id == "claim:w1_claim_1"
        assert result.open_questions[0].question_id == "q:w1_question_1"
        assert result.open_questions[0].state is OpenQuestionState.TARGETED_SEARCH

    def test_provider_source_ids_and_claim_refs_are_normalized_together(self) -> None:
        result = Wave1WorkerOutput(
            schema_version=1,
            sources=(
                {
                    "source_id": "Source 1 / official",
                    "canonical_url": "https://example.com/source-1",
                    "title": "Official source",
                },
            ),
            claims=(
                {
                    "claim_id": "claim 1",
                    "statement": "A provider-shaped claim.",
                    "support_refs": ("Source 1 / official",),
                    "counter_refs": (),
                },
            ),
        )

        assert result.sources[0].source_id == "source:w1_Source_1_official"
        assert result.source_ids == ("source:w1_Source_1_official",)
        assert result.claims[0].support_refs == ("source:w1_Source_1_official",)

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
