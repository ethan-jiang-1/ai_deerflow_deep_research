"""Mixed real bootstrap/HITL1/topic-planning/wave0 lifecycle coverage.

@impl WAN-001
@impl WAN-002
@impl WAN-003
@impl WAN-004
@impl WAN-005
"""

from __future__ import annotations

import json
import secrets
import time
from datetime import UTC, datetime
from pathlib import Path

import pytest
from langchain_core.messages import HumanMessage

from deerflow_deep_research.graph.topology import LOGICAL_NODES
from deerflow_deep_research.runtime.bootstrap_bundle import BootstrapBundleStore
from deerflow_deep_research.runtime.request_bundle import RequestBundleStore
from deerflow_deep_research.runtime.research import ResearchGraphRecipe
from deerflow_deep_research.runtime.work_unit_store import WorkUnitStore

from .test_hitl1_lifecycle import (
    _BridgeFactory,
    _brief_json,
    _command_payload,
    _envelope,
    _handlers,
    _messages_response,
    _option_response,
    _resume_input,
    _start_graph,
)

_FULL_FAKE = {name: "fake" for name in LOGICAL_NODES}
_MIXED_WAVE0 = _FULL_FAKE | {
    "bootstrap": "real",
    "hitl1": "real",
    "topic_planning": "real",
    "wave0": "real",
}


class _FakeRequestStore:
    async def write_profile(self, profile: object) -> object:
        return None


def _patch_stores(monkeypatch: pytest.MonkeyPatch) -> None:
    """Patch stores with a real-now clock so attempt timestamps stay ordered.

    The real node uses ``datetime.now`` for ``created_at`` while the store stamps
    ``submitted_at`` with its own clock; in production both are ~now (created
    before submitted). The shared hitl1 helper pins the store clock to a fixed
    past date, which would invert the order, so wave0 uses a now-based clock.
    """

    async def wu_create(_cls, envelope, *, research_id, **_kwargs):
        return WorkUnitStore(
            workspace_host_path=envelope.workspace_host_path,
            research_id=research_id,
            clock=lambda: datetime.now(UTC),
            monotonic=time.monotonic,
            lock_sleep=time.sleep,
            token_factory=lambda: secrets.token_hex(16),
            fault_hook=None,
        )

    async def bb_create(_cls, envelope, *, research_id, **_kwargs):
        return BootstrapBundleStore(workspace_host_path=envelope.workspace_host_path, research_id=research_id)

    async def rb_create(_cls, envelope, *, research_id, **_kwargs):
        return RequestBundleStore(workspace_host_path=envelope.workspace_host_path, research_id=research_id)

    monkeypatch.setattr(WorkUnitStore, "create", classmethod(wu_create))
    monkeypatch.setattr(BootstrapBundleStore, "create", classmethod(bb_create))
    monkeypatch.setattr(RequestBundleStore, "create", classmethod(rb_create))


def _topic_plan_json() -> str:
    return json.dumps(
        {
            "schema_version": 1,
            "topics": [
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
            ],
        }
    )


def _worker_output_json() -> str:
    return json.dumps(
        {
            "schema_version": 1,
            "sources": [
                {
                    "source_id": "source:1",
                    "canonical_url": "https://example.com/path",
                    "title": "Example source",
                    "fetch_status": "fetched",
                }
            ],
            "baseline_facts": ["A baseline fact."],
            "limitations": "",
        }
    )


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


async def test_mixed_wave0_complete_lifecycle(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _patch_stores(monkeypatch)
    # hitl1 brief (start) + hitl1 brief (resume) + topic plan + one worker output per topic.
    bridge_factory = _BridgeFactory(
        _brief_json(), _brief_json(), _topic_plan_json(), _worker_output_json(), _worker_output_json()
    )
    recipe = ResearchGraphRecipe.create(implementation_modes=_MIXED_WAVE0, node_agent_bridge_factory=bridge_factory)
    start, resume, graph, _saver = _handlers(recipe)
    envelope = _envelope(tmp_path)
    user = HumanMessage(content="Compare storage options", id="human-start")

    research_id, config, started = await _start_graph(start, graph, envelope, user)
    _, hitl1 = _command_payload(started)
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

    # Real Wave0 ran between topic planning and HITL2 and produced accepted
    # submissions for its topics (fake Wave1 adds more downstream).
    values = (await graph.aget_state(config)).values
    assert len(tuple(values.get("accepted_submission_refs") or ())) >= 2

    proceed = _option_response(str(hitl2["request_id"]), "proceed", "human-proceed")
    completed = await resume.execute(
        graph,
        config=config,
        envelope=envelope,
        action_input=_resume_input(research_id, (user, response, proceed), "call-resume-2"),
    )
    assert completed["code"] == "completed"
    assert completed["implementation_mode"] == "full_fake"
    assert bridge_factory.calls  # the worker bridge was actually invoked


async def test_wave0_blocked_when_worker_fails_every_topic(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _patch_stores(monkeypatch)
    # The wave0 worker returns invalid output on every attempt -> no accepted
    # submissions -> the gate cannot pass -> terminal blocked.
    bridge_factory = _BridgeFactory(_brief_json(), _brief_json(), _topic_plan_json(), "not-json", "not-json")
    recipe = ResearchGraphRecipe.create(implementation_modes=_MIXED_WAVE0, node_agent_bridge_factory=bridge_factory)
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
    assert not values.get("accepted_submission_refs")
