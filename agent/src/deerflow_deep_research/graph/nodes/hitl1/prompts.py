"""Prompt and compact-context helpers for real HITL1.

@impl HIN-001
@impl HIN-002
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from typing import Any

from deerflow_deep_research.domain.context import NodeExecutionRequest
from deerflow_deep_research.domain.profile import (
    CostTolerance,
    OutputFormat,
    PartialResearchProfile,
    ResearchDepth,
    StructuredBrief,
    TargetAudience,
    TimeBudget,
)

REQUIRED_DIMENSIONS = ("depth", "audience", "format", "cost_tolerance", "time_budget", "must_answer")
CONTEXT_SCHEMA_VERSION = 1
MAX_CONTEXT_CHARS = 2_048


def _enum_values(enum_type: type) -> list[str]:
    return [item.value for item in enum_type]


VALID_OPTIONS: dict[str, list[str]] = {
    "depth": _enum_values(ResearchDepth),
    "audience": _enum_values(TargetAudience),
    "format": _enum_values(OutputFormat),
    "cost_tolerance": _enum_values(CostTolerance),
    "time_budget": _enum_values(TimeBudget),
}


def build_brief_prompt(question: str, *, repair_error: str | None = None) -> NodeExecutionRequest:
    if not isinstance(question, str) or not question.strip():
        raise ValueError("question_required")
    repair = ""
    if repair_error:
        repair = f"\nPrevious output failed validation with: {repair_error[:240]}. Return a repaired object."
    objective = (
        "Draft a structured Deep Research intake brief from the user's original question. "
        "Use only the closed enum machine values listed in the expected output. "
        "The brief is advisory; the final profile will come from the human response."
        f"{repair}\n\nOriginal question:\n{question.strip()}"
    )
    expected = {
        "instruction": "Return exactly one JSON object and no markdown, prose, or code fences.",
        "schema_version": 1,
        "required_keys": [
            "schema_version",
            "brief_summary",
            "depth",
            "audience",
            "format",
            "cost_tolerance",
            "time_budget",
            "must_answer",
            "scope_boundaries",
            "custom_notes",
        ],
        "valid_options": VALID_OPTIONS,
        "bounds": {
            "brief_summary": "<=512 chars",
            "must_answer": "1-8 strings, each <=256 chars",
            "scope_boundaries": "<=2048 chars",
            "custom_notes": "<=1024 chars",
        },
    }
    return NodeExecutionRequest(
        objective=objective,
        expected_output=json.dumps(expected, sort_keys=True, separators=(",", ":")),
    )


def parse_brief_output(text: str) -> StructuredBrief:
    if not isinstance(text, str) or not text.strip():
        raise ValueError("brief_output_empty")
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError("brief_output_json_invalid") from exc
    if not isinstance(payload, dict):
        raise ValueError("brief_output_json_invalid")
    return StructuredBrief.model_validate(payload)


def _dump_compact(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    if len(encoded) <= MAX_CONTEXT_CHARS:
        return encoded
    compact = dict(payload)
    compact["brief_summary"] = str(compact.get("brief_summary", ""))[:240]
    compact["instructions"] = str(compact.get("instructions", ""))[:360]
    encoded = json.dumps(compact, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    if len(encoded) > MAX_CONTEXT_CHARS:
        raise ValueError("hitl_context_too_large")
    return encoded


def _dimension_payload(profile: StructuredBrief | PartialResearchProfile) -> dict[str, str]:
    payload: dict[str, str] = {}
    for field in ("depth", "audience", "format", "cost_tolerance", "time_budget"):
        value = getattr(profile, field)
        if value is not None:
            payload[field] = value.value if hasattr(value, "value") else str(value)
    return payload


def build_brief_context(brief: StructuredBrief, missing: Iterable[str] = REQUIRED_DIMENSIONS) -> str:
    payload = {
        "context_schema_version": CONTEXT_SCHEMA_VERSION,
        "brief_summary": brief.brief_summary,
        "proposed_dimensions": _dimension_payload(brief),
        "required_dimensions": list(REQUIRED_DIMENSIONS),
        "missing_dimensions": list(missing),
        "valid_options": VALID_OPTIONS,
        "instructions": (
            "Reply in JSON or concise text with values for depth, audience, format, "
            "cost_tolerance, time_budget, and at least one must_answer question."
        ),
    }
    return _dump_compact(payload)


def build_followup_context(partial: PartialResearchProfile, missing: Iterable[str]) -> str:
    missing_values = list(missing)
    payload = {
        "context_schema_version": CONTEXT_SCHEMA_VERSION,
        "brief_summary": "Additional profile details are required before research can proceed.",
        "proposed_dimensions": _dimension_payload(partial),
        "required_dimensions": list(REQUIRED_DIMENSIONS),
        "missing_dimensions": missing_values,
        "valid_options": VALID_OPTIONS,
        "instructions": "Please provide only these missing fields: " + ", ".join(missing_values) + ".",
    }
    return _dump_compact(payload)


__all__ = [
    "CONTEXT_SCHEMA_VERSION",
    "MAX_CONTEXT_CHARS",
    "REQUIRED_DIMENSIONS",
    "VALID_OPTIONS",
    "build_brief_context",
    "build_brief_prompt",
    "build_followup_context",
    "parse_brief_output",
]
