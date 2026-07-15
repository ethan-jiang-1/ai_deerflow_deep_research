"""Pure HITL1 research-profile contracts.

@impl HIN-001
@impl HIN-003
@impl HIN-004
"""

from __future__ import annotations

import base64
import hashlib
import json
import re
from collections.abc import Mapping
from enum import StrEnum
from typing import Any, Literal, Protocol, runtime_checkable

from pydantic import ConfigDict, Field, field_validator, model_validator

from deerflow_deep_research.domain.lifecycle import FrozenContract
from deerflow_deep_research.domain.state import ContentRef

MAX_MUST_ANSWER = 8
MAX_QUESTION_CHARS = 256
MAX_SCOPE_CHARS = 2_048
MAX_NOTES_CHARS = 1_024
MAX_BRIEF_SUMMARY_CHARS = 512
PROFILE_SCHEMA_VERSION = 1


class ResearchDepth(StrEnum):
    QUICK_OVERVIEW = "quick_overview"
    STANDARD = "standard"
    DEEP_DIVE = "deep_dive"
    EXHAUSTIVE = "exhaustive"


class TargetAudience(StrEnum):
    LAYPERSON = "layperson"
    PRACTITIONER = "practitioner"
    DOMAIN_EXPERT = "domain_expert"
    EXECUTIVE = "executive"


class OutputFormat(StrEnum):
    EXECUTIVE_BRIEF = "executive_brief"
    DETAILED_REPORT = "detailed_report"
    ANNOTATED_BIBLIOGRAPHY = "annotated_bibliography"
    FAQ = "faq"


class CostTolerance(StrEnum):
    MINIMAL = "minimal"
    MODERATE = "moderate"
    EXTENSIVE = "extensive"


class TimeBudget(StrEnum):
    VERY_QUICK = "very_quick"
    STANDARD = "standard"
    THOROUGH = "thorough"
    OVERNIGHT = "overnight"


_DIMENSION_FIELDS = ("depth", "audience", "format", "cost_tolerance", "time_budget")
_REQUIRED_FIELDS = (*_DIMENSION_FIELDS, "must_answer")


class _ProfileBase(FrozenContract):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal[1] = PROFILE_SCHEMA_VERSION
    must_answer: tuple[str, ...] = Field(default=(), max_length=MAX_MUST_ANSWER)
    scope_boundaries: str = Field(default="", max_length=MAX_SCOPE_CHARS)
    custom_notes: str = Field(default="", max_length=MAX_NOTES_CHARS)

    @field_validator("must_answer", mode="before")
    @classmethod
    def normalize_questions(cls, value: Any) -> tuple[str, ...]:
        if value is None:
            return ()
        if isinstance(value, str):
            value = (value,)
        if not isinstance(value, (tuple, list)):
            raise ValueError("must_answer_invalid")
        normalized: list[str] = []
        for item in value:
            if not isinstance(item, str):
                raise ValueError("must_answer_invalid")
            text = item.strip()
            if not text or len(text) > MAX_QUESTION_CHARS:
                raise ValueError("must_answer_invalid")
            normalized.append(text)
        if len(normalized) > MAX_MUST_ANSWER:
            raise ValueError("must_answer_invalid")
        return tuple(normalized)


class StructuredBrief(_ProfileBase):
    brief_summary: str = Field(min_length=1, max_length=MAX_BRIEF_SUMMARY_CHARS)
    depth: ResearchDepth
    audience: TargetAudience
    format: OutputFormat
    cost_tolerance: CostTolerance
    time_budget: TimeBudget
    must_answer: tuple[str, ...] = Field(min_length=1, max_length=MAX_MUST_ANSWER)


class PartialResearchProfile(_ProfileBase):
    depth: ResearchDepth | None = None
    audience: TargetAudience | None = None
    format: OutputFormat | None = None
    cost_tolerance: CostTolerance | None = None
    time_budget: TimeBudget | None = None


class ResearchProfile(PartialResearchProfile):
    degraded_profile: bool = False

    @model_validator(mode="after")
    def require_complete_profile_unless_degraded(self) -> ResearchProfile:
        if self.degraded_profile:
            return self
        missing = missing_dimensions(self)
        if missing:
            raise ValueError(f"profile_incomplete:{','.join(missing)}")
        return self


@runtime_checkable
class RequestBundleStoreProtocol(Protocol):
    async def write_profile(self, profile: ResearchProfile) -> ContentRef: ...


def _canonical_value(value: Any) -> Any:
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, FrozenContract):
        return _canonical_value(value.model_dump(mode="python"))
    if isinstance(value, Mapping):
        return {str(key): _canonical_value(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_canonical_value(item) for item in value]
    return value


def canonical_profile_bytes(profile: ResearchProfile) -> bytes:
    if not isinstance(profile, ResearchProfile):
        raise TypeError("profile_required")
    return json.dumps(
        _canonical_value(profile),
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def canonical_profile_json(profile: ResearchProfile) -> str:
    return canonical_profile_bytes(profile).decode("utf-8")


def compute_profile_content_hash(profile: ResearchProfile) -> str:
    digest = hashlib.sha256(canonical_profile_bytes(profile)).digest()
    return "h_" + base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def missing_dimensions(profile: PartialResearchProfile | ResearchProfile) -> tuple[str, ...]:
    missing = [field for field in _DIMENSION_FIELDS if getattr(profile, field) is None]
    if not profile.must_answer:
        missing.append("must_answer")
    return tuple(missing)


def merge_profile_progress(
    current: PartialResearchProfile | Mapping[str, Any] | None,
    incoming: PartialResearchProfile | Mapping[str, Any],
) -> PartialResearchProfile:
    base = PartialResearchProfile.model_validate(current or {})
    update = (
        incoming if isinstance(incoming, PartialResearchProfile) else PartialResearchProfile.model_validate(incoming)
    )
    payload = base.model_dump(mode="python")
    for field in _DIMENSION_FIELDS:
        value = getattr(update, field)
        if value is not None:
            payload[field] = value
    if update.must_answer:
        payload["must_answer"] = update.must_answer
    if update.scope_boundaries:
        payload["scope_boundaries"] = update.scope_boundaries
    if update.custom_notes:
        payload["custom_notes"] = update.custom_notes
    return PartialResearchProfile.model_validate(payload)


def finalize_profile(profile: PartialResearchProfile | Mapping[str, Any], *, degraded: bool = False) -> ResearchProfile:
    progress = (
        profile if isinstance(profile, PartialResearchProfile) else PartialResearchProfile.model_validate(profile)
    )
    return ResearchProfile.model_validate(progress.model_dump(mode="python") | {"degraded_profile": degraded})


def profile_state_fields(profile: ResearchProfile, profile_ref: ContentRef) -> dict[str, Any]:
    if not isinstance(profile_ref, ContentRef):
        raise TypeError("profile_ref_required")
    return {
        "profile_ref": profile_ref,
        "research_depth": profile.depth.value if profile.depth is not None else "",
        "target_audience": profile.audience.value if profile.audience is not None else "",
        "output_format": profile.format.value if profile.format is not None else "",
        "cost_tolerance": profile.cost_tolerance.value if profile.cost_tolerance is not None else "",
        "time_budget": profile.time_budget.value if profile.time_budget is not None else "",
        "must_answer_questions": profile.must_answer,
        "degraded_profile": profile.degraded_profile,
        "pending_profile": None,
        "profile_followup_round": 0,
    }


_ENUMS: dict[str, type[StrEnum]] = {
    "depth": ResearchDepth,
    "audience": TargetAudience,
    "format": OutputFormat,
    "cost_tolerance": CostTolerance,
    "time_budget": TimeBudget,
}

_JSON_ALIASES = {
    "research_depth": "depth",
    "target_audience": "audience",
    "output_format": "format",
    "must_answer_questions": "must_answer",
}

_TEXT_SYNONYMS: dict[str, dict[str, tuple[str, ...]]] = {
    "depth": {
        "quick_overview": ("quick overview", "quick_overview", "brief overview"),
        "standard": ("standard depth", "standard-depth", "standard"),
        "deep_dive": ("deep dive", "deep_dive"),
        "exhaustive": ("exhaustive",),
    },
    "audience": {
        "layperson": ("layperson", "general audience", "non expert", "non-expert"),
        "practitioner": ("practitioner", "practitioners"),
        "domain_expert": ("domain expert", "domain_expert", "expert audience"),
        "executive": ("executive", "executives"),
    },
    "format": {
        "executive_brief": ("executive brief", "executive_brief"),
        "detailed_report": ("detailed report", "detailed_report"),
        "annotated_bibliography": ("annotated bibliography", "annotated_bibliography"),
        "faq": ("faq", "q&a", "q and a"),
    },
    "cost_tolerance": {
        "minimal": ("minimal cost", "minimal"),
        "moderate": ("moderate cost", "moderate"),
        "extensive": ("extensive cost", "extensive"),
    },
    "time_budget": {
        "very_quick": ("very quick", "very_quick"),
        "standard": ("standard time", "standard timeline", "standard"),
        "thorough": ("thorough",),
        "overnight": ("overnight",),
    },
}


def _enum_or_none(enum_type: type[StrEnum], value: Any) -> StrEnum | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip().lower().replace(" ", "_").replace("-", "_")
    try:
        return enum_type(normalized)
    except ValueError:
        return None


def _parse_json_response(text: str) -> dict[str, Any]:
    try:
        raw = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError("profile_response_json_invalid") from exc
    if not isinstance(raw, dict):
        raise ValueError("profile_response_json_invalid")
    allowed = set(_REQUIRED_FIELDS) | {"scope_boundaries", "custom_notes", "schema_version"} | set(_JSON_ALIASES)
    extra = set(raw) - allowed
    if extra:
        raise ValueError("profile_response_extra_fields")
    normalized: dict[str, Any] = {}
    for key, value in raw.items():
        field = _JSON_ALIASES.get(key, key)
        if field in _ENUMS:
            enum_value = _enum_or_none(_ENUMS[field], value)
            if enum_value is not None:
                normalized[field] = enum_value
            continue
        normalized[field] = value
    return normalized


def _contains_phrase(text: str, phrase: str) -> bool:
    normalized = re.escape(phrase.lower()).replace(r"\ ", r"[\s_-]+")
    return re.search(rf"(?<![a-z0-9]){normalized}(?![a-z0-9])", text) is not None


def _parse_text_response(text: str) -> dict[str, Any]:
    lowered = text.lower().replace("_", " ")
    payload: dict[str, Any] = {}
    for field, values in _TEXT_SYNONYMS.items():
        matches = []
        for value, phrases in values.items():
            if any(_contains_phrase(lowered, phrase) for phrase in phrases):
                matches.append(value)
        if len(set(matches)) == 1:
            payload[field] = next(iter(set(matches)))

    must_match = re.search(r"must\s+answer\s*:?\s*(?P<body>.+)$", text, flags=re.IGNORECASE)
    if must_match:
        body = must_match.group("body")
        questions = [item.strip(" ;.") for item in re.split(r"\s+(?:and|&)\s+|[,;\n]+", body) if item.strip(" ;.")]
        if questions:
            payload["must_answer"] = tuple(questions[:MAX_MUST_ANSWER])
    return payload


def parse_profile_response(text: str) -> PartialResearchProfile:
    if not isinstance(text, str) or not text.strip():
        raise ValueError("profile_response_empty")
    stripped = text.strip()
    payload = _parse_json_response(stripped) if stripped.startswith(("{", "[")) else _parse_text_response(stripped)
    return PartialResearchProfile.model_validate(payload)


__all__ = [
    "CostTolerance",
    "OutputFormat",
    "PartialResearchProfile",
    "ResearchDepth",
    "ResearchProfile",
    "RequestBundleStoreProtocol",
    "StructuredBrief",
    "TargetAudience",
    "TimeBudget",
    "canonical_profile_bytes",
    "canonical_profile_json",
    "compute_profile_content_hash",
    "finalize_profile",
    "merge_profile_progress",
    "missing_dimensions",
    "parse_profile_response",
    "profile_state_fields",
]
