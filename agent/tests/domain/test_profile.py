"""HITL1 research profile domain contracts.

@impl HIN-001
@impl HIN-003
"""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from deerflow_deep_research.domain.profile import (
    CostTolerance,
    OutputFormat,
    PartialResearchProfile,
    ResearchDepth,
    ResearchProfile,
    StructuredBrief,
    TargetAudience,
    TimeBudget,
    canonical_profile_json,
    finalize_profile,
    merge_profile_progress,
    missing_dimensions,
    parse_profile_response,
)


def _complete_profile(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "depth": "standard",
        "audience": "practitioner",
        "format": "detailed_report",
        "cost_tolerance": "moderate",
        "time_budget": "standard",
        "must_answer": ("What matters most?",),
        "scope_boundaries": "Use grid-scale deployment only.",
        "custom_notes": "Prefer recent sources.",
    }
    payload.update(overrides)
    return payload


def test_closed_enums_are_stable_machine_values() -> None:
    assert {item.value for item in ResearchDepth} == {
        "quick_overview",
        "standard",
        "deep_dive",
        "exhaustive",
    }
    assert {item.value for item in TargetAudience} == {
        "layperson",
        "practitioner",
        "domain_expert",
        "executive",
    }
    assert {item.value for item in OutputFormat} == {
        "executive_brief",
        "detailed_report",
        "annotated_bibliography",
        "faq",
    }
    assert {item.value for item in CostTolerance} == {"minimal", "moderate", "extensive"}
    assert {item.value for item in TimeBudget} == {"very_quick", "standard", "thorough", "overnight"}


def test_profile_contracts_are_frozen_extra_forbid_and_schema_version_one() -> None:
    brief = StructuredBrief(
        brief_summary="A scoped research request.",
        **_complete_profile(),
    )
    assert brief.schema_version == 1
    with pytest.raises(ValidationError):
        StructuredBrief(brief_summary="x", unexpected=True, **_complete_profile())
    with pytest.raises(ValidationError):
        brief.brief_summary = "changed"  # type: ignore[misc]

    partial = PartialResearchProfile(depth="quick_overview")
    assert partial.schema_version == 1
    with pytest.raises(ValidationError):
        partial.depth = ResearchDepth.STANDARD  # type: ignore[misc]


def test_profile_bounds_and_final_completeness() -> None:
    profile = ResearchProfile(**_complete_profile(must_answer=["Q1", "Q2"]))
    assert profile.must_answer == ("Q1", "Q2")

    with pytest.raises(ValidationError, match="must_answer"):
        ResearchProfile(**_complete_profile(must_answer=[]))
    with pytest.raises(ValidationError, match="must_answer"):
        ResearchProfile(**_complete_profile(must_answer=["x" * 257]))
    with pytest.raises(ValidationError):
        ResearchProfile(**_complete_profile(scope_boundaries="x" * 2049))
    with pytest.raises(ValidationError):
        ResearchProfile(**_complete_profile(custom_notes="x" * 1025))
    with pytest.raises(ValidationError, match="profile_incomplete"):
        ResearchProfile(depth="standard", must_answer=("Q1",))

    degraded = ResearchProfile(depth="standard", must_answer=("Q1",), degraded_profile=True)
    assert degraded.degraded_profile is True
    assert missing_dimensions(degraded) == ("audience", "format", "cost_tolerance", "time_budget")


def test_canonical_profile_json_is_stable_and_rejects_wrong_type() -> None:
    profile = ResearchProfile(**_complete_profile())
    encoded = canonical_profile_json(profile)
    assert encoded == json.dumps(json.loads(encoded), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    assert json.loads(encoded)["schema_version"] == 1
    with pytest.raises(TypeError, match="profile_required"):
        canonical_profile_json(PartialResearchProfile(depth="standard"))  # type: ignore[arg-type]


def test_parse_profile_response_accepts_json_and_ignores_unknown_enum_values() -> None:
    parsed = parse_profile_response(
        json.dumps(
            {
                "depth": "superficial",
                "target_audience": "domain_expert",
                "output_format": "annotated_bibliography",
                "cost_tolerance": "extensive",
                "time_budget": "overnight",
                "must_answer_questions": ["Q1"],
            }
        )
    )
    assert parsed.depth is None
    assert parsed.audience is TargetAudience.DOMAIN_EXPERT
    assert parsed.format is OutputFormat.ANNOTATED_BIBLIOGRAPHY
    assert parsed.cost_tolerance is CostTolerance.EXTENSIVE
    assert parsed.time_budget is TimeBudget.OVERNIGHT
    assert parsed.must_answer == ("Q1",)

    with pytest.raises(ValueError, match="profile_response_json_invalid"):
        parse_profile_response("[1, 2]")
    with pytest.raises(ValueError, match="profile_response_extra_fields"):
        parse_profile_response('{"depth":"standard","host_path":"/tmp/x"}')


def test_parse_profile_response_is_deterministic_for_free_text() -> None:
    parsed = parse_profile_response(
        "standard depth, for practitioners, detailed report, moderate cost, standard time; must answer: Q1 and Q2"
    )
    assert parsed == PartialResearchProfile(
        depth=ResearchDepth.STANDARD,
        audience=TargetAudience.PRACTITIONER,
        format=OutputFormat.DETAILED_REPORT,
        cost_tolerance=CostTolerance.MODERATE,
        time_budget=TimeBudget.STANDARD,
        must_answer=("Q1", "Q2"),
    )

    unknown = parse_profile_response("depth=superficial; must answer: Q1")
    assert unknown.depth is None
    assert unknown.must_answer == ("Q1",)


def test_merge_and_finalize_profile_progress() -> None:
    current = PartialResearchProfile(depth="quick_overview", must_answer=("Old",))
    incoming = PartialResearchProfile(audience="layperson", must_answer=("New",))
    merged = merge_profile_progress(current, incoming)
    assert merged.depth is ResearchDepth.QUICK_OVERVIEW
    assert merged.audience is TargetAudience.LAYPERSON
    assert merged.must_answer == ("New",)
    with pytest.raises(ValidationError, match="profile_incomplete"):
        finalize_profile(merged)
    assert finalize_profile(merged, degraded=True).degraded_profile is True
