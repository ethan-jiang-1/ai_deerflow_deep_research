from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace

import pytest
from deerflow.sandbox.local.local_sandbox import LocalSandbox, PathMapping

from deerflow_deep_research.runtime.work_unit_storage import (
    check_prelaunch_work_unit_storage,
    classify_work_unit_storage,
    probe_posix_primitives,
    verify_runtime_work_unit_storage,
)

RESEARCH_ID = "r_" + "A" * 43


def _config(use: str, *, provisioner_url: str | None = None) -> SimpleNamespace:
    return SimpleNamespace(sandbox=SimpleNamespace(use=use, provisioner_url=provisioner_url))


@pytest.mark.parametrize(
    ("use", "provisioner", "status", "reason"),
    [
        ("deerflow.sandbox.local:LocalSandboxProvider", None, "ready", "local_thread_mount"),
        (
            "deerflow.sandbox.local.local_sandbox_provider:LocalSandboxProvider",
            None,
            "ready",
            "local_thread_mount",
        ),
        ("deerflow.community.aio_sandbox:AioSandboxProvider", None, "ready", "aio_local_thread_mount"),
        (
            "deerflow.community.aio_sandbox.aio_sandbox_provider:AioSandboxProvider",
            "http://provisioner:8002",
            "not_ready",
            "aio_provisioner_unmounted",
        ),
        ("deerflow.community.e2b_sandbox:E2BSandboxProvider", None, "not_ready", "e2b_unmounted"),
        (
            "deerflow.community.e2b_sandbox.e2b_sandbox_provider:E2BSandboxProvider",
            None,
            "not_ready",
            "e2b_unmounted",
        ),
        ("deerflow.community.boxlite:BoxliteProvider", None, "not_ready", "boxlite_unmounted"),
        (
            "deerflow.community.boxlite.provider:BoxliteProvider",
            None,
            "not_ready",
            "boxlite_unmounted",
        ),
        ("custom.local:LocalSandboxProvider", None, "unknown", "provider_unrecognized"),
    ],
)
def test_provider_classifier_is_exact(
    use: str,
    provisioner: str | None,
    status: str,
    reason: str,
) -> None:
    result = classify_work_unit_storage(_config(use, provisioner_url=provisioner))
    assert (result.status, result.reason) == (status, reason)


def test_executable_posix_probe_contends_replaces_syncs_and_cleans(tmp_path: Path) -> None:
    names = (".probe.lock", ".probe.src", ".probe.dst")
    probe_posix_primitives(tmp_path, names)
    assert not any((tmp_path / name).exists() for name in names)


def test_prelaunch_probe_uses_existing_base_and_cleans(tmp_path: Path) -> None:
    result = check_prelaunch_work_unit_storage(
        _config("deerflow.sandbox.local:LocalSandboxProvider"),
        base_dir=tmp_path,
    )
    assert result.ready
    assert not tuple(tmp_path.glob(".deep-research-work-unit-fsprobe-*"))


def test_prelaunch_probe_uses_one_exact_token_family(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import deerflow_deep_research.runtime.work_unit_storage as storage

    token = "a" * 32
    captured: list[tuple[str, str, str]] = []
    monkeypatch.setattr(storage.secrets, "token_hex", lambda _: token)
    monkeypatch.setattr(storage, "probe_posix_primitives", lambda _base, names: captured.append(names))
    result = storage.check_prelaunch_work_unit_storage(
        _config("deerflow.sandbox.local:LocalSandboxProvider"),
        base_dir=tmp_path,
    )
    assert result.ready
    assert captured == [
        (
            f".deep-research-work-unit-fsprobe-{token}.lock",
            f".deep-research-work-unit-fsprobe-{token}.src",
            f".deep-research-work-unit-fsprobe-{token}.dst",
        )
    ]


def test_probe_cleanup_failure_is_distinct(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import deerflow_deep_research.runtime.work_unit_storage as storage

    monkeypatch.setattr(storage, "_unlink_if_present", lambda *_args: (_ for _ in ()).throw(OSError("cleanup")))
    result = storage.check_prelaunch_work_unit_storage(
        _config("deerflow.sandbox.local:LocalSandboxProvider"),
        base_dir=tmp_path,
    )
    assert (result.status, result.reason) == ("not_ready", "probe_cleanup_failed")


class FakeSandbox:
    def __init__(self, workspace: Path) -> None:
        self.id = "sandbox-1"
        self.workspace = workspace
        self.commands: list[str] = []

    def _host_path(self, virtual: str) -> Path:
        prefix = "/mnt/user-data/workspace/"
        assert virtual.startswith(prefix)
        return self.workspace / virtual.removeprefix(prefix)

    def read_file(self, path: str) -> str:
        return self._host_path(path).read_text(encoding="utf-8")

    def write_file(self, path: str, content: str, append: bool = False) -> None:
        host = self._host_path(path)
        host.parent.mkdir(parents=True, exist_ok=True)
        host.write_text(content, encoding="utf-8")

    def execute_command(self, command: str) -> str:
        self.commands.append(command)
        return ""


class FakeProvider:
    uses_thread_data_mounts = True

    def __init__(self, sandbox: FakeSandbox) -> None:
        self.sandbox = sandbox

    def get(self, sandbox_id: str) -> FakeSandbox | None:
        return self.sandbox if sandbox_id == self.sandbox.id else None


@pytest.mark.asyncio
async def test_runtime_verifier_proves_bidirectional_alias_and_provider_identity(tmp_path: Path) -> None:
    sandbox = FakeSandbox(tmp_path)
    provider = FakeProvider(sandbox)
    envelope = SimpleNamespace(
        app_config=_config("deerflow.sandbox.local:LocalSandboxProvider"),
        workspace_host_path=tmp_path,
        parent_sandbox=sandbox,
    )
    result = await verify_runtime_work_unit_storage(envelope, research_id=RESEARCH_ID, provider=provider)
    assert result.ready
    assert sandbox.commands and "/mnt/user-data/workspace/" in sandbox.commands[-1]
    diagnostics = tmp_path / "deep-research" / RESEARCH_ID / "diagnostics"
    assert not tuple(diagnostics.glob(".work-unit-*"))

    resolved = await verify_runtime_work_unit_storage(
        envelope,
        research_id=RESEARCH_ID,
        provider_resolver=lambda: provider,
    )
    assert resolved.ready


@pytest.mark.asyncio
async def test_runtime_verifier_cleanup_is_idempotent_with_real_local_sandbox(tmp_path: Path) -> None:
    sandbox = LocalSandbox(
        "local:test-user:test-thread",
        path_mappings=[PathMapping(container_path="/mnt/user-data/workspace", local_path=str(tmp_path))],
    )
    envelope = SimpleNamespace(
        app_config=_config("deerflow.sandbox.local:LocalSandboxProvider"),
        workspace_host_path=tmp_path,
        parent_sandbox=sandbox,
    )

    result = await verify_runtime_work_unit_storage(
        envelope,
        research_id=RESEARCH_ID,
        provider=FakeProvider(sandbox),
    )

    assert (result.status, result.reason) == ("ready", "local_thread_mount")


@pytest.mark.asyncio
async def test_runtime_verifier_rejects_mount_and_provider_contradictions(tmp_path: Path) -> None:
    sandbox = FakeSandbox(tmp_path)
    envelope = SimpleNamespace(
        app_config=_config("deerflow.sandbox.local:LocalSandboxProvider"),
        workspace_host_path=tmp_path,
        parent_sandbox=sandbox,
    )
    wrong = FakeProvider(FakeSandbox(tmp_path))
    assert (await verify_runtime_work_unit_storage(envelope, research_id=RESEARCH_ID, provider=wrong)).reason == (
        "thread_mount_unavailable"
    )
    wrong.uses_thread_data_mounts = False
    assert (await verify_runtime_work_unit_storage(envelope, research_id=RESEARCH_ID, provider=wrong)).reason == (
        "thread_mount_unavailable"
    )


@pytest.mark.asyncio
async def test_runtime_verifier_uses_to_thread_for_sandbox_io(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import deerflow_deep_research.runtime.work_unit_storage as storage

    sandbox = FakeSandbox(tmp_path)
    envelope = SimpleNamespace(
        app_config=_config("deerflow.sandbox.local:LocalSandboxProvider"),
        workspace_host_path=tmp_path,
        parent_sandbox=sandbox,
    )
    provider = FakeProvider(sandbox)
    original = storage.asyncio.to_thread
    calls: list[str] = []

    async def tracked(func, /, *args, **kwargs):
        calls.append(getattr(func, "__name__", type(func).__name__))
        return await original(func, *args, **kwargs)

    monkeypatch.setattr(storage.asyncio, "to_thread", tracked)
    assert (await verify_runtime_work_unit_storage(envelope, research_id=RESEARCH_ID, provider=provider)).ready
    assert {"read_file", "write_file", "execute_command"} <= set(calls)


@pytest.mark.asyncio
async def test_runtime_alias_mismatch_and_cleanup_failure_have_stable_reasons(tmp_path: Path) -> None:
    class MismatchedSandbox(FakeSandbox):
        reads = 0

        def read_file(self, path: str) -> str:
            self.reads += 1
            if self.reads == 1:
                return "different-base64url-token"
            return super().read_file(path)

    sandbox = MismatchedSandbox(tmp_path)
    envelope = SimpleNamespace(
        app_config=_config("deerflow.sandbox.local:LocalSandboxProvider"),
        workspace_host_path=tmp_path,
        parent_sandbox=sandbox,
    )
    result = await verify_runtime_work_unit_storage(
        envelope,
        research_id=RESEARCH_ID,
        provider=FakeProvider(sandbox),
    )
    assert (result.status, result.reason) == ("not_ready", "workspace_alias_mismatch")

    class CleanupFailSandbox(FakeSandbox):
        def execute_command(self, command: str) -> str:
            raise OSError("/secret/host/path")

    cleanup_sandbox = CleanupFailSandbox(tmp_path)
    cleanup_envelope = SimpleNamespace(
        app_config=_config("deerflow.sandbox.local:LocalSandboxProvider"),
        workspace_host_path=tmp_path,
        parent_sandbox=cleanup_sandbox,
    )
    cleanup = await verify_runtime_work_unit_storage(
        cleanup_envelope,
        research_id=RESEARCH_ID,
        provider=FakeProvider(cleanup_sandbox),
    )
    assert (cleanup.status, cleanup.reason) == ("not_ready", "probe_cleanup_failed")


def test_probe_failure_does_not_leak_host_path(tmp_path: Path) -> None:
    missing = tmp_path / "missing" / "secret-user"
    result = check_prelaunch_work_unit_storage(
        _config("deerflow.sandbox.local:LocalSandboxProvider"),
        base_dir=missing,
    )
    assert (result.status, result.reason) == ("not_ready", "posix_primitives_unavailable")
    assert str(missing) not in result.reason
    assert not os.path.exists(missing)
