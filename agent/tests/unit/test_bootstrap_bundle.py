"""Red tests for the runtime-owned bootstrap bundle store.

@impl BON-001
@impl BON-003
"""

from __future__ import annotations

import fcntl
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from deerflow_deep_research.domain.bootstrap import BootstrapMarker
from deerflow_deep_research.domain.lifecycle import WorkUnitStorageReason
from deerflow_deep_research.runtime.bootstrap_bundle import (
    LOCK_TIMEOUT_SECONDS,
    BootstrapBundleStore,
)
from deerflow_deep_research.runtime.work_unit_storage import WorkUnitStorageCheck, WorkUnitStoreError

RESEARCH_ID = "r_" + "A" * 43
_STALE_RID = "r_" + "Z" * 43


def _marker(
    *,
    research_id: str = RESEARCH_ID,
    start_message_id: str = "human-start",
    request_digest: str = "d_" + "B" * 43,
    state_schema_version: int = 2,
) -> BootstrapMarker:
    return BootstrapMarker(
        research_id=research_id,
        start_message_id=start_message_id,
        request_digest=request_digest,
        state_schema_version=state_schema_version,
    )


async def _ready(*_args: object, **_kwargs: object) -> WorkUnitStorageCheck:
    return WorkUnitStorageCheck("ready", "local_thread_mount")


def _not_ready(*_args: object, **_kwargs: object) -> WorkUnitStorageCheck:
    return WorkUnitStorageCheck("not_ready", "aio_provisioner_unmounted")


def _envelope(workspace: Path) -> SimpleNamespace:
    return SimpleNamespace(workspace_host_path=workspace, parent_sandbox=object(), app_config=object())


async def _store(workspace: Path, **hooks: object) -> BootstrapBundleStore:
    return await BootstrapBundleStore.create(
        _envelope(workspace),
        research_id=RESEARCH_ID,
        storage_verifier=_ready,
        **hooks,  # type: ignore[arg-type]
    )


def _marker_file(workspace: Path) -> Path:
    return workspace / "deep-research" / RESEARCH_ID / "request" / "marker.json"


def _write_marker_file(workspace: Path, content: bytes, *, mode: int = 0o600) -> None:
    path = _marker_file(workspace)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    os.chmod(path, mode)


class TestEstablishAndRead:
    async def test_read_before_establish_is_none(self, tmp_path: Path) -> None:
        store = await _store(tmp_path)
        assert await store.read_marker() is None

    async def test_establish_writes_marker_bound_to_identity(self, tmp_path: Path) -> None:
        store = await _store(tmp_path)
        marker = _marker()
        await store.establish_bundle(marker)
        assert _marker_file(tmp_path).read_bytes() == marker.canonical_json()
        assert await store.read_marker() == marker

    async def test_marker_is_mode_0600_regular_under_request(self, tmp_path: Path) -> None:
        store = await _store(tmp_path)
        await store.establish_bundle(_marker())
        path = _marker_file(tmp_path)
        assert path.is_file()
        assert stat_mode(path) & 0o777 == 0o600
        assert not path.is_symlink()

    async def test_establish_rejects_group_or_world_writable_existing_marker(self, tmp_path: Path) -> None:
        _write_marker_file(tmp_path, _marker().canonical_json(), mode=0o644)
        store = await _store(tmp_path)
        with pytest.raises(WorkUnitStoreError) as exc:
            await store.establish_bundle(_marker())
        assert exc.value.reason is WorkUnitStorageReason.POSIX_PRIMITIVES_UNAVAILABLE

    async def test_establish_rejects_symlink_marker(self, tmp_path: Path) -> None:
        path = _marker_file(tmp_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        target = tmp_path / "elsewhere"
        target.write_bytes(b"x")
        os.symlink(target, path)
        store = await _store(tmp_path)
        with pytest.raises(WorkUnitStoreError):
            await store.establish_bundle(_marker())


class TestRecoveryAndIdempotence:
    async def test_partial_directory_with_no_marker_is_completed(self, tmp_path: Path) -> None:
        _marker_file(tmp_path).parent.mkdir(parents=True, exist_ok=True)
        store = await _store(tmp_path)
        await store.establish_bundle(_marker())
        assert await store.read_marker() == _marker()

    async def test_stale_marker_is_replaced(self, tmp_path: Path) -> None:
        _write_marker_file(tmp_path, _marker(research_id=_STALE_RID).canonical_json())
        store = await _store(tmp_path)
        await store.establish_bundle(_marker())
        assert await store.read_marker() == _marker()
        assert _marker_file(tmp_path).read_bytes() == _marker().canonical_json()

    async def test_corrupt_marker_is_replaced(self, tmp_path: Path) -> None:
        _write_marker_file(tmp_path, b"not json")
        store = await _store(tmp_path)
        await store.establish_bundle(_marker())
        assert await store.read_marker() == _marker()

    async def test_matching_marker_re_establishment_is_idempotent(self, tmp_path: Path) -> None:
        store = await _store(tmp_path)
        marker = _marker()
        await store.establish_bundle(marker)
        snapshot = _marker_file(tmp_path).read_bytes()
        await store.establish_bundle(marker)  # second time: no-op
        assert _marker_file(tmp_path).read_bytes() == snapshot
        assert await store.read_marker() == marker

    async def test_stale_staging_is_cleaned_before_write(self, tmp_path: Path) -> None:
        staging = _marker_file(tmp_path).parent / ".marker.deadbeef.tmp"
        staging.parent.mkdir(parents=True, exist_ok=True)
        staging.write_bytes(b"stale")
        store = await _store(tmp_path)
        await store.establish_bundle(_marker())
        assert not staging.exists()
        assert await store.read_marker() == _marker()

    async def test_fault_after_staging_cleans_up_and_leaves_no_marker(self, tmp_path: Path) -> None:
        def fault(_point: str) -> None:
            raise RuntimeError("boom")

        store = await _store(tmp_path, fault_hook=fault, token_factory=lambda: "a" * 32)
        with pytest.raises(RuntimeError):
            await store.establish_bundle(_marker())
        assert not _marker_file(tmp_path).exists()
        # No leftover staging.
        request_dir = _marker_file(tmp_path).parent
        assert not any(name.startswith(".marker.") for name in os.listdir(request_dir))


class TestCreateReadiness:
    async def test_unsupported_provider_fails_closed_before_write(self, tmp_path: Path) -> None:
        async def _verifier(*_a: object, **_k: object) -> WorkUnitStorageCheck:
            return _not_ready()

        with pytest.raises(WorkUnitStoreError) as exc:
            await BootstrapBundleStore.create(
                _envelope(tmp_path),
                research_id=RESEARCH_ID,
                storage_verifier=_verifier,
            )
        assert exc.value.code.value == "work_unit_storage_unavailable"
        assert not (tmp_path / "deep-research").exists()


class TestLockContention:
    async def test_real_lock_contention_releases_within_deadline(self, tmp_path: Path) -> None:
        ticks = iter([0.0, 0.0, 0.0, LOCK_TIMEOUT_SECONDS + 1])
        store_a = await _store(tmp_path)
        store_b = await _store(tmp_path, monotonic=lambda: next(ticks), lock_sleep=lambda _s: None)
        marker = _marker()

        # Hold the bootstrap lock from another store while store_b establishes.
        opened, request_fd = store_a._open_request()
        lock_fd = store_a._open_lock(request_fd)
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            with pytest.raises(WorkUnitStoreError) as exc:
                await store_b.establish_bundle(marker)
            assert exc.value.reason is WorkUnitStorageReason.LOCK_TIMEOUT
        finally:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
            os.close(lock_fd)
            for fd in reversed(opened):
                os.close(fd)

        # After release, establishment succeeds.
        await store_b.establish_bundle(marker)
        assert await store_b.read_marker() == marker


def stat_mode(path: Path) -> int:
    return os.stat(path).st_mode
