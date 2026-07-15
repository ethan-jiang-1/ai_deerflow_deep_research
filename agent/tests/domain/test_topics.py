"""Topic-planning domain contracts and materializer.

@impl TOP-001
@impl TOP-002
@impl TOP-003
"""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from deerflow_deep_research.domain.topics import (
    MAX_TOPICS,
    ResearchTopic,
    TopicPlan,
    materialize_topic_plan,
    materialized_topics_state,
    parse_plan_output,
    slugify_topic,
)


def _topic(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "title": "Grid-scale battery economics",
        "scope": "Cost dynamics of lithium grid batteries.",
        "must_answer_bindings": ["What matters most?"],
        "search_dimensions": ["pricing", "deployment"],
        "exclusions": ["consumer electronics"],
    }
    payload.update(overrides)
    return payload


def _plan(*topics: dict[str, object]) -> str:
    return json.dumps({"schema_version": 1, "topics": list(topics)})


def test_topic_plan_contract_is_frozen_extra_forbid_and_bounded() -> None:
    plan = TopicPlan.model_validate({"topics": [_topic()]})
    assert plan.schema_version == 1
    assert len(plan.topics) == 1
    [topic] = plan.topics
    assert topic.must_answer_bindings == ("What matters most?",)
    assert topic.search_dimensions == ("pricing", "deployment")

    with pytest.raises(ValidationError):
        TopicPlan.model_validate({"topics": [_topic(unexpected=True)]})
    with pytest.raises(ValidationError):
        plan.topics = ()  # type: ignore[misc]
    with pytest.raises(ValidationError):
        TopicPlan.model_validate({"topics": []})
    with pytest.raises(ValidationError):
        TopicPlan.model_validate({"topics": [_topic(title="x" * 129)]})
    with pytest.raises(ValidationError):
        TopicPlan.model_validate({"topics": [_topic(must_answer_bindings=[])]})
    with pytest.raises(ValidationError):
        TopicPlan.model_validate({"topics": [_topic(must_answer_bindings=["x" * 257])]})
    with pytest.raises(ValidationError):
        TopicPlan.model_validate({"topics": [_topic(search_dimensions=["x" * 129])]})
    with pytest.raises(ValidationError):
        TopicPlan.model_validate({"topics": [_topic(exclusions=["x" * 129])]})


def test_topic_plan_bounds_topic_count() -> None:
    many = [_topic(title=f"Topic {n}") for n in range(MAX_TOPICS + 1)]
    with pytest.raises(ValidationError):
        TopicPlan.model_validate({"topics": many})


def test_parse_plan_output_accepts_json_and_rejects_invalid() -> None:
    parsed = parse_plan_output(_plan(_topic()))
    assert isinstance(parsed, TopicPlan)
    assert parsed.schema_version == 1

    with pytest.raises(ValueError, match="topic_plan_json_invalid"):
        parse_plan_output("[1, 2]")
    with pytest.raises(ValueError, match="topic_plan_json_invalid"):
        parse_plan_output("not json")
    with pytest.raises(ValueError, match="topic_plan_empty"):
        parse_plan_output("   ")
    with pytest.raises(ValueError, match="topic_plan_extra_fields"):
        parse_plan_output(json.dumps({"topics": [_topic()], "host_path": "/tmp/x"}))


def test_materializer_ids_and_slugs_are_stable_and_model_independent() -> None:
    plan = TopicPlan(
        topics=(
            ResearchTopic(title="Grid-Scale Batteries", scope="A", must_answer_bindings=("Q",)),
            ResearchTopic(title="Solar Capacity", scope="B", must_answer_bindings=("Q",)),
        )
    )
    first = materialize_topic_plan(plan, ["Q"])
    second = materialize_topic_plan(plan, ["Q"])
    assert first == second
    for entry in first.topics:
        assert entry.topic_id == entry.slug
        assert entry.topic_id != entry.title
        assert entry.topic_id == slugify_topic(entry.title)
    assert {t.topic_id for t in first.topics} == {"grid-scale-batteries", "solar-capacity"}


def test_materializer_rejects_duplicate_slugs_and_overlapping_scopes() -> None:
    dup_slug = TopicPlan(
        topics=(
            ResearchTopic(title="Batteries", scope="A", must_answer_bindings=("Q",)),
            ResearchTopic(title="batteries", scope="B", must_answer_bindings=("Q",)),
        )
    )
    with pytest.raises(ValueError, match="topic_duplicate_slug"):
        materialize_topic_plan(dup_slug, ["Q"])

    overlap = TopicPlan(
        topics=(
            ResearchTopic(title="Batteries", scope="same scope", must_answer_bindings=("Q",)),
            ResearchTopic(title="Storage", scope="same scope", must_answer_bindings=("Q",)),
        )
    )
    with pytest.raises(ValueError, match="topic_overlap"):
        materialize_topic_plan(overlap, ["Q"])


def test_materializer_coverage_binds_every_root_question() -> None:
    plan = TopicPlan(
        topics=(
            ResearchTopic(title="Batteries", scope="A", must_answer_bindings=("Q1",)),
            ResearchTopic(title="Solar", scope="B", must_answer_bindings=("Q2",)),
        )
    )
    materialized = materialize_topic_plan(plan, ["Q1", "Q2"])
    assert set(materialized.coverage) == {"Q1", "Q2"}
    assert materialized.coverage["Q1"] == ("batteries",)
    state = materialized_topics_state(materialized)
    assert state["topic_refs"] == ("batteries", "solar")
    assert len(state["topic_registry"]) == 2
    assert state["topic_registry"][0]["topic_id"] == "batteries"


def test_materializer_rejects_empty_uncovered_and_over_expansion() -> None:
    plan = TopicPlan(topics=(ResearchTopic(title="Batteries", scope="A", must_answer_bindings=("Q1",)),))
    with pytest.raises(ValueError, match="topic_coverage_uncovered"):
        materialize_topic_plan(plan, ["Q1", "Q2"])
    with pytest.raises(ValueError, match="topic_coverage_empty"):
        materialize_topic_plan(plan, [])

    over_payload = {
        "topics": [
            {"title": f"T{n}", "scope": f"scope-{n}", "must_answer_bindings": ["Q"]} for n in range(MAX_TOPICS + 1)
        ]
    }
    with pytest.raises(ValidationError):
        materialize_topic_plan(over_payload, ["Q"])
