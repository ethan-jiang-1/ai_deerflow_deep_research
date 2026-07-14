from __future__ import annotations

import asyncio
import base64
import hashlib
from datetime import UTC, datetime, timedelta

import pytest

from deerflow_deep_research.domain.invocation import WorkUnitControllerDependencies
from deerflow_deep_research.domain.work_units import (
    VALIDATOR_V1_PASSED_CHECKS,
    Attempt,
    CandidateResult,
    SubmissionRecord,
    compute_candidate_hash,
    compute_record_hash,
)
from deerflow_deep_research.engine.work_units.kernel import WorkIntent, allocate_attempt, materialize_work_spec
from deerflow_deep_research.graph.components.work_units import (
    WorkUnitComponentConfig,
    run_work_unit_component,
    submit_candidate_if_active,
)

RESEARCH_ID = "r_" + "A" * 43
NOW = datetime(2026, 7, 14, tzinfo=UTC)


def _hash(data: bytes) -> str:
    return "h_" + base64.urlsafe_b64encode(hashlib.sha256(data).digest()).decode("ascii").rstrip("=")


def _intents(count: int) -> tuple[WorkIntent, ...]:
    return tuple(
        WorkIntent(
            worker_role="fixture_worker",
            scope=(f"topic:{index}",),
            result_contract="fixture.work-unit",
            result_schema_version=1,
            required_outputs=(),
        )
        for index in range(count)
    )


async def _worker(spec, attempt) -> CandidateResult:
    await asyncio.sleep((2 - spec.work_ordinal % 3) * 0.001)
    root = f"workspace/deep-research/{RESEARCH_ID}/work/{spec.work_id}/{attempt.attempt_id}"
    result_bytes = f"result:{spec.work_id}".encode()
    payload = {
        "schema_version": 1,
        "research_id": RESEARCH_ID,
        "generation": 0,
        "phase": "wave0",
        "work_id": spec.work_id,
        "attempt_id": attempt.attempt_id,
        "worker_role": spec.worker_role,
        "spec_hash": spec.spec_hash,
        "result_contract": spec.result_contract,
        "result_ref": f"{root}/result.json",
        "result_hash": _hash(result_bytes),
        "result_schema_version": 1,
        "result_byte_count": len(result_bytes),
        "output_refs": (),
        "source_refs": (),
    }
    payload["candidate_hash"] = compute_candidate_hash(payload)
    return CandidateResult.model_validate(payload)


def _submitter(records: dict[str, SubmissionRecord] | None = None):
    records = records if records is not None else {}
    previous: str | None = None

    async def submit(spec, _attempt, candidate) -> SubmissionRecord:
        nonlocal previous
        payload = candidate.model_dump(mode="python")
        payload.update(
            scope=spec.scope,
            validator_version=1,
            passed_checks=VALIDATOR_V1_PASSED_CHECKS,
            submitted_at=NOW,
            previous_record_hash=previous,
        )
        payload["record_hash"] = compute_record_hash(payload)
        record = SubmissionRecord.model_validate(payload)
        previous = record.record_hash
        records[spec.work_id] = record
        return record

    return submit


class _NoAccessStore:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def read_canonical_bytes(self, relative_ref, *, max_bytes):
        self.calls.append("read_canonical_bytes")
        raise AssertionError("store access forbidden")

    async def load_records(self):
        self.calls.append("load_records")
        raise AssertionError("store access forbidden")

    async def read_validation_plan(self, plan):
        self.calls.append("read_validation_plan")
        raise AssertionError("store access forbidden")

    async def commit_candidate(self, candidate, *, scope, validator_version=1, passed_checks=()):
        self.calls.append("commit_candidate")
        raise AssertionError("store access forbidden")

    def infrastructure_error(self, reason):
        return RuntimeError(reason)

    async def write_work_spec(self, spec, attempt):
        self.calls.append("write_work_spec")
        raise AssertionError("store access forbidden")

    def attempt_artifact_writer(self, spec, attempt):
        self.calls.append("attempt_artifact_writer")
        raise AssertionError("store access forbidden")


class _UnusedResolver:
    async def resolve_worker(self, **_kwargs):
        raise AssertionError("resolver access forbidden")


async def test_component_runs_three_concurrent_workers_and_multiple_refill_batches() -> None:
    result = await run_work_unit_component(
        {},
        config=WorkUnitComponentConfig(
            research_id=RESEARCH_ID,
            generation=0,
            phase="wave0",
            intents=_intents(7),
            max_concurrency=3,
            clock=lambda: NOW,
        ),
        worker=_worker,
        submit=_submitter(),
    )
    assert result.gate_view.drained
    assert len(result.gate_view.planned_work_ids) == 7
    assert set(result.gate_view.accepted_record_by_work_id) == set(result.gate_view.planned_work_ids)
    assert len(set(result.parent_update["accepted_submission_refs"])) == 7
    assert result.parent_update["pending_work_ids"] == ()


async def test_component_supports_32_work_concurrency_one_under_internal_limit() -> None:
    result = await run_work_unit_component(
        {},
        config=WorkUnitComponentConfig(
            research_id=RESEARCH_ID,
            generation=0,
            phase="wave0",
            intents=_intents(32),
            max_concurrency=1,
            clock=lambda: NOW,
        ),
        worker=_worker,
        submit=_submitter(),
    )
    assert result.gate_view.drained
    assert len(result.parent_update["attempts_by_id"]) == 32


async def test_whole_wave_replay_reconciles_before_worker_dispatch() -> None:
    records: dict[str, SubmissionRecord] = {}
    config = WorkUnitComponentConfig(
        research_id=RESEARCH_ID,
        generation=0,
        phase="wave0",
        intents=_intents(3),
        max_concurrency=3,
        clock=lambda: NOW,
    )
    first = await run_work_unit_component({}, config=config, worker=_worker, submit=_submitter(records))
    worker_calls = 0

    async def should_not_run(spec, attempt):
        nonlocal worker_calls
        worker_calls += 1
        return await _worker(spec, attempt)

    async def reconcile(spec, _attempt):
        return records.get(spec.work_id)

    replay = await run_work_unit_component(
        first.parent_update,
        config=config,
        worker=should_not_run,
        submit=_submitter(records),
        reconcile=reconcile,
    )
    assert worker_calls == 0
    assert replay.gate_view.accepted_record_by_work_id == first.gate_view.accepted_record_by_work_id


async def test_component_allocates_from_checkpoint_ordinal_and_advances_parent_cursor() -> None:
    result = await run_work_unit_component(
        {"next_work_ordinal": 3},
        config=WorkUnitComponentConfig(
            research_id=RESEARCH_ID,
            generation=0,
            phase="wave0",
            intents=_intents(3),
            max_concurrency=3,
            clock=lambda: NOW,
            start_work_ordinal=3,
        ),
        worker=_worker,
        submit=_submitter(),
    )
    assert result.gate_view.planned_work_ids == (
        "g0_wave0_w0003",
        "g0_wave0_w0004",
        "g0_wave0_w0005",
    )
    assert result.parent_update["next_work_ordinal"] == 6


def test_component_rejects_an_ordinal_window_past_the_id_bound() -> None:
    with pytest.raises(ValueError, match="start_work_ordinal_invalid"):
        WorkUnitComponentConfig(
            research_id=RESEARCH_ID,
            generation=0,
            phase="wave0",
            intents=_intents(3),
            max_concurrency=3,
            clock=lambda: NOW,
            start_work_ordinal=9998,
        )


@pytest.mark.parametrize(
    ("terminal_code", "status"),
    [("cancelled", "cancelled"), ("superseded", "cancelled")],
)
async def test_late_terminal_candidate_is_rejected_before_any_store_access(terminal_code, status) -> None:
    spec = materialize_work_spec(
        research_id=RESEARCH_ID,
        generation=0,
        phase="wave0",
        work_ordinal=0,
        intent=_intents(1)[0],
    )
    pending = allocate_attempt(spec, attempt_ordinal=0, created_at=NOW)
    attempt = Attempt.model_validate(
        {
            **pending.model_dump(mode="python"),
            "status": status,
            "terminal_at": NOW,
            "terminal_code": terminal_code,
        }
    )
    candidate = await _worker(spec, attempt)
    store = _NoAccessStore()
    controller = WorkUnitControllerDependencies(store=store, resolver=_UnusedResolver())
    with pytest.raises(ValueError, match="attempt_terminal"):
        await submit_candidate_if_active(
            controller,
            spec=spec,
            attempt=attempt,
            candidate=candidate,
            active_attempt_id=attempt.attempt_id,
            now=NOW,
        )
    assert store.calls == []


async def test_expired_or_inactive_candidate_is_rejected_before_any_store_access() -> None:
    spec = materialize_work_spec(
        research_id=RESEARCH_ID,
        generation=0,
        phase="wave0",
        work_ordinal=0,
        intent=_intents(1)[0],
    )
    attempt = allocate_attempt(
        spec,
        attempt_ordinal=0,
        created_at=NOW,
        expires_at=NOW + timedelta(seconds=1),
    )
    candidate = await _worker(spec, attempt)
    store = _NoAccessStore()
    controller = WorkUnitControllerDependencies(store=store, resolver=_UnusedResolver())
    with pytest.raises(ValueError, match="attempt_expired"):
        await submit_candidate_if_active(
            controller,
            spec=spec,
            attempt=attempt,
            candidate=candidate,
            active_attempt_id=attempt.attempt_id,
            now=attempt.expires_at,
        )
    with pytest.raises(ValueError, match="attempt_not_active"):
        await submit_candidate_if_active(
            controller,
            spec=spec,
            attempt=attempt,
            candidate=candidate,
            active_attempt_id=None,
            now=NOW,
        )
    assert store.calls == []
