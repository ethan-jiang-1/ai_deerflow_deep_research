"""Zero-tool model-node and deterministic-node conformance.

@impl EVH-008
"""

from __future__ import annotations

import json
import time
from datetime import UTC, datetime
from pathlib import Path

import pytest

from deerflow_deep_research.agents.policies import ExecutionBudget, ExecutionPolicy
from deerflow_deep_research.domain.context import GraphContextView, NodeAgentContext
from deerflow_deep_research.domain.lifecycle import AcceptedHumanResponse, ResponseKind
from deerflow_deep_research.domain.node_spec import NodeBuildDependencies
from deerflow_deep_research.graph.nodes.final_delivery import NODE_SPEC as FINAL_SPEC
from deerflow_deep_research.graph.nodes.hitl1 import node as hitl1_node
from deerflow_deep_research.graph.nodes.hitl2 import node as hitl2_node
from deerflow_deep_research.graph.nodes.readiness import NODE_SPEC as READINESS_SPEC
from deerflow_deep_research.graph.nodes.rerun import NODE_SPEC as RERUN_SPEC
from deerflow_deep_research.graph.nodes.topic_planning import NODE_SPEC as TOPIC_SPEC
from deerflow_deep_research.graph.nodes.wave2_synthesis import NODE_SPEC as WAVE2_SPEC
from deerflow_deep_research.runtime.node_agent_bridge import RuntimeNodeAgentBridge
from deerflow_deep_research.runtime.request_bundle import RequestBundleStore
from deerflow_deep_research.runtime.work_unit_store import WorkUnitStore
from tests.fixtures.fake_models import ScriptedChatModel, ai_message
from tests.fixtures.runtime import local_runtime_envelope, unique_run_identity


class _ForbiddenModelCapability:
    async def run_agent(self, *, context, request):
        raise AssertionError(f"deterministic node called model: {context.node_name}")


def _brief() -> str:
    return json.dumps(
        {
            "schema_version": 1,
            "brief_summary": "A bounded research brief.",
            "depth": "standard",
            "audience": "practitioner",
            "format": "detailed_report",
            "cost_tolerance": "moderate",
            "time_budget": "standard",
            "must_answer": ["Q1"],
            "scope_boundaries": "",
            "custom_notes": "",
        }
    )


def _topic_plan() -> str:
    return json.dumps(
        {
            "schema_version": 1,
            "topics": [
                {
                    "title": "Storage",
                    "scope": "Storage economics",
                    "must_answer_bindings": ["Q1"],
                    "search_dimensions": [],
                    "exclusions": [],
                }
            ],
        }
    )


def _synthesis() -> str:
    return json.dumps(
        {
            "schema_version": 1,
            "findings": [],
            "relations": [],
            "gaps": [],
            "summary": "No unsupported findings.",
        }
    )


def _bridge(tmp_path: Path, node_name: str, response: str):
    identity = unique_run_identity()
    envelope = local_runtime_envelope(tmp_path, identity=identity)
    workspace = f"/mnt/user-data/workspace/deep-research/{identity.research_id}"
    policy = ExecutionPolicy(
        policy_name=f"{node_name}-zero-tool",
        allowed_tool_names=frozenset(),
        read_roots=(workspace,),
        write_roots=(),
        attempt_root=workspace,
        budget=ExecutionBudget(2, 1, 1, 1, 8_192, 2_048, 1, 4_096, 5),
    )
    bridge = RuntimeNodeAgentBridge(
        envelope=envelope,
        policy=policy,
        model_resolver=lambda _envelope: ScriptedChatModel(responses=[ai_message(response)]),
        tools_resolver=lambda _envelope, _policy: (),
    )
    graph = GraphContextView(
        research_scope_id=identity.research_id,
        workspace_root=workspace,
        uploads_root="/mnt/user-data/uploads",
        outputs_root=f"/mnt/user-data/outputs/deep-research/{identity.research_id}",
    )
    context = NodeAgentContext(
        research_scope_id=identity.research_id,
        node_name=node_name,
        attempt_id=f"g0-{node_name}-a1".replace("_", "-"),
        workspace_root=workspace,
        attempt_root=f"{workspace}/attempts/{node_name}",
        policy_name=policy.policy_name,
    )
    return identity, envelope, bridge, graph, context


async def test_hitl1_brief_generation_crosses_real_zero_tool_bridge(monkeypatch, tmp_path: Path) -> None:
    identity, envelope, bridge, graph, context = _bridge(tmp_path, "hitl1", _brief())
    store = RequestBundleStore(workspace_host_path=envelope.workspace_host_path, research_id=identity.research_id)
    monkeypatch.setattr(hitl1_node, "interrupt", lambda _value: (_ for _ in ()).throw(RuntimeError("interrupt")))
    dependencies = NodeBuildDependencies(graph, context, bridge, request_bundle=store)
    state = {
        "research_id": identity.research_id,
        "start_message_id": "human-start",
        "request_text": "Compare storage options",
        "generation": 0,
        "execution_trace": (),
        "consumed_message_ids": (),
    }
    with pytest.raises(RuntimeError, match="interrupt"):
        await hitl1_node.build_real(dependencies)(state)
    assert bridge.agents_built == 1


async def test_topic_planning_crosses_real_zero_tool_bridge(tmp_path: Path) -> None:
    identity, _envelope, bridge, graph, context = _bridge(tmp_path, "topic_planning", _topic_plan())
    update = await TOPIC_SPEC.real_factory(NodeBuildDependencies(graph, context, bridge))(
        {
            "research_id": identity.research_id,
            "request_text": "Compare storage options",
            "research_depth": "standard",
            "target_audience": "practitioner",
            "output_format": "detailed_report",
            "cost_tolerance": "moderate",
            "time_budget": "standard",
            "must_answer_questions": ("Q1",),
            "degraded_profile": False,
            "execution_trace": (),
        }
    )
    assert update["route"] == "next"
    assert bridge.agents_built == 1


async def test_wave2_crosses_real_zero_tool_bridge(tmp_path: Path) -> None:
    identity, envelope, bridge, graph, context = _bridge(tmp_path, "wave2_synthesis", _synthesis())
    store = WorkUnitStore(
        workspace_host_path=envelope.workspace_host_path,
        research_id=identity.research_id,
        clock=lambda: datetime(2026, 7, 17, tzinfo=UTC),
        monotonic=time.monotonic,
        lock_sleep=time.sleep,
        token_factory=lambda: "6" * 32,
        fault_hook=None,
    )
    update = await WAVE2_SPEC.real_factory(NodeBuildDependencies(graph, context, bridge, synthesis_bundle=store))(
        {"research_id": identity.research_id, "accepted_submission_refs": (), "execution_trace": ()}
    )
    assert update["execution_trace"] == ("wave2_synthesis",)
    assert bridge.agents_built == 1
    assert (
        envelope.workspace_host_path / "deep-research" / identity.research_id / "synthesis" / "findings.json"
    ).is_file()


def _deterministic_dependencies(node_name: str, *, publication_bundle=None) -> NodeBuildDependencies:
    research_id = "r_" + "D" * 43
    workspace = f"/mnt/user-data/workspace/deep-research/{research_id}"
    graph = GraphContextView(
        research_scope_id=research_id,
        workspace_root=workspace,
        uploads_root="/mnt/user-data/uploads",
        outputs_root=f"/mnt/user-data/outputs/deep-research/{research_id}",
    )
    return NodeBuildDependencies(
        graph_context=graph,
        agent_context=NodeAgentContext(
            research_scope_id=research_id,
            node_name=node_name,
            attempt_id=f"g0-{node_name.replace('_', '-')}-a1",
            workspace_root=workspace,
            attempt_root=f"{workspace}/attempts/{node_name}",
            policy_name=f"{node_name.replace('_', '-')}-deterministic",
        ),
        capabilities=_ForbiddenModelCapability(),
        publication_bundle=publication_bundle,
    )


async def test_hitl2_is_deterministic_zero_tool_node(monkeypatch) -> None:
    dependencies = _deterministic_dependencies("hitl2")

    def accept(descriptor: dict) -> dict:
        return AcceptedHumanResponse(
            request_id=descriptor["request"]["request_id"],
            message_id="human-proceed",
            value="proceed",
            response_kind=ResponseKind.OPTION,
            option_id="proceed",
        ).model_dump(mode="json")

    monkeypatch.setattr(hitl2_node, "interrupt", accept)
    update = await hitl2_node.build_real(dependencies)(
        {
            "research_id": dependencies.graph_context.research_scope_id,
            "generation": 0,
            "start_message_id": "human-start",
            "accepted_submission_refs": ("ref:1",),
            "synthesis_gaps": (),
            "consumed_request_ids": (),
            "consumed_message_ids": (),
            "execution_trace": (),
        }
    )
    assert update["route"] == "proceed"


async def test_rerun_readiness_and_final_delivery_are_deterministic_zero_tool_nodes(tmp_path: Path) -> None:
    research_id = "r_" + "D" * 43
    rerun = await RERUN_SPEC.real_factory(_deterministic_dependencies("rerun"))(
        {
            "research_id": research_id,
            "generation": 0,
            "hitl2_rerun_payload": {"scope": "full", "reason": "re-evaluate"},
            "execution_trace": (),
        }
    )
    assert rerun["route"] == "topic_planning"

    readiness = await READINESS_SPEC.real_factory(_deterministic_dependencies("readiness"))(
        {
            "research_id": research_id,
            "generation": 0,
            "accepted_submission_refs": ("ref:1",),
            "must_answer_questions": (),
            "consumed_request_ids": ("request-1",),
            "execution_trace": (),
        }
    )
    assert readiness["route"] == "pass"

    publication_store = WorkUnitStore(
        workspace_host_path=tmp_path,
        research_id=research_id,
        clock=lambda: datetime(2026, 7, 17, tzinfo=UTC),
        monotonic=time.monotonic,
        lock_sleep=time.sleep,
        token_factory=lambda: "b" * 32,
        fault_hook=None,
    )
    final = await FINAL_SPEC.real_factory(
        _deterministic_dependencies("final_delivery", publication_bundle=publication_store)
    )(
        {
            "research_id": research_id,
            "generation": 0,
            "accepted_submission_refs": ("ref:1",),
            "execution_trace": (),
        }
    )
    assert final["terminal_status"] == "completed"
    assert (tmp_path / "deep-research" / research_id / "final" / "report.md").is_file()
