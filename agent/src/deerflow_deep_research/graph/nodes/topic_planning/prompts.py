"""Planner prompt helpers for real topic planning.

@impl TOP-001
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass

from deerflow_deep_research.domain.context import NodeExecutionRequest
from deerflow_deep_research.domain.topics import (
    MAX_TOPIC_BINDING_CHARS,
    MAX_TOPIC_DIMENSION_CHARS,
    MAX_TOPIC_DIMENSIONS,
    MAX_TOPIC_EXCLUSION_CHARS,
    MAX_TOPIC_EXCLUSIONS,
    MAX_TOPIC_SCOPE_CHARS,
    MAX_TOPIC_TITLE_CHARS,
    MAX_TOPICS,
    TOPIC_SCHEMA_VERSION,
    parse_plan_output,
)

MAX_PLANNER_OBJECTIVE_CHARS = 4_096


@dataclass(frozen=True)
class PlannerInputs:
    """The checkpointed profile constraints the planner consumes.

    Carries the HITL1 profile short fields plus ``request_text`` so the prompt
    builder signature stays stable as profile dimensions evolve.
    """

    request_text: str
    research_depth: str
    target_audience: str
    output_format: str
    cost_tolerance: str
    time_budget: str
    must_answer_questions: tuple[str, ...]
    degraded_profile: bool

    @property
    def coverage_questions(self) -> tuple[str, ...]:
        """Root questions every topic set must cover; falls back to the request."""
        questions = tuple(q for q in self.must_answer_questions if isinstance(q, str) and q.strip())
        return questions or (self.request_text.strip(),)

    @property
    def single_topic(self) -> bool:
        return (
            self.research_depth == "quick_overview"
            and self.cost_tolerance == "minimal"
            and self.time_budget == "very_quick"
        )


def _profile_payload(inputs: PlannerInputs) -> dict[str, object]:
    return {
        "request_text": inputs.request_text.strip(),
        "research_depth": inputs.research_depth,
        "target_audience": inputs.target_audience,
        "output_format": inputs.output_format,
        "cost_tolerance": inputs.cost_tolerance,
        "time_budget": inputs.time_budget,
        "must_answer_questions": list(inputs.coverage_questions),
        "degraded_profile": inputs.degraded_profile,
    }


def build_planner_prompt(inputs: PlannerInputs, *, repair_error: str | None = None) -> NodeExecutionRequest:
    """Build the bounded planner ``NodeExecutionRequest`` from profile constraints."""
    if not isinstance(inputs.request_text, str) or not inputs.request_text.strip():
        raise ValueError("request_text_required")
    single_topic = inputs.single_topic
    repair = ""
    if repair_error:
        repair = (
            f"\nA previous plan failed validation with: {repair_error[:240]}. "
            "Return a repaired plan that satisfies every requirement."
        )
    breadth = ""
    if inputs.degraded_profile:
        breadth = (
            "\nThe confirmed profile is degraded (incomplete). Propose broader, more "
            "conservative topics that still cover every must-answer question."
        )
    profile = json.dumps(_profile_payload(inputs), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    topic_instruction = (
        "Decompose the confirmed research profile into exactly one scoped research topic."
        if single_topic
        else "Decompose the confirmed research profile into a bounded set of scoped research topics."
    )
    objective = (
        f"{topic_instruction} Every must-answer question MUST be bound to at least one topic. Do not "
        "invent topic ids or slugs; the system derives them. Topics must be distinct and "
        "non-overlapping."
        f"{breadth}{repair}\n\nConfirmed profile:\n{profile}"
    )
    if len(objective) > MAX_PLANNER_OBJECTIVE_CHARS:
        objective = objective[:MAX_PLANNER_OBJECTIVE_CHARS]
    expected = {
        "instruction": "Return exactly one JSON object and no markdown, prose, or code fences.",
        "schema_version": TOPIC_SCHEMA_VERSION,
        "required_keys": ["schema_version", "topics"],
        "topic_required_keys": [
            "title",
            "scope",
            "must_answer_bindings",
            "search_dimensions",
            "exclusions",
        ],
        "bounds": {
            "topics": "exactly 1 entry" if single_topic else f"1-{MAX_TOPICS} entries",
            "must_answer_bindings": "1-8 strings drawn from the profile must_answer_questions",
            "title": f"<= {MAX_TOPIC_TITLE_CHARS} chars",
            "scope": f"<= {MAX_TOPIC_SCOPE_CHARS} chars",
            "search_dimensions": f"0-{MAX_TOPIC_DIMENSIONS} strings, each <= {MAX_TOPIC_DIMENSION_CHARS} chars",
            "exclusions": f"0-{MAX_TOPIC_EXCLUSIONS} strings, each <= {MAX_TOPIC_EXCLUSION_CHARS} chars",
            "must_answer_binding_chars": f"<= {MAX_TOPIC_BINDING_CHARS}",
        },
    }
    return NodeExecutionRequest(
        objective=objective,
        expected_output=json.dumps(expected, sort_keys=True, separators=(",", ":")),
    )


def planner_inputs_from_state(state: Mapping[str, object]) -> PlannerInputs:
    """Read the planner's checkpoint profile constraints from ``ResearchState``."""
    raw_questions = state.get("must_answer_questions") or ()
    if isinstance(raw_questions, (tuple, list)):
        questions = tuple(q for q in raw_questions if isinstance(q, str))
    else:
        questions = ()
    return PlannerInputs(
        request_text=str(state.get("request_text") or ""),
        research_depth=str(state.get("research_depth") or ""),
        target_audience=str(state.get("target_audience") or ""),
        output_format=str(state.get("output_format") or ""),
        cost_tolerance=str(state.get("cost_tolerance") or ""),
        time_budget=str(state.get("time_budget") or ""),
        must_answer_questions=questions,
        degraded_profile=bool(state.get("degraded_profile") or False),
    )


__all__ = [
    "MAX_PLANNER_OBJECTIVE_CHARS",
    "PlannerInputs",
    "build_planner_prompt",
    "parse_plan_output",
    "planner_inputs_from_state",
]
