"""Runtime work-unit store, replay, and serialization contracts.

@impl WOU-005
@impl WOU-006
"""

from __future__ import annotations

import asyncio
import base64
import fcntl
import hashlib
import os
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from deerflow_deep_research.domain.bundle import evidence_ledger_path, evidence_lock_path
from deerflow_deep_research.domain.lifecycle import WorkUnitStorageReason
from deerflow_deep_research.domain.work_units import (
    Attempt,
    CandidateResult,
    FixtureResultDocument,
    PlannedRead,
    WorkSpec,
    WorkUnitValidationPlan,
    canonical_json_bytes,
    compute_candidate_hash,
    compute_work_spec_hash,
    parse_submission_ledger,
)
from deerflow_deep_research.runtime.work_unit_storage import WorkUnitStorageCheck, WorkUnitStoreError
from deerflow_deep_research.runtime.work_unit_store import (
    CommitDisposition,
    WorkUnitStore,
)

RESEARCH_ID = "r_" + "A" * 43
NOW = datetime(2026, 7, 14, 1, 2, 3, 4, tzinfo=UTC)


def _content_hash(content: bytes) -> str:
    digest = base64.urlsafe_b64encode(hashlib.sha256(content).digest()).decode("ascii").rstrip("=")
    return f"h_{digest}"


def _candidate(work_ordinal: int = 0, attempt_ordinal: int = 0, **overrides: object) -> CandidateResult:
    work_id = f"g0_wave0_w{work_ordinal:04d}"
    attempt_id = f"{work_id}_a{attempt_ordinal:02d}"
    spec_payload: dict[str, object] = {
        "schema_version": 1,
        "research_id": RESEARCH_ID,
        "generation": 0,
        "phase": "wave0",
        "work_id": work_id,
        "work_ordinal": work_ordinal,
        "worker_role": "fixture_worker",
        "scope": (f"topic:{work_ordinal}",),
        "result_contract": "fixture.work-unit",
        "result_schema_version": 1,
        "required_outputs": (),
    }
    root = f"workspace/deep-research/{RESEARCH_ID}/work/{work_id}/{attempt_id}"
    payload: dict[str, object] = {
        "schema_version": 1,
        "research_id": RESEARCH_ID,
        "generation": 0,
        "phase": "wave0",
        "work_id": work_id,
        "attempt_id": attempt_id,
        "worker_role": "fixture_worker",
        "spec_hash": compute_work_spec_hash(spec_payload),
        "result_contract": "fixture.work-unit",
        "result_ref": f"{root}/result.json",
        "result_hash": "h_" + "B" * 43,
        "result_schema_version": 1,
        "result_byte_count": 10,
        "output_refs": (),
        "source_refs": (),
    }
    payload.update(overrides)
    payload["candidate_hash"] = compute_candidate_hash(payload)
    return CandidateResult.model_validate(payload)


def _spec() -> WorkSpec:
    payload = {
        "schema_version": 1,
        "research_id": RESEARCH_ID,
        "generation": 0,
        "phase": "wave0",
        "work_id": "g0_wave0_w0000",
        "work_ordinal": 0,
        "worker_role": "fixture_worker",
        "scope": ("topic:0",),
        "result_contract": "fixture.work-unit",
        "result_schema_version": 1,
        "required_outputs": ("claims.json",),
    }
    payload["spec_hash"] = compute_work_spec_hash(payload)
    return WorkSpec.model_validate(payload)


def _attempt(spec: WorkSpec | None = None, ordinal: int = 0) -> Attempt:
    spec = spec or _spec()
    return Attempt(
        schema_version=1,
        research_id=spec.research_id,
        generation=spec.generation,
        phase=spec.phase,
        work_id=spec.work_id,
        attempt_id=f"{spec.work_id}_a{ordinal:02d}",
        attempt_ordinal=ordinal,
        spec_hash=spec.spec_hash,
        status="pending",
        created_at=NOW,
        started_at=None,
        expires_at=None,
        terminal_at=None,
        terminal_code=None,
    )


async def _ready(*_args, **_kwargs) -> WorkUnitStorageCheck:
    return WorkUnitStorageCheck("ready", "local_thread_mount")


def _envelope(workspace: Path) -> SimpleNamespace:
    return SimpleNamespace(workspace_host_path=workspace, parent_sandbox=object(), app_config=object())


async def _store(workspace: Path, **hooks) -> WorkUnitStore:
    return await WorkUnitStore.create(
        _envelope(workspace),
        research_id=RESEARCH_ID,
        storage_verifier=_ready,
        clock=lambda: NOW,
        **hooks,
    )


async def test_store_derives_only_canonical_research_paths_and_modes(tmp_path: Path) -> None:
    store = await _store(tmp_path)
    committed = await store.commit_candidate(_candidate(), scope=("topic:0",))
    assert committed.disposition is CommitDisposition.APPENDED

    relative_ledger = evidence_ledger_path(RESEARCH_ID).removeprefix("workspace/")
    relative_lock = evidence_lock_path(RESEARCH_ID).removeprefix("workspace/")
    ledger = tmp_path / relative_ledger
    lock = tmp_path / relative_lock
    assert ledger.is_file() and lock.is_file()
    assert ledger.stat().st_mode & 0o777 == 0o600
    assert lock.stat().st_mode & 0o777 == 0o600
    assert parse_submission_ledger(ledger.read_bytes()) == (committed.record,)
    assert "/private/" not in str(committed)


async def test_same_attempt_replays_and_sibling_attempt_cannot_create_second_winner(tmp_path: Path) -> None:
    store = await _store(tmp_path)
    candidate = _candidate()
    first = await store.commit_candidate(candidate, scope=("topic:0",))
    replay = await store.commit_candidate(candidate, scope=("topic:0",))
    sibling = await store.commit_candidate(_candidate(attempt_ordinal=1), scope=("topic:0",))
    assert replay.disposition is CommitDisposition.REPLAYED
    assert sibling.disposition is CommitDisposition.WORK_ALREADY_ACCEPTED
    assert replay.record.record_hash == sibling.record.record_hash == first.record.record_hash
    assert len(await store.load_records()) == 1


async def test_same_attempt_different_candidate_conflicts_without_mutation(tmp_path: Path) -> None:
    store = await _store(tmp_path)
    await store.commit_candidate(_candidate(), scope=("topic:0",))
    with pytest.raises(ValueError, match="candidate_conflict"):
        await store.commit_candidate(_candidate(result_hash="h_" + "C" * 43), scope=("topic:0",))
    assert len(await store.load_records()) == 1


async def test_existing_group_or_world_writable_lock_or_ledger_is_rejected(tmp_path: Path) -> None:
    store = await _store(tmp_path)
    await store.commit_candidate(_candidate(), scope=("topic:0",))
    evidence = tmp_path / "deep-research" / RESEARCH_ID / "evidence"
    for name in (".submissions.lock", "submissions.jsonl"):
        path = evidence / name
        path.chmod(0o644)
        with pytest.raises(WorkUnitStoreError) as excinfo:
            await store.load_records()
        assert excinfo.value.reason is WorkUnitStorageReason.POSIX_PRIMITIVES_UNAVAILABLE
        path.chmod(0o600)


async def test_real_lock_contention_uses_fixed_deadline_and_releases(tmp_path: Path) -> None:
    ticks = iter((0.0, 0.5, 1.0, 1.5, 2.0, 2.1))
    store = await _store(tmp_path, monotonic=lambda: next(ticks), lock_sleep=lambda _seconds: None)
    await store.commit_candidate(_candidate(), scope=("topic:0",))
    lock = tmp_path / "deep-research" / RESEARCH_ID / "evidence" / ".submissions.lock"
    fd = os.open(lock, os.O_RDWR | os.O_NOFOLLOW)
    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    try:
        with pytest.raises(WorkUnitStoreError) as excinfo:
            await store.load_records()
        assert excinfo.value.reason is WorkUnitStorageReason.LOCK_TIMEOUT
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)
    assert len(await (await _store(tmp_path)).load_records()) == 1


async def test_staging_is_same_directory_mode_0600_and_removed_on_fault(tmp_path: Path) -> None:
    seen: list[tuple[str, tuple[str, ...]]] = []

    def fault(point: str, evidence_fd: int) -> None:
        seen.append((point, tuple(os.listdir(evidence_fd))))
        if point == "after_staging_fsync":
            raise RuntimeError("fault")

    store = await _store(tmp_path, fault_hook=fault, token_factory=lambda: "a" * 32)
    with pytest.raises(RuntimeError, match="fault"):
        await store.commit_candidate(_candidate(), scope=("topic:0",))
    evidence = tmp_path / "deep-research" / RESEARCH_ID / "evidence"
    assert any(".submissions." + "a" * 32 + ".tmp" in names for _, names in seen)
    assert not tuple(evidence.glob(".submissions.*.tmp"))
    assert not (evidence / "submissions.jsonl").exists()


@pytest.mark.parametrize(
    ("fault_point", "ledger_committed"),
    [
        ("before_staging_write", False),
        ("after_staging_fsync", False),
        ("after_ledger_replace", True),
        ("after_directory_fsync", True),
    ],
)
async def test_atomic_publication_fault_boundaries_replay_from_last_parent_checkpoint(
    tmp_path: Path,
    fault_point: str,
    ledger_committed: bool,
) -> None:
    def fault(point: str, _evidence_fd: int) -> None:
        if point == fault_point:
            raise RuntimeError(fault_point)

    faulting = await _store(tmp_path, fault_hook=fault, token_factory=lambda: "c" * 32)
    with pytest.raises(RuntimeError, match=fault_point):
        await faulting.commit_candidate(_candidate(), scope=("topic:0",))

    restarted = await _store(tmp_path)
    assert len(await restarted.load_records()) == int(ledger_committed)
    replay = await restarted.commit_candidate(_candidate(), scope=("topic:0",))
    expected = CommitDisposition.REPLAYED if ledger_committed else CommitDisposition.APPENDED
    assert replay.disposition is expected
    assert len(await restarted.load_records()) == 1


async def test_stale_staging_is_non_authoritative_and_symlink_lock_is_rejected(tmp_path: Path) -> None:
    store = await _store(tmp_path)
    await store.commit_candidate(_candidate(), scope=("topic:0",))
    evidence = tmp_path / "deep-research" / RESEARCH_ID / "evidence"
    stale = evidence / (".submissions." + "b" * 32 + ".tmp")
    stale.write_text("not-authority", encoding="utf-8")
    assert len(await store.load_records()) == 1
    assert not stale.exists()

    lock = evidence / ".submissions.lock"
    lock.unlink()
    lock.symlink_to(evidence / "submissions.jsonl")
    with pytest.raises(WorkUnitStoreError) as excinfo:
        await store.load_records()
    assert excinfo.value.reason is WorkUnitStorageReason.POSIX_PRIMITIVES_UNAVAILABLE


async def test_store_factory_rejects_unverified_workspace_without_mutation(tmp_path: Path) -> None:
    async def unavailable(*_args, **_kwargs) -> WorkUnitStorageCheck:
        return WorkUnitStorageCheck("not_ready", "workspace_alias_mismatch")

    with pytest.raises(WorkUnitStoreError) as excinfo:
        await WorkUnitStore.create(
            _envelope(tmp_path),
            research_id=RESEARCH_ID,
            storage_verifier=unavailable,
        )
    assert excinfo.value.reason is WorkUnitStorageReason.WORKSPACE_ALIAS_MISMATCH
    assert not await asyncio.to_thread(os.listdir, tmp_path)


async def test_store_factory_accepts_verified_temp_workspace(tmp_path: Path) -> None:
    async def ready(*_args, **_kwargs) -> WorkUnitStorageCheck:
        return WorkUnitStorageCheck("ready", "local_thread_mount")

    store = await WorkUnitStore.create(
        _envelope(tmp_path),
        research_id=RESEARCH_ID,
        storage_verifier=ready,
    )
    assert store.research_id == RESEARCH_ID
    assert await store.load_records() == ()


async def test_concurrent_same_candidate_observes_one_record(tmp_path: Path) -> None:
    left, right = await asyncio.gather(_store(tmp_path), _store(tmp_path))
    results = await asyncio.gather(
        left.commit_candidate(_candidate(), scope=("topic:0",)),
        right.commit_candidate(_candidate(), scope=("topic:0",)),
    )
    assert {result.disposition for result in results} == {
        CommitDisposition.APPENDED,
        CommitDisposition.REPLAYED,
    }
    assert results[0].record.record_hash == results[1].record.record_hash


async def test_contained_read_plan_returns_bytes_and_virtual_ref_without_host_path(tmp_path: Path) -> None:
    store = await _store(tmp_path)
    ref = f"workspace/deep-research/{RESEARCH_ID}/work/g0_wave0_w0000/g0_wave0_w0000_a00/result.json"
    host = tmp_path / ref.removeprefix("workspace/")
    await asyncio.to_thread(host.parent.mkdir, parents=True)
    await asyncio.to_thread(host.write_bytes, b"result")
    reads = await store.read_validation_plan(WorkUnitValidationPlan((PlannedRead(ref, 64),)))
    assert reads[ref].data == b"result"
    assert reads[ref].contained and reads[ref].stable and reads[ref].regular
    assert store.virtual_ref(ref) == f"/mnt/user-data/{ref}"
    assert str(tmp_path) not in str(reads)


async def test_read_canonical_bytes_uses_the_contained_no_follow_reader(tmp_path: Path) -> None:
    store = await _store(tmp_path)
    ref = f"workspace/deep-research/{RESEARCH_ID}/work/g0_wave0_w0000/g0_wave0_w0000_a00/work-spec.json"
    host = tmp_path / ref.removeprefix("workspace/")
    await asyncio.to_thread(host.parent.mkdir, parents=True)
    await asyncio.to_thread(host.write_bytes, b'{"schema_version":1}')
    assert await store.read_canonical_bytes(ref, max_bytes=64) == b'{"schema_version":1}'
    with pytest.raises(FileNotFoundError, match="artifact_missing"):
        await store.read_canonical_bytes(ref.replace("work-spec.json", "missing.json"), max_bytes=64)


async def test_synthesis_evidence_reads_only_committed_result_with_integrity_check(tmp_path: Path) -> None:
    store = await _store(tmp_path)
    content = b'{"schema_version":1,"sources":[{"title":"accepted evidence"}]}'
    candidate = _candidate(result_hash=_content_hash(content), result_byte_count=len(content))
    result_path = tmp_path / candidate.result_ref.removeprefix("workspace/")
    await asyncio.to_thread(result_path.parent.mkdir, parents=True)
    await asyncio.to_thread(result_path.write_bytes, content)
    committed = await store.commit_candidate(candidate, scope=("topic:0",))

    evidence = await store.read_synthesis_evidence((committed.record.record_hash,))

    assert len(evidence) == 1
    assert evidence[0].submission_ref == committed.record.record_hash
    assert evidence[0].content == content.decode()
    assert evidence[0].truncated is False
    await asyncio.to_thread(result_path.write_bytes, b"tampered")
    with pytest.raises(ValueError, match="synthesis_evidence_integrity_mismatch"):
        await store.read_synthesis_evidence((committed.record.record_hash,))


async def test_contained_read_rejects_symlink_escape_and_oversize(tmp_path: Path) -> None:
    store = await _store(tmp_path)
    root = tmp_path / "deep-research" / RESEARCH_ID / "work"
    await asyncio.to_thread(root.mkdir, parents=True)
    outside = tmp_path / "outside-secret"
    await asyncio.to_thread(outside.write_bytes, b"secret")
    link = root / "escape.json"
    await asyncio.to_thread(link.symlink_to, outside)
    ref = f"workspace/deep-research/{RESEARCH_ID}/work/escape.json"
    escaped = await store.read_validation_plan(WorkUnitValidationPlan((PlannedRead(ref, 64),)))
    assert escaped[ref].data is None and not escaped[ref].contained

    large = root / "large.json"
    await asyncio.to_thread(large.write_bytes, b"x" * 65)
    large_ref = f"workspace/deep-research/{RESEARCH_ID}/work/large.json"
    oversized = await store.read_validation_plan(WorkUnitValidationPlan((PlannedRead(large_ref, 64),)))
    assert oversized[large_ref].data is None


async def test_controller_spec_and_narrowed_fixture_writer_have_disjoint_authority(tmp_path: Path) -> None:
    store = await _store(tmp_path)
    spec, attempt = _spec(), _attempt()
    await store.write_work_spec(spec, attempt)
    await store.write_work_spec(spec, attempt)
    writer = store.attempt_artifact_writer(spec, attempt)
    document = FixtureResultDocument(
        schema_version=1,
        research_id=spec.research_id,
        generation=spec.generation,
        phase=spec.phase,
        work_id=spec.work_id,
        attempt_id=attempt.attempt_id,
        worker_role=spec.worker_role,
        spec_hash=spec.spec_hash,
        result_contract="fixture.work-unit",
        fixture_marker="non_research_fixture",
        output_paths=spec.required_outputs,
        source_ids=(),
    )
    await writer.write_result(document)
    await writer.write_output("claims.json", b'{"claims":[]}')

    root = tmp_path / "deep-research" / RESEARCH_ID / "work" / spec.work_id / attempt.attempt_id
    assert (root / "work-spec.json").read_bytes() == canonical_json_bytes(spec)
    assert (root / "result.json").read_bytes() == canonical_json_bytes(document)
    assert (root / "outputs" / "claims.json").read_bytes() == b'{"claims":[]}'
    assert not {"commit_candidate", "load_records", "write_work_spec"} & set(dir(writer))


async def test_fixture_writer_rejects_undeclared_output_and_identity_mutation(tmp_path: Path) -> None:
    store = await _store(tmp_path)
    spec, attempt = _spec(), _attempt()
    writer = store.attempt_artifact_writer(spec, attempt)
    with pytest.raises(ValueError, match="output_not_declared"):
        await writer.write_output("../escape.json", b"escape")
    wrong = FixtureResultDocument.model_construct(
        schema_version=1,
        research_id=spec.research_id,
        generation=spec.generation,
        phase=spec.phase,
        work_id=spec.work_id,
        attempt_id=f"{spec.work_id}_a01",
        worker_role=spec.worker_role,
        spec_hash=spec.spec_hash,
        result_contract="fixture.work-unit",
        fixture_marker="non_research_fixture",
        output_paths=spec.required_outputs,
        source_ids=(),
    )
    with pytest.raises(ValueError, match="fixture_identity_mismatch"):
        await writer.write_result(wrong)
