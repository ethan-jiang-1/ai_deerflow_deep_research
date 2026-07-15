"""Pure topic-planning contracts for the real topic planning node.

@impl TOP-001
@impl TOP-002
@impl TOP-003
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from typing import Any, Literal

from pydantic import Field, field_validator

from deerflow_deep_research.domain.lifecycle import FrozenContract

MAX_TOPICS = 8
MIN_TOPICS = 1
MAX_TOPIC_TITLE_CHARS = 128
MAX_TOPIC_SCOPE_CHARS = 512
MAX_TOPIC_BINDING_CHARS = 256
MAX_TOPIC_DIMENSIONS = 8
MAX_TOPIC_DIMENSION_CHARS = 128
MAX_TOPIC_EXCLUSIONS = 8
MAX_TOPIC_EXCLUSION_CHARS = 128
MAX_TOPIC_SLUG_CHARS = 48
TOPIC_SCHEMA_VERSION = 1

_PLAN_ALLOWED_KEYS = {"schema_version", "topics"}
_TOPIC_ALLOWED_KEYS = {
    "title",
    "scope",
    "must_answer_bindings",
    "search_dimensions",
    "exclusions",
}


class ResearchTopic(FrozenContract):
    """A single scoped research topic proposed by the planner."""

    title: str = Field(min_length=1, max_length=MAX_TOPIC_TITLE_CHARS)
    scope: str = Field(min_length=1, max_length=MAX_TOPIC_SCOPE_CHARS)
    must_answer_bindings: tuple[str, ...] = Field(min_length=1, max_length=MAX_TOPICS)
    search_dimensions: tuple[str, ...] = Field(default=(), max_length=MAX_TOPIC_DIMENSIONS)
    exclusions: tuple[str, ...] = Field(default=(), max_length=MAX_TOPIC_EXCLUSIONS)

    @field_validator("title", "scope")
    @classmethod
    def _strip_required_text(cls, value: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("topic_field_invalid")
        return value.strip()

    @field_validator("must_answer_bindings", "search_dimensions", "exclusions", mode="before")
    @classmethod
    def _normalize_text_tuple(cls, value: Any) -> tuple[str, ...]:
        if value is None:
            return ()
        if isinstance(value, str):
            value = (value,)
        if not isinstance(value, (tuple, list)):
            raise ValueError("topic_field_invalid")
        normalized: list[str] = []
        for item in value:
            if not isinstance(item, str):
                raise ValueError("topic_field_invalid")
            text = item.strip()
            if not text:
                raise ValueError("topic_field_invalid")
            normalized.append(text)
        return tuple(normalized)

    @field_validator("must_answer_bindings")
    @classmethod
    def _bound_bindings(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        for item in value:
            if len(item) > MAX_TOPIC_BINDING_CHARS:
                raise ValueError("topic_binding_too_long")
        return value

    @field_validator("search_dimensions")
    @classmethod
    def _bound_dimensions(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        for item in value:
            if len(item) > MAX_TOPIC_DIMENSION_CHARS:
                raise ValueError("topic_dimension_too_long")
        return value

    @field_validator("exclusions")
    @classmethod
    def _bound_exclusions(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        for item in value:
            if len(item) > MAX_TOPIC_EXCLUSION_CHARS:
                raise ValueError("topic_exclusion_too_long")
        return value


class TopicPlan(FrozenContract):
    """Validated planner structured output: a bounded set of scoped topics."""

    schema_version: Literal[1] = TOPIC_SCHEMA_VERSION
    topics: tuple[ResearchTopic, ...] = Field(min_length=MIN_TOPICS, max_length=MAX_TOPICS)


class MaterializedTopic(FrozenContract):
    """A registry entry with a deterministic, model-independent id and slug."""

    topic_id: str = Field(min_length=1, max_length=MAX_TOPIC_SLUG_CHARS)
    slug: str = Field(min_length=1, max_length=MAX_TOPIC_SLUG_CHARS)
    title: str = Field(min_length=1, max_length=MAX_TOPIC_TITLE_CHARS)
    scope: str = Field(min_length=1, max_length=MAX_TOPIC_SCOPE_CHARS)
    must_answer_bindings: tuple[str, ...] = Field(default=())
    search_dimensions: tuple[str, ...] = Field(default=())
    exclusions: tuple[str, ...] = Field(default=())


class MaterializedTopics(FrozenContract):
    """The deterministic topic registry plus a must-answer coverage map."""

    schema_version: Literal[1] = TOPIC_SCHEMA_VERSION
    topics: tuple[MaterializedTopic, ...] = Field(min_length=MIN_TOPICS, max_length=MAX_TOPICS)
    coverage: Mapping[str, tuple[str, ...]] = Field(default_factory=dict)


_SLUG_RE = re.compile(r"[^a-z0-9]+")


def slugify_topic(title: str) -> str:
    """Derive a stable, model-independent slug from a validated topic title.

    The slug is never the raw model-proposed string: it is lowercased,
    non-alphanumeric runs collapsed to single hyphens, trimmed, and bounded.
    """
    if not isinstance(title, str):
        raise ValueError("topic_title_invalid")
    slug = _SLUG_RE.sub("-", title.strip().lower()).strip("-")
    if not slug:
        slug = "topic"
    return slug[:MAX_TOPIC_SLUG_CHARS]


def parse_plan_output(text: str) -> TopicPlan:
    """Parse and validate one model ``summary`` JSON object into a ``TopicPlan``."""
    if not isinstance(text, str) or not text.strip():
        raise ValueError("topic_plan_empty")
    try:
        raw = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError("topic_plan_json_invalid") from exc
    if not isinstance(raw, dict):
        raise ValueError("topic_plan_json_invalid")
    unknown = set(raw) - _PLAN_ALLOWED_KEYS
    if unknown:
        raise ValueError("topic_plan_extra_fields")
    return TopicPlan.model_validate(raw)


def materialize_topic_plan(plan: TopicPlan | Mapping[str, Any], must_answer: Sequence[str]) -> MaterializedTopics:
    """Deterministically materialize a validated plan into a stable registry.

    Derives model-independent ids/slugs, rejects duplicate slugs and overlapping
    scopes, and builds a coverage map that binds every root ``must_answer``
    question to at least one topic. Raises ``ValueError`` on empty/uncovered
    coverage or over-expansion. Performs no I/O and no model calls.
    """
    validated = plan if isinstance(plan, TopicPlan) else TopicPlan.model_validate(plan)
    questions = tuple(q for q in must_answer if isinstance(q, str) and q.strip())
    if not questions:
        raise ValueError("topic_coverage_empty")

    topics_in = validated.topics
    seen_slugs: set[str] = set()
    seen_scopes: set[str] = set()
    materialized: list[MaterializedTopic] = []
    for proposed in topics_in:
        slug = slugify_topic(proposed.title)
        if slug in seen_slugs:
            raise ValueError("topic_duplicate_slug")
        if proposed.scope in seen_scopes:
            raise ValueError("topic_overlap")
        seen_slugs.add(slug)
        seen_scopes.add(proposed.scope)
        materialized.append(
            MaterializedTopic(
                topic_id=slug,
                slug=slug,
                title=proposed.title,
                scope=proposed.scope,
                must_answer_bindings=proposed.must_answer_bindings,
                search_dimensions=proposed.search_dimensions,
                exclusions=proposed.exclusions,
            )
        )

    coverage: dict[str, tuple[str, ...]] = {}
    bound_topic_ids: set[str] = set()
    for question in questions:
        covering = tuple(entry.topic_id for entry in materialized if question in entry.must_answer_bindings)
        if not covering:
            raise ValueError(f"topic_coverage_uncovered:{question}")
        coverage[question] = covering
        bound_topic_ids.update(covering)

    if not bound_topic_ids:
        raise ValueError("topic_coverage_empty")

    return MaterializedTopics(topics=tuple(materialized), coverage=coverage)


def materialized_topics_state(materialized: MaterializedTopics) -> dict[str, Any]:
    """Project a materialized registry into bounded planner-owned checkpoint state."""
    registry = tuple(entry.model_dump(mode="json") for entry in materialized.topics)
    return {
        "topic_refs": tuple(entry.topic_id for entry in materialized.topics),
        "topic_registry": registry,
    }


__all__ = [
    "MAX_TOPICS",
    "MAX_TOPIC_BINDING_CHARS",
    "MAX_TOPIC_DIMENSIONS",
    "MAX_TOPIC_DIMENSION_CHARS",
    "MAX_TOPIC_EXCLUSIONS",
    "MAX_TOPIC_EXCLUSION_CHARS",
    "MAX_TOPIC_SCOPE_CHARS",
    "MAX_TOPIC_SLUG_CHARS",
    "MAX_TOPIC_TITLE_CHARS",
    "MaterializedTopic",
    "MaterializedTopics",
    "ResearchTopic",
    "TOPIC_SCHEMA_VERSION",
    "TopicPlan",
    "materialize_topic_plan",
    "materialized_topics_state",
    "parse_plan_output",
    "slugify_topic",
]
