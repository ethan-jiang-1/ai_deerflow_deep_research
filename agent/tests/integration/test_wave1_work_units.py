from __future__ import annotations

import time
from datetime import UTC, datetime
from types import SimpleNamespace

from deerflow_deep_research.domain.context import GraphContextView, NodeAgentContext
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

RESEARCH_ID = "r_" + "B" * 43
NOW = datetime(2026, 7, 14, tzinfo=UTC)


class ForbiddenCapabilities:
    async def run_agent(self, *, context, request):
        raise AssertionError("fixture work must not call an agent")


class BaseResolver:
    def __init__(self, graph_context: GraphContextView) -> None:
        self._graph_context = graph_context

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
            capabilities=ForbiddenCapabilities(),
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
