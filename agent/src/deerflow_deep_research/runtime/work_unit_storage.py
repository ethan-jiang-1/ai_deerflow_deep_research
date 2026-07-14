"""Shared work-unit storage classification and executable capability probes.

@impl WOU-006
@impl DEC-005
"""

from __future__ import annotations

import asyncio
import fcntl
import os
import secrets
import shlex
import stat
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from deerflow_deep_research.domain.bundle import (
    prelaunch_fs_probe_names,
    runtime_alias_probe_path,
    runtime_fs_probe_paths,
)
from deerflow_deep_research.domain.lifecycle import InfrastructureResultCode, WorkUnitStorageReason
from deerflow_deep_research.domain.work_units import RESEARCH_ID_RE

StorageStatus = Literal["ready", "not_ready", "unknown"]

_LOCAL_PATHS = frozenset(
    {
        "deerflow.sandbox.local:LocalSandboxProvider",
        "deerflow.sandbox.local.local_sandbox_provider:LocalSandboxProvider",
    }
)
_AIO_PATHS = frozenset(
    {
        "deerflow.community.aio_sandbox:AioSandboxProvider",
        "deerflow.community.aio_sandbox.aio_sandbox_provider:AioSandboxProvider",
    }
)
_E2B_PATHS = frozenset(
    {
        "deerflow.community.e2b_sandbox:E2BSandboxProvider",
        "deerflow.community.e2b_sandbox.e2b_sandbox_provider:E2BSandboxProvider",
    }
)
_BOXLITE_PATHS = frozenset(
    {
        "deerflow.community.boxlite:BoxliteProvider",
        "deerflow.community.boxlite.provider:BoxliteProvider",
    }
)


@dataclass(frozen=True)
class WorkUnitStorageCheck:
    status: StorageStatus
    reason: str

    @property
    def ready(self) -> bool:
        return self.status == "ready"


class _ProbeCleanupError(RuntimeError):
    pass


class WorkUnitStoreError(RuntimeError):
    """Closed redacted work-unit infrastructure failure."""

    def __init__(self, reason: WorkUnitStorageReason | str) -> None:
        self.reason = reason if isinstance(reason, WorkUnitStorageReason) else WorkUnitStorageReason(reason)
        self.code = (
            InfrastructureResultCode.WORK_UNIT_STORE_BUSY
            if self.reason is WorkUnitStorageReason.LOCK_TIMEOUT
            else InfrastructureResultCode.WORK_UNIT_STORAGE_UNAVAILABLE
        )
        super().__init__(f"[{self.code.value}] {self.reason.value}")


def _config_value(value: Any, key: str, default: Any = None) -> Any:
    if isinstance(value, dict):
        return value.get(key, default)
    return getattr(value, key, default)


def classify_work_unit_storage(app_config: Any) -> WorkUnitStorageCheck:
    sandbox = _config_value(app_config, "sandbox")
    provider_path = _config_value(sandbox, "use", "")
    if provider_path in _LOCAL_PATHS:
        return WorkUnitStorageCheck("ready", "local_thread_mount")
    if provider_path in _AIO_PATHS:
        if _config_value(sandbox, "provisioner_url"):
            return WorkUnitStorageCheck("not_ready", "aio_provisioner_unmounted")
        return WorkUnitStorageCheck("ready", "aio_local_thread_mount")
    if provider_path in _E2B_PATHS:
        return WorkUnitStorageCheck("not_ready", "e2b_unmounted")
    if provider_path in _BOXLITE_PATHS:
        return WorkUnitStorageCheck("not_ready", "boxlite_unmounted")
    return WorkUnitStorageCheck("unknown", "provider_unrecognized")


def _unlink_if_present(dir_fd: int, name: str) -> None:
    try:
        os.unlink(name, dir_fd=dir_fd)
    except FileNotFoundError:
        return


def probe_posix_primitives(base_dir: Path, names: tuple[str, str, str]) -> None:
    """Execute the exact lock/replace/fsync primitives required by the store."""
    dir_fd = os.open(base_dir, os.O_RDONLY | os.O_DIRECTORY)
    lock_name, src_name, dst_name = names
    lock_fd = second_lock_fd = src_fd = -1
    operation_error: BaseException | None = None
    cleanup_error: BaseException | None = None
    try:
        create_flags = os.O_CREAT | os.O_EXCL | os.O_RDWR | os.O_NOFOLLOW
        lock_fd = os.open(lock_name, create_flags, 0o600, dir_fd=dir_fd)
        second_lock_fd = os.open(lock_name, os.O_RDWR | os.O_NOFOLLOW, dir_fd=dir_fd)
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            fcntl.flock(second_lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            pass
        else:
            raise OSError("flock_contention_not_enforced")

        src_fd = os.open(src_name, create_flags, 0o600, dir_fd=dir_fd)
        os.write(src_fd, b"work-unit-fs-probe")
        os.fsync(src_fd)
        os.close(src_fd)
        src_fd = -1
        os.replace(src_name, dst_name, src_dir_fd=dir_fd, dst_dir_fd=dir_fd)
        verify_fd = os.open(dst_name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=dir_fd)
        try:
            if not stat.S_ISREG(os.fstat(verify_fd).st_mode) or os.read(verify_fd, 64) != b"work-unit-fs-probe":
                raise OSError("replace_verification_failed")
        finally:
            os.close(verify_fd)
        os.fsync(dir_fd)
    except BaseException as exc:
        operation_error = exc
    finally:
        try:
            if src_fd >= 0:
                os.close(src_fd)
            if second_lock_fd >= 0:
                os.close(second_lock_fd)
            if lock_fd >= 0:
                os.close(lock_fd)
            for name in names:
                _unlink_if_present(dir_fd, name)
            os.close(dir_fd)
        except BaseException as exc:
            cleanup_error = exc
    if cleanup_error is not None:
        raise _ProbeCleanupError from cleanup_error
    if operation_error is not None:
        raise operation_error


def check_prelaunch_work_unit_storage(app_config: Any, *, base_dir: Path) -> WorkUnitStorageCheck:
    classification = classify_work_unit_storage(app_config)
    if not classification.ready:
        return classification
    token = secrets.token_hex(16)
    try:
        probe_posix_primitives(base_dir, prelaunch_fs_probe_names(token))
    except _ProbeCleanupError:
        return WorkUnitStorageCheck("not_ready", "probe_cleanup_failed")
    except Exception:
        return WorkUnitStorageCheck("not_ready", "posix_primitives_unavailable")
    return classification


async def _verify_runtime_work_unit_storage(
    envelope: Any,
    *,
    research_id: str,
    provider: Any,
) -> WorkUnitStorageCheck:
    """Verify installed provider identity, workspace aliasing, and POSIX I/O."""
    classification = classify_work_unit_storage(envelope.app_config)
    if not classification.ready:
        return classification
    parent = envelope.parent_sandbox
    if (
        parent is None
        or getattr(provider, "uses_thread_data_mounts", False) is not True
        or provider.get(parent.id) is not parent
    ):
        return WorkUnitStorageCheck("not_ready", "thread_mount_unavailable")
    if not isinstance(research_id, str) or not RESEARCH_ID_RE.fullmatch(research_id):
        return WorkUnitStorageCheck("not_ready", "workspace_alias_mismatch")

    diagnostics = Path(envelope.workspace_host_path) / "deep-research" / research_id / "diagnostics"
    created_dirs = tuple(
        path
        for path in (
            Path(envelope.workspace_host_path) / "deep-research",
            Path(envelope.workspace_host_path) / "deep-research" / research_id,
            diagnostics,
        )
        if not path.exists()
    )
    await asyncio.to_thread(diagnostics.mkdir, parents=True, exist_ok=True)
    alias_token = secrets.token_hex(16)
    alias_ref = runtime_alias_probe_path(research_id, alias_token)
    virtual_alias = f"/mnt/user-data/{alias_ref}"
    host_alias = diagnostics / Path(alias_ref).name
    host_value = secrets.token_urlsafe(24)
    sandbox_value = secrets.token_urlsafe(24)
    cleanup_failed = False
    try:

        def _host_write() -> None:
            fd = os.open(host_alias, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
            try:
                os.write(fd, host_value.encode("ascii"))
                os.fsync(fd)
            finally:
                os.close(fd)

        await asyncio.to_thread(_host_write)
        if await asyncio.to_thread(parent.read_file, virtual_alias) != host_value:
            return WorkUnitStorageCheck("not_ready", "workspace_alias_mismatch")
        await asyncio.to_thread(host_alias.unlink)
        await asyncio.to_thread(parent.write_file, virtual_alias, sandbox_value)

        def _host_read() -> str:
            fd = os.open(host_alias, os.O_RDONLY | os.O_NOFOLLOW)
            try:
                mode = os.fstat(fd).st_mode
                if not stat.S_ISREG(mode):
                    raise OSError("alias_not_regular")
                os.fchmod(fd, 0o600)
                return os.read(fd, 256).decode("ascii")
            finally:
                os.close(fd)

        if await asyncio.to_thread(_host_read) != sandbox_value:
            return WorkUnitStorageCheck("not_ready", "workspace_alias_mismatch")
        await asyncio.to_thread(host_alias.unlink)
        fs_token = secrets.token_hex(16)
        fs_names = tuple(Path(path).name for path in runtime_fs_probe_paths(research_id, fs_token))
        try:
            await asyncio.to_thread(probe_posix_primitives, diagnostics, fs_names)
        except _ProbeCleanupError:
            return WorkUnitStorageCheck("not_ready", "probe_cleanup_failed")
        except Exception:
            return WorkUnitStorageCheck("not_ready", "posix_primitives_unavailable")
        return classification
    finally:
        try:
            await asyncio.to_thread(host_alias.unlink, missing_ok=True)
            virtual_dirs = [
                f"/mnt/user-data/workspace/deep-research/{research_id}/diagnostics",
                f"/mnt/user-data/workspace/deep-research/{research_id}",
                "/mnt/user-data/workspace/deep-research",
            ]
            quoted_dirs = " ".join(shlex.quote(path) for path in virtual_dirs)
            command = f"rm -f -- {shlex.quote(virtual_alias)}; rmdir -- {quoted_dirs} 2>/dev/null || true"
            await asyncio.to_thread(parent.execute_command, command)
            try:
                await asyncio.to_thread(parent.read_file, virtual_alias)
            except Exception:
                pass
            else:
                cleanup_failed = True
            for directory in reversed(created_dirs):
                await asyncio.to_thread(directory.rmdir)
            if await asyncio.to_thread(host_alias.exists):
                cleanup_failed = True
        except Exception:
            cleanup_failed = True
        if cleanup_failed:
            raise _ProbeCleanupError


async def verify_runtime_work_unit_storage(
    envelope: Any,
    *,
    research_id: str,
    provider: Any = None,
    provider_resolver: Callable[[], Any] | None = None,
) -> WorkUnitStorageCheck:
    if provider is None:
        if provider_resolver is None:
            from deerflow.sandbox import get_sandbox_provider

            provider_resolver = get_sandbox_provider
        provider = provider_resolver()
    try:
        return await _verify_runtime_work_unit_storage(
            envelope,
            research_id=research_id,
            provider=provider,
        )
    except _ProbeCleanupError:
        return WorkUnitStorageCheck("not_ready", "probe_cleanup_failed")


__all__ = [
    "StorageStatus",
    "WorkUnitStorageCheck",
    "WorkUnitStoreError",
    "check_prelaunch_work_unit_storage",
    "classify_work_unit_storage",
    "probe_posix_primitives",
    "verify_runtime_work_unit_storage",
]
