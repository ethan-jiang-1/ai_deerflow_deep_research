"""Runtime-owned request-bundle profile writer.

@impl HIN-004
@impl REG-010
"""

from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from deerflow_deep_research.domain.bundle import profile_path
from deerflow_deep_research.domain.lifecycle import WorkUnitStorageReason
from deerflow_deep_research.domain.profile import (
    ResearchProfile,
    canonical_profile_bytes,
    compute_profile_content_hash,
)
from deerflow_deep_research.runtime import request_bundle as request_bundle_module
from deerflow_deep_research.runtime.request_bundle import RequestBundleStore
from deerflow_deep_research.runtime.work_unit_storage import WorkUnitStorageCheck, WorkUnitStoreError

RESEARCH_ID = "r_" + "A" * 43
OTHER_RESEARCH_ID = "r_" + "B" * 43


async def _ready(*_args: object, **_kwargs: object) -> WorkUnitStorageCheck:
    return WorkUnitStorageCheck("ready", "local_thread_mount")


def _envelope(workspace: Path) -> SimpleNamespace:
    return SimpleNamespace(workspace_host_path=workspace, parent_sandbox=object(), app_config=object())


async def _store(workspace: Path, **hooks: object) -> RequestBundleStore:
    return await RequestBundleStore.create(
        _envelope(workspace),
        research_id=RESEARCH_ID,
        storage_verifier=_ready,
        **hooks,  # type: ignore[arg-type]
    )


def _profile(**overrides: object) -> ResearchProfile:
    payload: dict[str, object] = {
        "depth": "standard",
        "audience": "practitioner",
        "format": "detailed_report",
        "cost_tolerance": "moderate",
        "time_budget": "standard",
        "must_answer": ("Q1",),
        "scope_boundaries": "Grid scale only.",
        "custom_notes": "Prefer recent sources.",
    }
    payload.update(overrides)
    return ResearchProfile(**payload)


def _profile_file(workspace: Path, research_id: str = RESEARCH_ID) -> Path:
    return workspace / profile_path(research_id).removeprefix("workspace/")


async def test_write_profile_publishes_canonical_json_and_content_ref(tmp_path: Path) -> None:
    store = await _store(tmp_path)
    profile = _profile(depth="deep_dive", audience="domain_expert")
    ref = await store.write_profile(profile)

    path = _profile_file(tmp_path)
    assert path.read_bytes() == canonical_profile_bytes(profile)
    assert path.stat().st_mode & 0o777 == 0o600
    assert ref.sandbox_path == profile_path(RESEARCH_ID)
    assert ref.content_hash == compute_profile_content_hash(profile)
    assert ref.schema_version == 1
    assert "deep_dive" in ref.short_summary
    assert str(tmp_path) not in str(ref)


async def test_write_profile_uses_asyncio_to_thread(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    calls: list[str] = []

    async def fake_to_thread(func, *args, **kwargs):  # type: ignore[no-untyped-def]
        calls.append(func.__name__)
        return func(*args, **kwargs)

    monkeypatch.setattr(request_bundle_module.asyncio, "to_thread", fake_to_thread)
    store = await _store(tmp_path)
    await store.write_profile(_profile())
    assert calls == ["_write_profile_sync"]


async def test_fault_cleans_same_directory_staging(tmp_path: Path) -> None:
    def fault(point: str) -> None:
        if point == "after_staging_fsync":
            raise RuntimeError("boom")

    store = await _store(tmp_path, fault_hook=fault, token_factory=lambda: "a" * 32)
    with pytest.raises(RuntimeError, match="boom"):
        await store.write_profile(_profile())

    request_dir = _profile_file(tmp_path).parent
    assert request_dir.is_dir()
    assert not _profile_file(tmp_path).exists()
    assert not tuple(request_dir.glob(".profile.*.tmp"))


async def test_existing_symlink_or_cross_research_path_fails_without_host_path_leak(tmp_path: Path) -> None:
    profile_file = _profile_file(tmp_path)
    profile_file.parent.mkdir(parents=True)
    outside = tmp_path / "outside-secret"
    outside.write_bytes(b"secret")
    profile_file.symlink_to(outside)
    store = await _store(tmp_path)
    with pytest.raises(WorkUnitStoreError) as excinfo:
        await store.write_profile(_profile())
    assert excinfo.value.reason is WorkUnitStorageReason.POSIX_PRIMITIVES_UNAVAILABLE
    assert str(tmp_path) not in str(excinfo.value)
    assert outside.read_bytes() == b"secret"

    other_file = _profile_file(tmp_path, OTHER_RESEARCH_ID)
    assert not other_file.exists()


async def test_store_create_rejects_unverified_workspace_before_write(tmp_path: Path) -> None:
    async def unavailable(*_args: object, **_kwargs: object) -> WorkUnitStorageCheck:
        return WorkUnitStorageCheck("not_ready", "workspace_alias_mismatch")

    with pytest.raises(WorkUnitStoreError) as excinfo:
        await RequestBundleStore.create(
            _envelope(tmp_path),
            research_id=RESEARCH_ID,
            storage_verifier=unavailable,
        )
    assert excinfo.value.reason is WorkUnitStorageReason.WORKSPACE_ALIAS_MISMATCH
    assert not await request_bundle_module.asyncio.to_thread(os.listdir, tmp_path)


def test_store_rejects_malformed_research_id(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="research_id"):
        RequestBundleStore(workspace_host_path=tmp_path, research_id="../escape")
