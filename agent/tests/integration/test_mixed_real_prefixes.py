"""Handler-driven mixed graph coverage through the highest real prefix.

@impl EVH-001
@impl EVH-008
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
    _resume_input,
    _start_graph,
)
from .test_wave0_lifecycle import _patch_stores, _profile_answer, _topic_plan_json, _worker_output_json

_FULL_FAKE = {name: "fake" for name in LOGICAL_NODES}
_REAL_THROUGH_WAVE2 = _FULL_FAKE | {
    "bootstrap": "real",
    "hitl1": "real",
    "topic_planning": "real",
    "wave0": "real",
    "wave1": "real",
    "wave2_synthesis": "real",
    "targeted_evidence": "real",
}


def _wave1_output(source_id: str, url: str) -> str:
    return json.dumps(
        {
            "schema_version": 1,
            "sources": [
                {
                    "source_id": source_id,
                    "canonical_url": url,
                    "title": "Deep evidence",
                    "content_ref": "workspace/forged",
                    "content_hash": "h_" + "Z" * 43,
                    "byte_count": 999,
                    "is_new_vs_wave0": True,
                }
            ],
            "source_ids": [source_id],
            "claims": [],
            "open_questions": [],
        }
    )


def _synthesis_output() -> str:
    return json.dumps(
        {
            "schema_version": 1,
            "findings": [],
            "relations": [],
            "gaps": [],
            "summary": "Evidence synthesized without unsupported findings.",
        }
    )


async def test_handlers_run_real_prefix_through_wave2_and_keep_later_nodes_fake(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _patch_stores(monkeypatch)
    bridge_factory = _BridgeFactory(
        _brief_json(),
        _brief_json(),
        _topic_plan_json(),
        _worker_output_json(),
        _worker_output_json(),
        _wave1_output("source:w1a", "https://example.com/w1a"),
        _wave1_output("source:w1b", "https://example.com/w1b"),
        _synthesis_output(),
    )
    recipe = ResearchGraphRecipe.create(
        implementation_modes=_REAL_THROUGH_WAVE2,
        node_agent_bridge_factory=bridge_factory,
    )
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
        action_input=_resume_input(research_id, (user, response), "call-resume-real-prefix"),
    )

    result, hitl2 = _command_payload(resumed)
    snapshot = await graph.aget_state(config)
    values = snapshot.values
    assert result["code"] == "suspended"
    assert result["implementation_mode"] == "full_fake"
    assert hitl2["mode"] == "choice"
    assert snapshot.tasks[0].interrupts[0].value["phase"] == "hitl2"
    assert len(values["accepted_submission_refs"]) == 4
    artifact = envelope.workspace_host_path / "deep-research" / research_id / "synthesis" / "findings.json"
    assert json.loads(artifact.read_text(encoding="utf-8"))["summary"].startswith("Evidence synthesized")
    assert "targeted_evidence" not in tuple(values["execution_trace"])
