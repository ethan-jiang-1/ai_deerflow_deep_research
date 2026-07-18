"""Wave1 work-unit planning, validation, gate, and open-question integration.

@impl WON-001
@impl WON-003
@impl WON-004
@impl WON-006
"""

from __future__ import annotations

import json
import time
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from deerflow_deep_research.domain.context import GraphContextView, NodeAgentContext, NodeExecutionResult
from deerflow_deep_research.domain.enums import NodeFinishReason
from deerflow_deep_research.domain.invocation import GraphInvocationContext, WorkUnitControllerDependencies
from deerflow_deep_research.domain.node_spec import NodeBuildDependencies, NodeCapability
from deerflow_deep_research.domain.state import WORK_UNIT_GATE_PREVIEW_FIELDS, merge_trace, preview_work_unit_update
from deerflow_deep_research.graph.builder import _node_wrapper
from deerflow_deep_research.graph.components.work_units import run_fixture_work_unit_component
from deerflow_deep_research.graph.nodes.gate_adapter import default_gate_defs
from deerflow_deep_research.graph.nodes.wave1 import NODE_SPEC
from deerflow_deep_research.graph.nodes.wave1 import subgraph as wave1_subgraph
from deerflow_deep_research.runtime.projection import RuntimeWorkUnitDependencyResolver
from deerflow_deep_research.runtime.work_unit_store import WorkUnitStore
from tests.assets.provider_shapes import load_provider_shape_cases, thaw_provider_shape_payload

RESEARCH_ID = "r_" + "B" * 43
NOW = datetime(2026, 7, 14, tzinfo=UTC)
SHAPE_CASES = {
    case.case_id: case
    for case in load_provider_shape_cases(Path(__file__).parents[1] / "fixtures/provider_shapes/wave1.json")
}


class ForbiddenCapabilities:
    async def run_agent(self, *, context, request):
        raise AssertionError("fixture work must not call an agent")


class ScriptedWave1Capabilities:
    def __init__(
        self,
        *,
        malformed: bool = False,
        malformed_once: bool = False,
        reverse_sources: bool = False,
        provider_payload: dict | None = None,
    ) -> None:
        self.contexts: list[NodeAgentContext] = []
        self.requests: list[object] = []
        self.malformed = malformed
        self.malformed_once = malformed_once
        self.reverse_sources = reverse_sources
        self.provider_payload = provider_payload

    async def run_agent(self, *, context, request):
        if not isinstance(context, NodeAgentContext):
            raise TypeError("node_agent_context_required")
        self.contexts.append(context)
        self.requests.append(request)
        if self.provider_payload is not None:
            return NodeExecutionResult(
                finish_reason=NodeFinishReason.SUCCESS,
                summary=json.dumps(self.provider_payload),
            )
        if self.malformed or (self.malformed_once and len(self.contexts) == 1):
            return NodeExecutionResult(finish_reason=NodeFinishReason.SUCCESS, summary="not-json")
        source_id = f"source:{context.attempt_id[-3:]}"
        sources = [
            {
                "source_id": source_id,
                "canonical_url": f"https://example.com/{context.attempt_id}",
                "title": "Scripted evidence",
            }
        ]
        support_refs = [source_id]
        if self.reverse_sources:
            sources = [
                {
                    "source_id": "source:z",
                    "canonical_url": "https://example.com/z",
                    "title": "Z source",
                },
                {
                    "source_id": "source:a",
                    "canonical_url": "https://example.com/a",
                    "title": "A source",
                },
            ]
            support_refs = ["source:z", "source:a"]
        return NodeExecutionResult(
            finish_reason=NodeFinishReason.SUCCESS,
            summary=json.dumps(
                {
                    "schema_version": 1,
                    "sources": sources,
                    "claims": [
                        {
                            "claim_id": f"claim:w1_{context.attempt_id[-3:]}",
                            "statement": "The scripted source supports this claim.",
                            "support_refs": support_refs,
                            "counter_refs": [],
                        }
                    ],
                    "open_questions": [],
                }
            ),
        )


class BaseResolver:
    def __init__(self, graph_context: GraphContextView, capabilities=None) -> None:
        self._graph_context = graph_context
        self._capabilities = capabilities or ForbiddenCapabilities()

    def resolve(self, *, logical_name, attempt_id, policy):
        return NodeBuildDependencies(
            graph_context=self._graph_context,
            agent_context=NodeAgentContext(
                research_scope_id=RESEARCH_ID,
                node_name=logical_name,
                attempt_id=attempt_id,
                workspace_root=self._graph_context.workspace_root,
                attempt_root=f"{self._graph_context.workspace_root}/attempts/{attempt_id}",
                policy_name=policy.name,
            ),
            capabilities=self._capabilities,
        )


def _context(tmp_path) -> tuple[GraphInvocationContext, WorkUnitStore]:
    graph_context = GraphContextView(
        research_scope_id=RESEARCH_ID,
        workspace_root=f"/mnt/user-data/workspace/deep-research/{RESEARCH_ID}",
        uploads_root="/mnt/user-data/uploads",
        outputs_root=f"/mnt/user-data/outputs/deep-research/{RESEARCH_ID}",
    )
    base = BaseResolver(graph_context)
    store = WorkUnitStore(
        workspace_host_path=tmp_path,
        research_id=RESEARCH_ID,
        clock=lambda: NOW,
        monotonic=time.monotonic,
        lock_sleep=time.sleep,
        token_factory=lambda: "1" * 32,
        fault_hook=None,
    )
    controller = WorkUnitControllerDependencies(
        store=store,
        resolver=RuntimeWorkUnitDependencyResolver(graph_context, base, store),
    )
    return GraphInvocationContext(graph_context, base, controller), store


def _state() -> dict:
    return {
        "research_id": RESEARCH_ID,
        "generation": 0,
        "fixture_plan": {"wave1": ("repair", "pass")},
        "execution_trace": (),
        "gate_attempts_by_phase": {},
        "repair_budget_by_phase": {},
        "pending_work_ids": (),
        "batch_cursor": 0,
        "next_work_ordinal": 0,
        "next_attempt_ordinal_by_work_id": {},
        "work_specs_by_id": {},
        "attempts_by_id": {},
        "work_status_by_id": {},
        "active_attempt_by_work_id": {},
        "terminal_failures_by_attempt_id": {},
        "accepted_submission_refs": (),
    }


def _apply_result(state: dict, result: dict) -> dict:
    next_state = dict(state)
    preview_delta = {key: value for key, value in result.items() if key in WORK_UNIT_GATE_PREVIEW_FIELDS}
    next_state.update(preview_work_unit_update(state, preview_delta))
    for key, value in result.items():
        if key in WORK_UNIT_GATE_PREVIEW_FIELDS:
            continue
        next_state[key] = merge_trace(state.get(key, ()), value) if key == "execution_trace" else value
    return next_state


async def test_wave1_reuses_shared_kernel_with_distinct_fixture_scope_and_content(tmp_path) -> None:
    assert NODE_SPEC.capabilities == frozenset({NodeCapability.WORK_UNIT_CONTROLLER})
    assert wave1_subgraph.run_fixture_work_unit_component is run_fixture_work_unit_component
    assert not {
        "StateGraph",
        "WorkUnitStore",
        "validate_submission_candidate",
        "commit_candidate",
    } & set(vars(wave1_subgraph))
    assert tuple(intent.scope for intent in wave1_subgraph.WAVE1_FIXTURE_INTENTS) == (
        ("wave1:fixture:0",),
        ("wave1:fixture:1",),
        ("wave1:fixture:2",),
    )

    context, store = _context(tmp_path)
    gate = default_gate_defs()["wave1"]
    wrapped = _node_wrapper("wave1", NODE_SPEC, NODE_SPEC.fake_factory, {"wave1": gate})
    first = await wrapped(_state(), SimpleNamespace(context=context))
    assert first["route"] == "repair"
    assert tuple(first["work_specs_by_id"]) == (
        "g0_wave1_w0000",
        "g0_wave1_w0001",
        "g0_wave1_w0002",
    )
    records = await store.load_records()
    assert len(records) == 3
    output_bytes = await store.read_canonical_bytes(records[0].output_refs[0].path, max_bytes=1024)
    assert b'"phase":"wave1"' in output_bytes
    assert b"wave0" not in output_bytes

    second = await wrapped(_apply_result(_state(), first), SimpleNamespace(context=context))
    assert second["route"] == "pass"
    assert tuple(second["work_specs_by_id"]) == (
        "g0_wave1_w0003",
        "g0_wave1_w0004",
        "g0_wave1_w0005",
    )
    assert len(await store.load_records()) == 6


async def test_real_wave1_crosses_worker_context_artifact_validator_and_ledger(tmp_path) -> None:
    """@impl EVH-003, EVH-004, EVH-008"""
    graph_context = GraphContextView(
        research_scope_id=RESEARCH_ID,
        workspace_root=f"/mnt/user-data/workspace/deep-research/{RESEARCH_ID}",
        uploads_root="/mnt/user-data/uploads",
        outputs_root=f"/mnt/user-data/outputs/deep-research/{RESEARCH_ID}",
    )
    capabilities = ScriptedWave1Capabilities(malformed_once=True)
    store = WorkUnitStore(
        workspace_host_path=tmp_path,
        research_id=RESEARCH_ID,
        clock=lambda: NOW,
        monotonic=time.monotonic,
        lock_sleep=time.sleep,
        token_factory=lambda: "2" * 32,
        fault_hook=None,
    )
    controller = WorkUnitControllerDependencies(
        store=store,
        resolver=RuntimeWorkUnitDependencyResolver(
            graph_context,
            BaseResolver(graph_context, capabilities),
            store,
        ),
    )
    state = _state() | {
        "topic_registry": (
            {
                "topic_id": "storage",
                "title": "Storage",
                "scope": "Storage economics",
                "must_answer_bindings": ("Q1",),
            },
        )
    }

    result = await wave1_subgraph.run_wave1_work_units_real(
        state,
        controller=controller,
        topic_registry=state["topic_registry"],
        capabilities=capabilities,
        wave0_urls=frozenset(),
        clock=lambda: NOW,
    )

    assert len(capabilities.contexts) == 2
    request = capabilities.requests[0]
    assert request.minimum_tool_calls == 1
    assert request.tool_call_limit == 3
    assert "content_ref" not in request.expected_output
    assert "content_hash" not in request.expected_output
    assert "byte_count" not in request.expected_output
    assert "is_new_vs_wave0" not in request.expected_output
    assert capabilities.requests[1].tools_enabled is False
    assert "/work/g0_wave1_w0000/g0_wave1_w0000_a00" in capabilities.contexts[0].attempt_root
    records = await store.load_records()
    assert len(records) == 1
    assert result.parent_update["accepted_submission_refs"] == (records[0].record_hash,)
    assert records[0].source_refs[0].content_ref.endswith("/cache/source-0.json")
    assert "forged" not in records[0].source_refs[0].content_ref
    persisted = await store.read_canonical_bytes(records[0].result_ref, max_bytes=256 * 1024)
    assert json.loads(persisted)["claims"][0]["support_refs"] == [records[0].source_refs[0].source_id]


@pytest.mark.parametrize(
    "case",
    [pytest.param(SHAPE_CASES["shape-wave1-source-order"], id="shape-wave1-source-order")],
)
async def test_real_wave1_canonicalizes_provider_source_order_before_candidate_validation(tmp_path, case) -> None:
    graph_context = GraphContextView(
        research_scope_id=RESEARCH_ID,
        workspace_root=f"/mnt/user-data/workspace/deep-research/{RESEARCH_ID}",
        uploads_root="/mnt/user-data/uploads",
        outputs_root=f"/mnt/user-data/outputs/deep-research/{RESEARCH_ID}",
    )
    capabilities = ScriptedWave1Capabilities(provider_payload=thaw_provider_shape_payload(case.payload))
    store = WorkUnitStore(
        workspace_host_path=tmp_path,
        research_id=RESEARCH_ID,
        clock=lambda: NOW,
        monotonic=time.monotonic,
        lock_sleep=time.sleep,
        token_factory=lambda: "7" * 32,
        fault_hook=None,
    )
    controller = WorkUnitControllerDependencies(
        store=store,
        resolver=RuntimeWorkUnitDependencyResolver(
            graph_context,
            BaseResolver(graph_context, capabilities),
            store,
        ),
    )
    topics = ({"topic_id": "storage", "title": "Storage", "scope": "Storage economics"},)

    result = await wave1_subgraph.run_wave1_work_units_real(
        _state() | {"topic_registry": topics},
        controller=controller,
        topic_registry=topics,
        capabilities=capabilities,
        wave0_urls=frozenset(),
        clock=lambda: NOW,
    )

    records = await store.load_records()
    assert result.parent_update["accepted_submission_refs"] == (records[0].record_hash,)
    assert tuple(source.source_id for source in records[0].source_refs) == ("source:a", "source:z")
    persisted = json.loads(await store.read_canonical_bytes(records[0].result_ref, max_bytes=256 * 1024))
    observed = {
        "source_ids": persisted["source_ids"],
        "support_refs": persisted["claims"][0]["support_refs"],
    }
    assert observed == thaw_provider_shape_payload(case.expected_payload)


@pytest.mark.parametrize(
    "case",
    [pytest.param(SHAPE_CASES["shape-wave1-malformed-submit"], id="shape-wave1-malformed-submit")],
)
async def test_real_wave1_malformed_output_becomes_typed_worker_failure_without_ledger(tmp_path, case) -> None:
    graph_context = GraphContextView(
        research_scope_id=RESEARCH_ID,
        workspace_root=f"/mnt/user-data/workspace/deep-research/{RESEARCH_ID}",
        uploads_root="/mnt/user-data/uploads",
        outputs_root=f"/mnt/user-data/outputs/deep-research/{RESEARCH_ID}",
    )
    capabilities = ScriptedWave1Capabilities(provider_payload=thaw_provider_shape_payload(case.payload))
    store = WorkUnitStore(
        workspace_host_path=tmp_path,
        research_id=RESEARCH_ID,
        clock=lambda: NOW,
        monotonic=time.monotonic,
        lock_sleep=time.sleep,
        token_factory=lambda: "4" * 32,
        fault_hook=None,
    )
    controller = WorkUnitControllerDependencies(
        store=store,
        resolver=RuntimeWorkUnitDependencyResolver(
            graph_context,
            BaseResolver(graph_context, capabilities),
            store,
        ),
    )
    topics = ({"topic_id": "storage", "title": "Storage", "scope": "Storage economics"},)

    result = await wave1_subgraph.run_wave1_work_units_real(
        _state() | {"topic_registry": topics},
        controller=controller,
        topic_registry=topics,
        capabilities=capabilities,
        wave0_urls=frozenset(),
        clock=lambda: NOW,
    )

    assert result.parent_update["accepted_submission_refs"] == ()
    assert tuple(result.parent_update["work_status_by_id"].values()) == ("failed",)
    assert await store.load_records() == ()
    assert case.expected_error_code == "source_ids_mismatch"
