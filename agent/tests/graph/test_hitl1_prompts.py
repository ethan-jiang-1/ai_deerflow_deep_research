"""Prompt helpers for real HITL1.

@impl HIN-001
@impl HIN-002
"""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from deerflow_deep_research.domain.context import NodeExecutionRequest
from deerflow_deep_research.domain.profile import PartialResearchProfile, StructuredBrief
from deerflow_deep_research.graph.nodes.hitl1.prompts import (
    build_brief_prompt,
    build_followup_context,
    parse_brief_output,
)


def _brief_json(**overrides: object) -> str:
    payload: dict[str, object] = {
        "schema_version": 1,
        "brief_summary": "Compare grid-scale storage options with cost and maturity tradeoffs.",
        "depth": "standard",
        "audience": "practitioner",
        "format": "detailed_report",
        "cost_tolerance": "moderate",
        "time_budget": "standard",
        "must_answer": ["Which storage options are commercially mature?"],
        "scope_boundaries": "Grid-scale storage only.",
        "custom_notes": "",
    }
    payload.update(overrides)
    return json.dumps(payload)


def test_build_brief_prompt_includes_question_and_exact_json_contract() -> None:
    request = build_brief_prompt("Compare renewable energy storage technologies")
    assert isinstance(request, NodeExecutionRequest)
    assert "Compare renewable energy storage technologies" in request.objective
    assert "exactly one JSON object" in request.expected_output
    assert "quick_overview" in request.expected_output
    assert len(request.expected_output) <= 2048


def test_parse_brief_output_accepts_only_valid_structured_brief_json() -> None:
    brief = parse_brief_output(_brief_json())
    assert isinstance(brief, StructuredBrief)
    assert brief.depth == "standard"

    with pytest.raises(ValueError, match="brief_output_json_invalid"):
        parse_brief_output("not json")
    with pytest.raises(ValueError, match="brief_output_json_invalid"):
        parse_brief_output("[1, 2]")
    with pytest.raises(ValidationError):
        parse_brief_output(_brief_json(depth="invented"))
    with pytest.raises(ValidationError):
        parse_brief_output(_brief_json(brief_summary=None))


def test_followup_context_is_compact_json_with_stable_options_and_missing_fields() -> None:
    partial = PartialResearchProfile(depth="quick_overview", must_answer=("Q1",), custom_notes="x" * 1000)
    context = build_followup_context(partial, ("audience", "format", "cost_tolerance", "time_budget"))
    payload = json.loads(context)
    assert len(context) <= 2048
    assert payload["context_schema_version"] == 1
    assert payload["missing_dimensions"] == ["audience", "format", "cost_tolerance", "time_budget"]
    assert payload["required_dimensions"] == [
        "depth",
        "audience",
        "format",
        "cost_tolerance",
        "time_budget",
        "must_answer",
    ]
    assert payload["valid_options"]["depth"] == ["quick_overview", "standard", "deep_dive", "exhaustive"]
    assert "audience" in payload["instructions"]
