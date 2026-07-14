from __future__ import annotations

import time
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from deerflow_deep_research.domain.context import GraphContextView, NodeAgentContext
from deerflow_deep_research.domain.invocation import GraphInvocationContext, WorkUnitControllerDependencies
from deerflow_deep_research.domain.lifecycle import WorkUnitStorageReason
from deerflow_deep_research.domain.node_spec import NodeBuildDependencies, NodeCapability
from deerflow_deep_research.domain.state import WORK_UNIT_GATE_PREVIEW_FIELDS, merge_trace, preview_work_unit_update
from deerflow_deep_research.domain.work_units import WORK_UNIT_GATE_VIEW_KEY, WorkSpecRef, canonical_json_bytes
from deerflow_deep_research.engine.work_units.kernel import allocate_attempt, materialize_work_spec
from deerflow_deep_research.graph.builder import _node_wrapper
from deerflow_deep_research.graph.components.work_units import reconcile_parent_ledger_authority
from deerflow_deep_research.graph.nodes.gate_adapter import default_gate_defs
from deerflow_deep_research.graph.nodes.wave0 import NODE_SPEC
from deerflow_deep_research.graph.nodes.wave0.subgraph import WAVE0_FIXTURE_INTENTS, run_wave0_work_units
from deerflow_deep_research.runtime.projection import RuntimeWorkUnitDependencyResolver
from deerflow_deep_research.runtime.work_unit_storage import WorkUnitStoreError
from deerflow_deep_research.runtime.work_unit_store import WorkUnitStore

RESEARCH_ID = "r_" + "A" * 43
NOW = datetime(2026, 7, 14, tzinfo=UTC)


class ForbiddenCapabilities:
    async def run_agent(self, *, context, request):
        raise AssertionError("fixture work must not call an agent")


def _graph_context() -> GraphContextView:
    return GraphContextView(
        research_scope_id=RESEARCH_ID,
        workspace_root=f"/mnt/user-data/workspace/deep-research/{RESEARCH_ID}",
        uploads_root="/mnt/user-data/uploads",
        outputs_root=f"/mnt/user-data/outputs/deep-research/{RESEARCH_ID}",
    )


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


def _store(tmp_path) -> WorkUnitStore:
    return WorkUnitStore(
        workspace_host_path=tmp_path,
        research_id=RESEARCH_ID,
        clock=lambda: NOW,
        monotonic=time.monotonic,
        lock_sleep=time.sleep,
        token_factory=lambda: "0" * 32,
        fault_hook=None,
    )


def _context(tmp_path) -> tuple[GraphInvocationContext, WorkUnitStore]:
    graph_context = _graph_context()
    base = BaseResolver(graph_context)
    store = _store(tmp_path)
    controller = WorkUnitControllerDependencies(
        store=store,
        resolver=RuntimeWorkUnitDependencyResolver(graph_context, base, store),
    )
    return GraphInvocationContext(graph_context, base, controller), store


def _state() -> dict:
    return {
        "research_id": RESEARCH_ID,
        "generation": 0,
        "fixture_plan": {"wave0": ("repair", "pass")},
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
        if key == "execution_trace":
            next_state[key] = merge_trace(state.get(key, ()), value)
        else:
            next_state[key] = value
    return next_state


async def test_wave0_shared_component_replays_and_quality_repair_allocates_new_work(tmp_path) -> None:
    assert NODE_SPEC.capabilities == frozenset({NodeCapability.WORK_UNIT_CONTROLLER})
    gate = default_gate_defs()["wave0"]
    assert tuple(rule.name for rule in gate.rules[:2]) == (
        "work_unit_completion",
        "fixture_sequence_wave0",
    )

    context, store = _context(tmp_path)
    wrapped = _node_wrapper("wave0", NODE_SPEC, NODE_SPEC.fake_factory, {"wave0": gate})
    first = await wrapped(_state(), SimpleNamespace(context=context))
    assert WORK_UNIT_GATE_VIEW_KEY not in first
    assert first["route"] == "repair"
    assert tuple(first["work_specs_by_id"]) == (
        "g0_wave0_w0000",
        "g0_wave0_w0001",
        "g0_wave0_w0002",
    )
    assert tuple(first["attempts_by_id"]) == tuple(f"{work_id}_a00" for work_id in first["work_specs_by_id"])
    assert len(first["accepted_submission_refs"]) == 3
    assert first["next_work_ordinal"] == 3
    assert first["pending_work_ids"] == ()
    assert len(await store.load_records()) == 3

    replay_state = _state()
    replay = await wrapped(replay_state, SimpleNamespace(context=context))
    assert replay["accepted_submission_refs"] == first["accepted_submission_refs"]
    assert len(await store.load_records()) == 3

    second_state = _apply_result(_state(), first)
    second = await wrapped(second_state, SimpleNamespace(context=context))
    assert second["route"] == "pass"
    assert tuple(second["work_specs_by_id"]) == (
        "g0_wave0_w0003",
        "g0_wave0_w0004",
        "g0_wave0_w0005",
    )
    assert second["next_work_ordinal"] == 6
    assert len(await store.load_records()) == 6


async def test_fault_before_submit_node_return_replays_ledger_ahead_of_parent_checkpoint(tmp_path) -> None:
    context, store = _context(tmp_path)
    assert context.work_units is not None

    def fault(point: str) -> None:
        if point == "before_submit_node_return":
            raise RuntimeError(point)

    with pytest.raises(RuntimeError, match="before_submit_node_return"):
        await run_wave0_work_units(
            _state(),
            controller=context.work_units,
            clock=lambda: NOW,
            fault_hook=fault,
        )
    assert len(await store.load_records()) == 3

    replay = await run_wave0_work_units(
        _state(),
        controller=context.work_units,
        clock=lambda: NOW,
    )
    assert len(replay.parent_update["accepted_submission_refs"]) == 3
    assert len(await store.load_records()) == 3


async def test_fault_after_returned_state_update_leaves_matching_checkpoint_and_ledger(tmp_path) -> None:
    context, store = _context(tmp_path)
    gate = default_gate_defs()["wave0"]
    wrapped = _node_wrapper("wave0", NODE_SPEC, NODE_SPEC.fake_factory, {"wave0": gate})
    returned = await wrapped(_state(), SimpleNamespace(context=context))

    class SimulatedCrash(RuntimeError):
        pass

    checkpoint = None
    with pytest.raises(SimulatedCrash):
        checkpoint = _apply_result(_state(), returned)
        raise SimulatedCrash("after_returned_state_update")
    assert checkpoint is not None
    records = await store.load_records()
    assert set(checkpoint["accepted_submission_refs"]) == {record.record_hash for record in records}


async def test_reconcile_matrix_catches_up_ledger_ahead_and_accepts_matching_checkpoint(tmp_path) -> None:
    context, store = _context(tmp_path)
    assert context.work_units is not None
    first = await run_wave0_work_units(
        _state(),
        controller=context.work_units,
        clock=lambda: NOW,
    )
    records = await reconcile_parent_ledger_authority(_state(), context.work_units)
    assert len(records) == 3

    checkpoint = _apply_result(_state(), first.parent_update)
    matching = await reconcile_parent_ledger_authority(checkpoint, context.work_units)
    assert tuple(record.record_hash for record in matching) == first.parent_update["accepted_submission_refs"]
    assert len(await store.load_records()) == 3


@pytest.mark.parametrize("checkpoint_ahead", ["accepted_ref", "submitted_status"])
async def test_reconcile_matrix_rejects_checkpoint_ahead_without_ledger_and_does_not_repair(
    tmp_path,
    checkpoint_ahead: str,
) -> None:
    context, store = _context(tmp_path)
    assert context.work_units is not None
    state = _state()
    if checkpoint_ahead == "accepted_ref":
        state["accepted_submission_refs"] = ("h_" + "Z" * 43,)
    else:
        state["work_status_by_id"] = {"g0_wave0_w0000_a00": "submitted"}
    before = dict(state)

    with pytest.raises(WorkUnitStoreError) as excinfo:
        await run_wave0_work_units(
            state,
            controller=context.work_units,
            clock=lambda: NOW,
        )
    assert excinfo.value.reason is WorkUnitStorageReason.LEDGER_CORRUPT
    assert state == before
    assert await store.load_records() == ()


@pytest.mark.parametrize("artifact_defect", ["missing", "mutated"])
async def test_reconcile_matrix_rejects_diverged_accepted_artifact_without_checkpoint_repair(
    tmp_path,
    artifact_defect: str,
) -> None:
    context, store = _context(tmp_path)
    assert context.work_units is not None
    first = await run_wave0_work_units(
        _state(),
        controller=context.work_units,
        clock=lambda: NOW,
    )
    checkpoint = _apply_result(_state(), first.parent_update)
    before = dict(checkpoint)
    record = (await store.load_records())[0]
    host_output = tmp_path / record.output_refs[0].path.removeprefix("workspace/")
    if artifact_defect == "missing":
        host_output.unlink()
    else:
        host_output.write_bytes(b"mutated")

    with pytest.raises(WorkUnitStoreError) as excinfo:
        await reconcile_parent_ledger_authority(checkpoint, context.work_units)
    assert excinfo.value.reason is WorkUnitStorageReason.ACCEPTED_ARTIFACT_DIVERGED
    assert checkpoint == before
    assert len(await store.load_records()) == 3


async def test_reconcile_matrix_maps_broken_ledger_to_typed_corruption_without_dispatch(tmp_path) -> None:
    context, store = _context(tmp_path)
    assert context.work_units is not None
    evidence = tmp_path / "deep-research" / RESEARCH_ID / "evidence"
    evidence.mkdir(parents=True)
    ledger = evidence / "submissions.jsonl"
    ledger.write_bytes(b'{"broken":true}\n')
    ledger.chmod(0o600)

    with pytest.raises(WorkUnitStoreError) as excinfo:
        await run_wave0_work_units(
            _state(),
            controller=context.work_units,
            clock=lambda: NOW,
        )
    assert excinfo.value.reason is WorkUnitStorageReason.LEDGER_CORRUPT


async def test_reconcile_matrix_supersedes_active_retry_when_sibling_record_already_won(tmp_path) -> None:
    context, store = _context(tmp_path)
    assert context.work_units is not None
    first = await run_wave0_work_units(
        _state(),
        controller=context.work_units,
        clock=lambda: NOW,
    )
    state = _apply_result(_state(), first.parent_update)
    work_id = "g0_wave0_w0000"
    accepted_attempt = f"{work_id}_a00"
    retry_attempt = f"{work_id}_a01"
    state["accepted_submission_refs"] = ()
    state["attempts_by_id"] = {
        **state["attempts_by_id"],
        retry_attempt: {
            "created_at": NOW,
            "started_at": None,
            "expires_at": None,
            "terminal_at": None,
            "terminal_code": None,
        },
    }
    state["work_status_by_id"] = {
        **state["work_status_by_id"],
        retry_attempt: "pending",
    }
    state["active_attempt_by_work_id"] = {work_id: retry_attempt}
    state["pending_work_ids"] = (work_id,)
    state["next_attempt_ordinal_by_work_id"] = {
        **state["next_attempt_ordinal_by_work_id"],
        work_id: 2,
    }

    reconciled = await run_wave0_work_units(
        state,
        controller=context.work_units,
        clock=lambda: NOW,
    )
    record = next(record for record in await store.load_records() if record.work_id == work_id)
    assert reconciled.gate_view.planned_work_ids == (work_id,)
    assert reconciled.gate_view.terminal_attempt_by_work_id == {work_id: accepted_attempt}
    assert reconciled.parent_update["work_status_by_id"] == {retry_attempt: "cancelled"}
    assert reconciled.parent_update["attempts_by_id"][retry_attempt]["terminal_code"] == "superseded"
    assert reconciled.parent_update["active_attempt_by_work_id"] == {}
    assert reconciled.parent_update["accepted_submission_refs"] == (record.record_hash,)
    assert len(await store.load_records()) == 3


async def test_reconcile_matrix_executes_active_retry_and_copies_canonical_first_spec(tmp_path) -> None:
    context, store = _context(tmp_path)
    assert context.work_units is not None
    spec = materialize_work_spec(
        research_id=RESEARCH_ID,
        generation=0,
        phase="wave0",
        work_ordinal=0,
        intent=WAVE0_FIXTURE_INTENTS[0],
    )
    first_attempt = allocate_attempt(spec, attempt_ordinal=0, created_at=NOW)
    retry = allocate_attempt(spec, attempt_ordinal=1, created_at=NOW)
    await store.write_work_spec(spec, first_attempt)
    state = _state()
    state.update(
        pending_work_ids=(spec.work_id,),
        next_work_ordinal=1,
        next_attempt_ordinal_by_work_id={spec.work_id: 2},
        work_specs_by_id={
            spec.work_id: WorkSpecRef(worker_role=spec.worker_role, spec_hash=spec.spec_hash).model_dump(mode="json")
        },
        attempts_by_id={
            first_attempt.attempt_id: {
                "created_at": NOW,
                "started_at": NOW,
                "expires_at": None,
                "terminal_at": NOW,
                "terminal_code": "worker_failed",
            },
            retry.attempt_id: {
                "created_at": NOW,
                "started_at": None,
                "expires_at": None,
                "terminal_at": None,
                "terminal_code": None,
            },
        },
        work_status_by_id={first_attempt.attempt_id: "failed", retry.attempt_id: "pending"},
        active_attempt_by_work_id={spec.work_id: retry.attempt_id},
    )

    completed = await run_wave0_work_units(
        state,
        controller=context.work_units,
        clock=lambda: NOW,
    )
    assert completed.parent_update["work_status_by_id"] == {retry.attempt_id: "submitted"}
    first_ref = (
        tmp_path / "deep-research" / RESEARCH_ID / "work" / spec.work_id / first_attempt.attempt_id / "work-spec.json"
    )
    retry_ref = first_ref.parent.parent / retry.attempt_id / "work-spec.json"
    assert first_ref.read_bytes() == retry_ref.read_bytes() == canonical_json_bytes(spec)
    assert len(await store.load_records()) == 1


@pytest.mark.parametrize(
    ("terminal_status", "terminal_code"),
    [("failed", "worker_failed"), ("timed_out", "deadline_exceeded")],
)
async def test_failed_or_timed_out_work_allocates_one_fresh_retry_through_shared_component(
    tmp_path,
    terminal_status: str,
    terminal_code: str,
) -> None:
    context, store = _context(tmp_path)
    assert context.work_units is not None
    spec = materialize_work_spec(
        research_id=RESEARCH_ID,
        generation=0,
        phase="wave0",
        work_ordinal=0,
        intent=WAVE0_FIXTURE_INTENTS[0],
    )
    failed = allocate_attempt(spec, attempt_ordinal=0, created_at=NOW)
    await store.write_work_spec(spec, failed)
    state = _state()
    state.update(
        next_work_ordinal=1,
        next_attempt_ordinal_by_work_id={spec.work_id: 1},
        work_specs_by_id={
            spec.work_id: WorkSpecRef(worker_role=spec.worker_role, spec_hash=spec.spec_hash).model_dump(mode="json")
        },
        attempts_by_id={
            failed.attempt_id: {
                "created_at": NOW,
                "started_at": NOW,
                "expires_at": None,
                "terminal_at": NOW,
                "terminal_code": terminal_code,
            }
        },
        work_status_by_id={failed.attempt_id: terminal_status},
    )

    completed = await run_wave0_work_units(
        state,
        controller=context.work_units,
        clock=lambda: NOW,
    )

    retry_id = f"{spec.work_id}_a01"
    assert completed.gate_view.planned_work_ids == (spec.work_id,)
    assert completed.parent_update["work_status_by_id"] == {retry_id: "submitted"}
    assert completed.parent_update["next_attempt_ordinal_by_work_id"] == {spec.work_id: 2}
    record = (await store.load_records())[0]
    assert record.attempt_id == retry_id
    first_ref = tmp_path / "deep-research" / RESEARCH_ID / "work" / spec.work_id / failed.attempt_id / "work-spec.json"
    retry_ref = first_ref.parent.parent / retry_id / "work-spec.json"
    assert first_ref.read_bytes() == retry_ref.read_bytes() == canonical_json_bytes(spec)
