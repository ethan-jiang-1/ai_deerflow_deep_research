"""Mixed real-bootstrap/real-HITL1/real-topic-planning lifecycle coverage.

@impl TOP-001
@impl TOP-003
@impl TOP-004
@impl TOP-005
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from langchain_core.messages import HumanMessage

from deerflow_deep_research.graph.topology import LOGICAL_NODES
from deerflow_deep_research.runtime.research import ResearchGraphRecipe

from .test_hitl1_lifecycle import (
    _BridgeFactory,
    _brief_json,
    _command_payload,
    _envelope,
    _handlers,
    _messages_response,
    _option_response,
    _patch_stores,
    _resume_input,
    _start_graph,
)

_FULL_FAKE = {name: "fake" for name in LOGICAL_NODES}
_MIXED_TOPIC = _FULL_FAKE | {"bootstrap": "real", "hitl1": "real", "topic_planning": "real"}


def _plan_json() -> str:
    topics = [
        {
            "title": "Batteries",
            "scope": "Grid battery economics",
            "must_answer_bindings": ["Q1"],
            "search_dimensions": [],
            "exclusions": [],
        },
        {
            "title": "Solar",
            "scope": "Utility-scale solar economics",
            "must_answer_bindings": ["Q2"],
            "search_dimensions": [],
            "exclusions": [],
        },
    ]
    return json.dumps({"schema_version": 1, "topics": topics})


def _profile_answer() -> str:
    return json.dumps(
        {
            "depth": "deep_dive",
            "audience": "domain_expert",
            "output_format": "annotated_bibliography",
            "cost_tolerance": "extensive",
            "time_budget": "overnight",
            "must_answer": ["Q1", "Q2"],
        }
    )


async def test_mixed_topic_planning_complete_lifecycle(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _patch_stores(monkeypatch)
    bridge_factory = _BridgeFactory(_brief_json(), _brief_json(), _plan_json())
    recipe = ResearchGraphRecipe.create(implementation_modes=_MIXED_TOPIC, node_agent_bridge_factory=bridge_factory)
    start, resume, graph, _saver = _handlers(recipe)
    envelope = _envelope(tmp_path)
    user = HumanMessage(content="Compare storage options", id="human-start")

    research_id, config, started = await _start_graph(start, graph, envelope, user)
    start_result, hitl1 = _command_payload(started)
    assert start_result["code"] == "suspended"
    assert hitl1["mode"] == "text"

    response = _messages_response(str(hitl1["request_id"]), _profile_answer(), "human-profile")
    resumed = await resume.execute(
        graph,
        config=config,
        envelope=envelope,
        action_input=_resume_input(research_id, (user, response), "call-resume-1"),
    )
    resume_result, hitl2 = _command_payload(resumed)
    assert resume_result["code"] == "suspended"
    assert hitl2["mode"] == "choice"

    # Real topic planning ran between the HITL1 accept and the HITL2 interrupt.
    values = (await graph.aget_state(config)).values
    assert tuple(values["topic_refs"]) == ("batteries", "solar")
    assert len(values["topic_registry"]) == 2
    assert values["topic_registry"][0]["topic_id"] == "batteries"
    assert values["research_depth"] == "deep_dive"
    assert tuple(values["must_answer_questions"]) == ("Q1", "Q2")

    proceed = _option_response(str(hitl2["request_id"]), "proceed", "human-proceed")
    completed = await resume.execute(
        graph,
        config=config,
        envelope=envelope,
        action_input=_resume_input(research_id, (user, response, proceed), "call-resume-2"),
    )
    assert completed["code"] == "completed"
    assert completed["implementation_mode"] == "full_fake"
    assert bridge_factory.calls  # the planner bridge was actually invoked


async def test_invalid_plan_is_repaired_then_completes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _patch_stores(monkeypatch)
    bridge_factory = _BridgeFactory(_brief_json(), _brief_json(), "not-json", _plan_json())
    recipe = ResearchGraphRecipe.create(implementation_modes=_MIXED_TOPIC, node_agent_bridge_factory=bridge_factory)
    start, resume, graph, _saver = _handlers(recipe)
    envelope = _envelope(tmp_path)
    user = HumanMessage(content="Compare storage options", id="human-start")

    research_id, config, started = await _start_graph(start, graph, envelope, user)
    _, hitl1 = _command_payload(started)

    response = _messages_response(str(hitl1["request_id"]), _profile_answer(), "human-profile")
    resumed = await resume.execute(
        graph,
        config=config,
        envelope=envelope,
        action_input=_resume_input(research_id, (user, response), "call-resume-1"),
    )
    resume_result, _hitl2 = _command_payload(resumed)
    assert resume_result["code"] == "suspended"
    values = (await graph.aget_state(config)).values
    assert tuple(values["topic_refs"]) == ("batteries", "solar")


async def test_repeated_invalid_plan_blocks_before_wave0(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _patch_stores(monkeypatch)
    bridge_factory = _BridgeFactory(_brief_json(), _brief_json(), "not-json", '{"still":"invalid"}')
    recipe = ResearchGraphRecipe.create(implementation_modes=_MIXED_TOPIC, node_agent_bridge_factory=bridge_factory)
    start, resume, graph, _saver = _handlers(recipe)
    envelope = _envelope(tmp_path)
    user = HumanMessage(content="Compare storage options", id="human-start")

    research_id, config, started = await _start_graph(start, graph, envelope, user)
    _, hitl1 = _command_payload(started)

    response = _messages_response(str(hitl1["request_id"]), _profile_answer(), "human-profile")
    resumed = await resume.execute(
        graph,
        config=config,
        envelope=envelope,
        action_input=_resume_input(research_id, (user, response), "call-resume-1"),
    )
    assert resumed["code"] == "blocked"
    values = (await graph.aget_state(config)).values
    assert not values.get("topic_registry")
    assert not values.get("topic_refs")


async def test_full_fake_topic_planning_completes_without_bridge(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _patch_stores(monkeypatch)
    recipe = ResearchGraphRecipe.create(implementation_modes=_FULL_FAKE)
    assert recipe.requires_node_agent_bridge is False
    start, resume, graph, _saver = _handlers(recipe)
    envelope = _envelope(tmp_path)
    user = HumanMessage(content="Compare storage options", id="human-start")

    research_id, config, started = await _start_graph(start, graph, envelope, user)
    _, hitl1 = _command_payload(started)
    response = _messages_response(str(hitl1["request_id"]), _profile_answer(), "human-profile")
    resumed = await resume.execute(
        graph,
        config=config,
        envelope=envelope,
        action_input=_resume_input(research_id, (user, response), "call-resume-1"),
    )
    resume_result, hitl2 = _command_payload(resumed)
    assert resume_result["code"] == "suspended"
    values = (await graph.aget_state(config)).values
    # Fake topic planning routes next without recording any registry.
    assert not values.get("topic_registry")
