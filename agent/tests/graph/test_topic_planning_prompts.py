"""Topic planning planner prompt helpers.

@impl TOP-001
"""

from __future__ import annotations

import json
from dataclasses import replace

import pytest

from deerflow_deep_research.domain.context import NodeExecutionRequest
from deerflow_deep_research.graph.nodes.topic_planning.prompts import (
    PlannerInputs,
    build_planner_prompt,
    parse_plan_output,
    planner_inputs_from_state,
)


def _inputs() -> PlannerInputs:
    return PlannerInputs(
        request_text="Compare storage options",
        research_depth="deep_dive",
        target_audience="domain_expert",
        output_format="annotated_bibliography",
        cost_tolerance="extensive",
        time_budget="overnight",
        must_answer_questions=("Q1", "Q2"),
        degraded_profile=False,
    )


def test_build_planner_prompt_carries_profile_constraints() -> None:
    request = build_planner_prompt(_inputs())
    assert isinstance(request, NodeExecutionRequest)
    assert "Compare storage options" in request.objective
    assert "deep_dive" in request.objective
    assert "Q1" in request.objective
    expected = json.loads(request.expected_output)
    assert expected["instruction"].startswith("Return exactly one JSON object")
    assert "topics" in expected["required_keys"]
    assert "must_answer_bindings" in expected["topic_required_keys"]


def test_very_quick_overview_limits_plan_to_one_topic() -> None:
    request = build_planner_prompt(
        replace(
            _inputs(),
            research_depth="quick_overview",
            cost_tolerance="minimal",
            time_budget="very_quick",
        )
    )

    assert "exactly one scoped research topic" in request.objective.lower()
    assert json.loads(request.expected_output)["bounds"]["topics"] == "exactly 1 entry"


def test_build_planner_prompt_requires_request_text() -> None:
    with pytest.raises(ValueError, match="request_text_required"):
        build_planner_prompt(replace(_inputs(), request_text="   "))


def test_degraded_profile_broadens_the_plan() -> None:
    request = build_planner_prompt(replace(_inputs(), degraded_profile=True))
    lowered = request.objective.lower()
    assert "broader" in lowered or "conservative" in lowered


def test_repair_prompt_carries_failure_metadata() -> None:
    request = build_planner_prompt(_inputs(), repair_error="topic_coverage_uncovered:Q2")
    assert "previous plan failed validation" in request.objective.lower()


def test_empty_must_answer_falls_back_to_request_text() -> None:
    inputs = replace(_inputs(), must_answer_questions=())
    assert inputs.coverage_questions == ("Compare storage options",)
    request = build_planner_prompt(inputs)
    assert "Compare storage options" in request.objective


def test_parse_plan_output_round_trip_and_rejects_invalid() -> None:
    plan = parse_plan_output(
        json.dumps(
            {
                "schema_version": 1,
                "topics": [{"title": "T", "scope": "S", "must_answer_bindings": ["Q1"]}],
            }
        )
    )
    assert len(plan.topics) == 1
    with pytest.raises(ValueError, match="topic_plan_json_invalid"):
        parse_plan_output("not json")
    with pytest.raises(ValueError, match="topic_plan_empty"):
        parse_plan_output("   ")


def test_planner_inputs_from_state_reads_profile_fields() -> None:
    inputs = planner_inputs_from_state(
        {
            "request_text": "X",
            "research_depth": "standard",
            "target_audience": "practitioner",
            "output_format": "detailed_report",
            "cost_tolerance": "moderate",
            "time_budget": "standard",
            "must_answer_questions": ["Q1", "Q2"],
            "degraded_profile": True,
        }
    )
    assert inputs.research_depth == "standard"
    assert inputs.must_answer_questions == ("Q1", "Q2")
    assert inputs.degraded_profile is True
    assert inputs.coverage_questions == ("Q1", "Q2")
