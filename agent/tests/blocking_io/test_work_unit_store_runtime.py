from __future__ import annotations

import asyncio
import fcntl
import os
import threading
import time
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from deerflow_deep_research.domain.work_units import CandidateResult, compute_candidate_hash, compute_work_spec_hash
from deerflow_deep_research.runtime.work_unit_storage import WorkUnitStorageCheck
from deerflow_deep_research.runtime.work_unit_store import CommitDisposition, WorkUnitStore

RESEARCH_ID = "r_" + "A" * 43
NOW = datetime(2026, 7, 14, tzinfo=UTC)


def _candidate() -> CandidateResult:
    work_id = "g0_wave0_w0000"
    attempt_id = f"{work_id}_a00"
    spec = {
        "schema_version": 1,
        "research_id": RESEARCH_ID,
        "generation": 0,
        "phase": "wave0",
        "work_id": work_id,
        "work_ordinal": 0,
        "worker_role": "fixture_worker",
        "scope": ("topic",),
        "result_contract": "fixture.work-unit",
        "result_schema_version": 1,
        "required_outputs": (),
    }
    root = f"workspace/deep-research/{RESEARCH_ID}/work/{work_id}/{attempt_id}"
    payload = {
        "schema_version": 1,
        "research_id": RESEARCH_ID,
        "generation": 0,
        "phase": "wave0",
        "work_id": work_id,
        "attempt_id": attempt_id,
        "worker_role": "fixture_worker",
        "spec_hash": compute_work_spec_hash(spec),
        "result_contract": "fixture.work-unit",
        "result_ref": f"{root}/result.json",
        "result_hash": "h_" + "B" * 43,
        "result_schema_version": 1,
        "result_byte_count": 1,
        "output_refs": (),
        "source_refs": (),
    }
    payload["candidate_hash"] = compute_candidate_hash(payload)
    return CandidateResult.model_validate(payload)


async def _ready(*_args, **_kwargs) -> WorkUnitStorageCheck:
    return WorkUnitStorageCheck("ready", "local_thread_mount")


async def _store(tmp_path: Path, **hooks) -> WorkUnitStore:
    envelope = SimpleNamespace(workspace_host_path=tmp_path, parent_sandbox=object(), app_config=object())
    return await WorkUnitStore.create(
        envelope,
        research_id=RESEARCH_ID,
        storage_verifier=_ready,
        clock=lambda: NOW,
        **hooks,
    )


async def test_commit_filesystem_work_does_not_block_event_loop(tmp_path: Path) -> None:
    def slow_fault(point: str, _fd: int) -> None:
        if point == "after_staging_fsync":
            time.sleep(0.1)

    store = await _store(tmp_path, fault_hook=slow_fault)
    ticks = 0

    async def heartbeat() -> None:
        nonlocal ticks
        for _ in range(10):
            await asyncio.sleep(0.01)
            ticks += 1

    result, _ = await asyncio.gather(
        store.commit_candidate(_candidate(), scope=("topic",)),
        heartbeat(),
    )
    assert result.disposition is CommitDisposition.APPENDED
    assert ticks == 10


async def test_cancellation_after_lock_waits_for_bounded_commit_then_reraises(tmp_path: Path) -> None:
    entered = threading.Event()
    release = threading.Event()

    def block_after_fsync(point: str, _fd: int) -> None:
        if point == "after_staging_fsync":
            entered.set()
            release.wait(timeout=1)

    store = await _store(tmp_path, fault_hook=block_after_fsync)
    task = asyncio.create_task(store.commit_candidate(_candidate(), scope=("topic",)))
    assert await asyncio.to_thread(entered.wait, 1)
    task.cancel()
    await asyncio.sleep(0)
    assert not task.done()
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert len(await store.load_records()) == 1


async def test_cancellation_before_lock_acquisition_stops_retry_and_leaves_ledger_unchanged(tmp_path: Path) -> None:
    store = await _store(tmp_path)
    await store.load_records()
    lock = tmp_path / "deep-research" / RESEARCH_ID / "evidence" / ".submissions.lock"
    fd = os.open(lock, os.O_RDWR | os.O_NOFOLLOW)
    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    try:
        task = asyncio.create_task(store.commit_candidate(_candidate(), scope=("topic",)))
        await asyncio.sleep(0.05)
        task.cancel()
        started = time.monotonic()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert time.monotonic() - started < 0.25
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)
    assert await store.load_records() == ()


async def test_committed_ledger_without_checkpoint_is_replayable(tmp_path: Path) -> None:
    store = await _store(tmp_path)
    first = await store.commit_candidate(_candidate(), scope=("topic",))
    restarted = await _store(tmp_path)
    replay = await restarted.commit_candidate(_candidate(), scope=("topic",))
    assert first.record.record_hash == replay.record.record_hash
    assert replay.disposition is CommitDisposition.REPLAYED
