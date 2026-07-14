from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from deerflow_deep_research.domain.context import GraphContextView, NodeAgentContext
from deerflow_deep_research.domain.failure_codes import FailureCode
from deerflow_deep_research.domain.gate import GateDefinition, GateRule, PhaseVerdict
from deerflow_deep_research.domain.invocation import (
    GraphInvocationContext,
    WorkUnitControllerDependencies,
)
from deerflow_deep_research.domain.node_spec import NodeBuildDependencies, NodeCapability, PolicyRef
from deerflow_deep_research.domain.work_units import (
    WORK_UNIT_GATE_VIEW_KEY,
    Attempt,
    WorkSpec,
    WorkUnitGateView,
    canonical_json_bytes,
    compute_work_spec_hash,
)
from deerflow_deep_research.engine.work_units.kernel import WorkUnitCompletionRule
from deerflow_deep_research.graph.builder import _node_wrapper
from deerflow_deep_research.graph.registry import load_research_node_specs
from deerflow_deep_research.runtime.projection import RuntimeWorkUnitDependencyResolver

RESEARCH_ID = "r_" + "A" * 43
NOW = datetime(2026, 7, 14, tzinfo=UTC)


class Capabilities:
    async def run_agent(self, *, context, request):
        raise AssertionError("unused")


def _graph() -> GraphContextView:
    return GraphContextView(
        research_scope_id=RESEARCH_ID,
        workspace_root=f"/mnt/user-data/workspace/deep-research/{RESEARCH_ID}",
        uploads_root="/mnt/user-data/uploads",
        outputs_root=f"/mnt/user-data/outputs/deep-research/{RESEARCH_ID}",
    )


class BaseResolver:
    def resolve(self, *, logical_name, attempt_id, policy):
        graph = _graph()
        return NodeBuildDependencies(
            graph_context=graph,
            agent_context=NodeAgentContext(
                research_scope_id=RESEARCH_ID,
                node_name=logical_name,
                attempt_id=attempt_id,
                workspace_root=graph.workspace_root,
                attempt_root=f"{graph.workspace_root}/attempts/{attempt_id}",
                policy_name=policy.name,
            ),
            capabilities=Capabilities(),
        )


class Store:
    def __init__(self) -> None:
        self.written = []
        self.files = {}

    async def read_canonical_bytes(self, relative_ref: str, *, max_bytes: int) -> bytes:
        try:
            value = self.files[relative_ref]
        except KeyError as exc:
            raise FileNotFoundError("artifact_missing") from exc
        assert len(value) <= max_bytes
        return value

    async def write_work_spec(self, spec, attempt) -> None:
        self.written.append((spec, attempt))
        ref = f"workspace/deep-research/{spec.research_id}/work/{spec.work_id}/{attempt.attempt_id}/work-spec.json"
        value = canonical_json_bytes(spec)
        if ref in self.files and self.files[ref] != value:
            raise ValueError("artifact_write_conflict")
        self.files[ref] = value

    async def load_records(self):
        return ()

    async def read_validation_plan(self, plan):
        return {}

    async def commit_candidate(self, candidate, *, scope, validator_version=1, passed_checks=()):
        raise AssertionError("not used")

    def infrastructure_error(self, reason):
        return RuntimeError(reason)

    def attempt_artifact_writer(self, spec, attempt):
        return SimpleNamespace(write_result=None, write_output=None)


class WorkResolver:
    async def resolve_worker(self, **_kwargs):
        raise AssertionError("not used")


class NoIOStore:
    async def read_canonical_bytes(self, relative_ref, *, max_bytes):
        raise AssertionError("wrapper gate validation must not read artifacts")

    async def load_records(self):
        raise AssertionError("wrapper gate validation must not read the ledger")

    async def read_validation_plan(self, plan):
        raise AssertionError("wrapper gate validation must not execute a read plan")

    async def commit_candidate(self, candidate, *, scope, validator_version=1, passed_checks=()):
        raise AssertionError("wrapper gate validation must not submit")

    def infrastructure_error(self, reason):
        raise AssertionError("wrapper gate validation must not construct an infrastructure error")

    async def write_work_spec(self, spec, attempt):
        raise AssertionError("wrapper gate validation must not write a spec")

    def attempt_artifact_writer(self, spec, attempt):
        raise AssertionError("wrapper gate validation must not resolve a writer")


def _spec_attempt() -> tuple[WorkSpec, Attempt]:
    payload = {
        "schema_version": 1,
        "research_id": RESEARCH_ID,
        "generation": 0,
        "phase": "wave0",
        "work_id": "g0_wave0_w0000",
        "work_ordinal": 0,
        "worker_role": "fixture_worker",
        "scope": ("topic",),
        "result_contract": "fixture.work-unit",
        "result_schema_version": 1,
        "required_outputs": (),
    }
    payload["spec_hash"] = compute_work_spec_hash(payload)
    spec = WorkSpec.model_validate(payload)
    attempt = Attempt(
        schema_version=1,
        research_id=RESEARCH_ID,
        generation=0,
        phase="wave0",
        work_id=spec.work_id,
        attempt_id=f"{spec.work_id}_a00",
        attempt_ordinal=0,
        spec_hash=spec.spec_hash,
        status="pending",
        created_at=NOW,
        started_at=None,
        expires_at=None,
        terminal_at=None,
        terminal_code=None,
    )
    return spec, attempt


async def test_per_work_resolver_projects_canonical_root_and_forces_nested_authority_none() -> None:
    store = Store()
    resolver = RuntimeWorkUnitDependencyResolver(_graph(), BaseResolver(), store)
    spec, attempt = _spec_attempt()
    worker = await resolver.resolve_worker(
        logical_name="wave0",
        work_spec=spec,
        attempt=attempt,
        policy=PolicyRef("wave0-policy", "v1"),
    )
    assert worker.node_dependencies.work_units is None
    assert worker.node_dependencies.agent_context.attempt_root.endswith(f"/work/{spec.work_id}/{attempt.attempt_id}")
    assert store.written == [(spec, attempt)]


async def test_per_work_resolver_rehydrates_retry_from_canonical_first_spec() -> None:
    store = Store()
    resolver = RuntimeWorkUnitDependencyResolver(_graph(), BaseResolver(), store)
    spec, attempt = _spec_attempt()
    await resolver.resolve_worker(
        logical_name="wave0",
        work_spec=spec,
        attempt=attempt,
        policy=PolicyRef("wave0-policy", "v1"),
    )
    retry = Attempt.model_validate(
        {
            **attempt.model_dump(mode="python"),
            "attempt_id": f"{spec.work_id}_a01",
            "attempt_ordinal": 1,
        }
    )
    worker = await resolver.resolve_worker(
        logical_name="wave0",
        work_spec=spec,
        attempt=retry,
        policy=PolicyRef("wave0-policy", "v1"),
    )
    assert worker.work_spec == spec
    assert store.written == [(spec, attempt), (spec, retry)]
    assert store.files[
        f"workspace/deep-research/{RESEARCH_ID}/work/{spec.work_id}/{retry.attempt_id}/work-spec.json"
    ] == canonical_json_bytes(spec)


async def test_per_work_resolver_rejects_divergent_first_spec_bytes() -> None:
    store = Store()
    resolver = RuntimeWorkUnitDependencyResolver(_graph(), BaseResolver(), store)
    spec, attempt = _spec_attempt()
    first_ref = f"workspace/deep-research/{RESEARCH_ID}/work/{spec.work_id}/{attempt.attempt_id}/work-spec.json"
    store.files[first_ref] = b"{}"
    with pytest.raises(ValueError, match="work_spec_replay_invalid"):
        await resolver.resolve_worker(
            logical_name="wave0",
            work_spec=spec,
            attempt=attempt,
            policy=PolicyRef("wave0-policy", "v1"),
        )


async def test_declaring_controller_requires_runtime_bundle_before_factory() -> None:
    base_spec = load_research_node_specs()["wave0"]
    declaring = replace(base_spec, capabilities=frozenset({NodeCapability.WORK_UNIT_CONTROLLER}))
    factory_called = False

    def factory(dependencies):
        nonlocal factory_called
        factory_called = True

        async def node(_state):
            return {}

        return node

    wrapped = _node_wrapper("wave0", declaring, factory, {})
    context = GraphInvocationContext(graph_context=_graph(), dependency_resolver=BaseResolver())
    with pytest.raises(ValueError, match="work_unit_capability_missing"):
        await wrapped({}, SimpleNamespace(context=context))
    assert not factory_called


def test_only_closed_node_capability_is_accepted() -> None:
    spec = load_research_node_specs()["wave0"]
    assert spec.capabilities == frozenset({NodeCapability.WORK_UNIT_CONTROLLER})
    with pytest.raises(TypeError, match="capabilities"):
        replace(spec, capabilities=frozenset({"work_unit_controller"}))


async def test_declaring_wrapper_previews_work_delta_and_strips_reserved_view() -> None:
    base_spec = load_research_node_specs()["wave0"]
    declaring = replace(base_spec, capabilities=frozenset({NodeCapability.WORK_UNIT_CONTROLLER}))
    work_id = "g0_wave0_w0000"
    attempt_id = f"{work_id}_a00"
    record_hash = "h_" + "B" * 43
    view = WorkUnitGateView(
        drained=True,
        planned_work_ids=(work_id,),
        terminal_attempt_by_work_id={work_id: attempt_id},
        accepted_record_by_work_id={work_id: record_hash},
        failure_summaries=(),
    )
    node_delta = {
        "work_specs_by_id": {work_id: {"worker_role": "fixture_worker", "spec_hash": "h_" + "C" * 43}},
        "attempts_by_id": {
            attempt_id: {
                "created_at": NOW,
                "started_at": NOW,
                "expires_at": None,
                "terminal_at": NOW,
                "terminal_code": "accepted",
            }
        },
        "work_status_by_id": {attempt_id: "submitted"},
        "active_attempt_by_work_id": {},
        "terminal_failures_by_attempt_id": {},
        "accepted_submission_refs": (record_hash,),
        WORK_UNIT_GATE_VIEW_KEY: view,
    }

    def factory(dependencies):
        assert dependencies.work_units is not None

        async def node(_state):
            return dict(node_delta)

        return node

    completion = WorkUnitCompletionRule()
    gate = GateDefinition(
        phase="wave0",
        rules=(GateRule("work_unit_completion", completion.evaluate, FailureCode.WORK_FAILED),),
        route_map={PhaseVerdict.PASS: "pass"},
    )
    wrapped = _node_wrapper("wave0", declaring, factory, {"wave0": gate})
    controller = WorkUnitControllerDependencies(store=NoIOStore(), resolver=WorkResolver())
    context = GraphInvocationContext(graph_context=_graph(), dependency_resolver=BaseResolver(), work_units=controller)
    prior_ref = "h_" + "D" * 43
    state = {"generation": 0, "execution_trace": (), "accepted_submission_refs": (prior_ref,)}
    result = await wrapped(state, SimpleNamespace(context=context))
    assert WORK_UNIT_GATE_VIEW_KEY not in result
    assert result["accepted_submission_refs"] == (record_hash,)
    assert result["route"] == "pass"
    assert state == {"generation": 0, "execution_trace": (), "accepted_submission_refs": (prior_ref,)}
    assert WORK_UNIT_GATE_VIEW_KEY in node_delta
