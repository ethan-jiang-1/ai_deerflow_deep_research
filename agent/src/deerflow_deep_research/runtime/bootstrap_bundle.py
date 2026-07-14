"""Runtime-owned atomic bootstrap bundle establishment.

@impl BON-001
@impl BON-003

``BootstrapBundleStore`` is the sole writer of the minimal research bundle directory
(``request/`` subtree) and the schema/version marker. It reuses the change-04 shared-workspace
probe (``verify_runtime_work_unit_storage``) so an unsupported provider fails closed with
``work_unit_storage_unavailable`` before any write, and reuses the same POSIX-lock +
same-directory-replace + fsync primitives as ``WorkUnitStore``. Establishment is
idempotent-recoverable: a missing directory, a partial tree, or a stale/existing marker that
does not match is cleaned up and re-established. The store derives the real bundle root from
``TrustedRuntimeEnvelope.workspace_host_path`` and never exposes a real host path to the node.
"""

from __future__ import annotations

import asyncio
import fcntl
import os
import stat
import threading
import time
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from deerflow_deep_research.domain.bootstrap import BootstrapMarker
from deerflow_deep_research.domain.bundle import MARKER_FILENAME, REQUEST_SUBTREE
from deerflow_deep_research.domain.lifecycle import WorkUnitStorageReason
from deerflow_deep_research.runtime.work_unit_storage import (
    WorkUnitStorageCheck,
    WorkUnitStoreError,
    verify_runtime_work_unit_storage,
)

LOCK_TIMEOUT_SECONDS = 2.0
LOCK_RETRY_SECONDS = 0.025
MAX_MARKER_BYTES = 4096
_BUNDLE_DIRECTORY = "deep-research"
_BOOTSTRAP_LOCK = ".bootstrap.lock"
_STAGING_PREFIX = ".marker."
_STAGING_SUFFIX = ".tmp"

StorageVerifier = Callable[..., Awaitable[WorkUnitStorageCheck]]
FaultHook = Callable[[str], None]


def _token() -> str:
    import secrets

    return secrets.token_hex(16)


def _open_directory(parent_fd: int, name: str, *, create: bool) -> int:
    if create:
        try:
            os.mkdir(name, 0o700, dir_fd=parent_fd)
        except FileExistsError:
            pass
    try:
        fd = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent_fd)
    except OSError as exc:
        raise WorkUnitStoreError(WorkUnitStorageReason.POSIX_PRIMITIVES_UNAVAILABLE) from exc
    if not stat.S_ISDIR(os.fstat(fd).st_mode):
        os.close(fd)
        raise WorkUnitStoreError(WorkUnitStorageReason.POSIX_PRIMITIVES_UNAVAILABLE)
    return fd


def _require_secure_regular(fd: int) -> None:
    mode = os.fstat(fd).st_mode
    if not stat.S_ISREG(mode) or mode & 0o077:
        raise WorkUnitStoreError(WorkUnitStorageReason.POSIX_PRIMITIVES_UNAVAILABLE)


def _is_staging_name(name: str) -> bool:
    return name.startswith(_STAGING_PREFIX) and name.endswith(_STAGING_SUFFIX)


class _EstablishCancelled(RuntimeError):
    """Raised by the sync establish worker when its caller was cancelled."""


class BootstrapBundleStore:
    """One verified research-scoped bootstrap bundle authority."""

    def __init__(
        self,
        *,
        workspace_host_path: Path,
        research_id: str,
        monotonic: Callable[[], float] = time.monotonic,
        lock_sleep: Callable[[float], None] = time.sleep,
        token_factory: Callable[[], str] = _token,
        fault_hook: FaultHook | None = None,
    ) -> None:
        self._workspace_host_path = workspace_host_path
        self.research_id = research_id
        self._monotonic = monotonic
        self._lock_sleep = lock_sleep
        self._token_factory = token_factory
        self._fault_hook = fault_hook

    @classmethod
    async def create(
        cls,
        envelope: Any,
        *,
        research_id: str,
        storage_verifier: StorageVerifier = verify_runtime_work_unit_storage,
        provider: Any = None,
        monotonic: Callable[[], float] = time.monotonic,
        lock_sleep: Callable[[float], None] = time.sleep,
        token_factory: Callable[[], str] = _token,
        fault_hook: FaultHook | None = None,
    ) -> BootstrapBundleStore:
        check = await storage_verifier(envelope, research_id=research_id, provider=provider)
        if not check.ready:
            try:
                reason = WorkUnitStorageReason(check.reason)
            except ValueError as exc:
                raise WorkUnitStoreError(WorkUnitStorageReason.PROVIDER_UNRECOGNIZED) from exc
            raise WorkUnitStoreError(reason)
        return cls(
            workspace_host_path=Path(envelope.workspace_host_path),
            research_id=research_id,
            monotonic=monotonic,
            lock_sleep=lock_sleep,
            token_factory=token_factory,
            fault_hook=fault_hook,
        )

    async def establish_bundle(self, marker: BootstrapMarker) -> None:
        if not isinstance(marker, BootstrapMarker):
            raise TypeError("marker_required")
        cancel_requested = threading.Event()
        worker = asyncio.create_task(asyncio.to_thread(self._establish_bundle_sync, marker, cancel_requested))
        try:
            await asyncio.shield(worker)
        except asyncio.CancelledError:
            cancel_requested.set()
            try:
                await asyncio.shield(worker)
            except _EstablishCancelled:
                pass
            raise

    async def read_marker(self) -> BootstrapMarker | None:
        return await asyncio.to_thread(self._read_marker_sync)

    def _fault(self, point: str) -> None:
        if self._fault_hook is not None:
            self._fault_hook(point)

    def _open_request(self) -> tuple[list[int], int]:
        """Open the request subtree (creating it) and return (open_fds, request_fd)."""
        try:
            workspace_fd = os.open(self._workspace_host_path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        except OSError as exc:
            raise WorkUnitStoreError(WorkUnitStorageReason.THREAD_MOUNT_UNAVAILABLE) from exc
        opened = [workspace_fd]
        try:
            current = workspace_fd
            for part in (_BUNDLE_DIRECTORY, self.research_id, REQUEST_SUBTREE):
                current = _open_directory(current, part, create=True)
                opened.append(current)
            return opened, current
        except BaseException:
            for fd in reversed(opened):
                os.close(fd)
            raise

    def _open_lock(self, request_fd: int) -> int:
        try:
            fd = -1
            for _ in range(3):
                try:
                    fd = os.open(
                        _BOOTSTRAP_LOCK,
                        os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW,
                        0o600,
                        dir_fd=request_fd,
                    )
                    break
                except FileNotFoundError:
                    continue
            if fd < 0:
                raise FileNotFoundError("stable lock could not be opened")
            _require_secure_regular(fd)
            return fd
        except WorkUnitStoreError:
            raise
        except OSError as exc:
            raise WorkUnitStoreError(WorkUnitStorageReason.POSIX_PRIMITIVES_UNAVAILABLE) from exc

    def _acquire_lock(self, lock_fd: int, cancel_requested: threading.Event | None = None) -> None:
        deadline: float | None = None
        while True:
            if cancel_requested is not None and cancel_requested.is_set():
                raise _EstablishCancelled
            try:
                fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                return
            except BlockingIOError as exc:
                if deadline is None:
                    deadline = self._monotonic() + LOCK_TIMEOUT_SECONDS
                if self._monotonic() >= deadline:
                    raise WorkUnitStoreError(WorkUnitStorageReason.LOCK_TIMEOUT) from exc
                self._lock_sleep(LOCK_RETRY_SECONDS)

    @staticmethod
    def _clean_staging(request_fd: int) -> None:
        for name in os.listdir(request_fd):
            if _is_staging_name(name):
                try:
                    os.unlink(name, dir_fd=request_fd)
                except OSError as exc:
                    raise WorkUnitStoreError(WorkUnitStorageReason.PROBE_CLEANUP_FAILED) from exc

    @staticmethod
    def _read_marker_bytes(request_fd: int) -> bytes | None:
        try:
            fd = os.open(MARKER_FILENAME, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=request_fd)
        except FileNotFoundError:
            return None
        except OSError as exc:
            raise WorkUnitStoreError(WorkUnitStorageReason.POSIX_PRIMITIVES_UNAVAILABLE) from exc
        try:
            _require_secure_regular(fd)
            size = os.fstat(fd).st_size
            if size > MAX_MARKER_BYTES:
                raise ValueError("marker_oversize")
            chunks: list[bytes] = []
            remaining = size
            while remaining:
                chunk = os.read(fd, min(remaining, 64 * 1024))
                if not chunk:
                    break
                chunks.append(chunk)
                remaining -= len(chunk)
            return b"".join(chunks)
        finally:
            os.close(fd)

    def _establish_bundle_sync(
        self,
        marker: BootstrapMarker,
        cancel_requested: threading.Event | None = None,
    ) -> None:
        opened, request_fd = self._open_request()
        lock_fd = -1
        staging_name: str | None = None
        try:
            lock_fd = self._open_lock(request_fd)
            self._acquire_lock(lock_fd, cancel_requested)
            self._clean_staging(request_fd)

            existing = self._read_marker_bytes(request_fd)
            if existing is not None:
                try:
                    parsed = BootstrapMarker.from_canonical_json(existing)
                except ValueError:
                    parsed = None
                if parsed == marker:
                    return  # idempotent re-establishment of a matching marker
                try:
                    os.unlink(MARKER_FILENAME, dir_fd=request_fd)
                except FileNotFoundError:
                    pass

            if cancel_requested is not None and cancel_requested.is_set():
                raise _EstablishCancelled
            self._fault("before_staging_write")
            staging_name = f"{_STAGING_PREFIX}{self._token_factory()}{_STAGING_SUFFIX}"
            staging_fd = os.open(
                staging_name,
                os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW,
                0o600,
                dir_fd=request_fd,
            )
            try:
                _require_secure_regular(staging_fd)
                view = memoryview(marker.canonical_json())
                while view:
                    written = os.write(staging_fd, view)
                    view = view[written:]
                os.fsync(staging_fd)
            finally:
                os.close(staging_fd)
            self._fault("after_staging_fsync")
            if cancel_requested is not None and cancel_requested.is_set():
                raise _EstablishCancelled
            os.replace(staging_name, MARKER_FILENAME, src_dir_fd=request_fd, dst_dir_fd=request_fd)
            staging_name = None
            self._fault("after_marker_replace")
            os.fsync(request_fd)
        finally:
            if staging_name is not None:
                try:
                    os.unlink(staging_name, dir_fd=request_fd)
                except FileNotFoundError:
                    pass
            if lock_fd >= 0:
                try:
                    fcntl.flock(lock_fd, fcntl.LOCK_UN)
                finally:
                    os.close(lock_fd)
            for fd in reversed(opened):
                os.close(fd)

    def _read_marker_sync(self) -> BootstrapMarker | None:
        try:
            workspace_fd = os.open(self._workspace_host_path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        except OSError:
            return None
        current_fd = workspace_fd
        try:
            for part in (_BUNDLE_DIRECTORY, self.research_id, REQUEST_SUBTREE):
                try:
                    next_fd = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=current_fd)
                except FileNotFoundError:
                    return None
                except OSError as exc:
                    raise WorkUnitStoreError(WorkUnitStorageReason.THREAD_MOUNT_UNAVAILABLE) from exc
                os.close(current_fd)
                current_fd = next_fd
            try:
                data = self._read_marker_bytes(current_fd)
            except ValueError as exc:
                raise WorkUnitStoreError(WorkUnitStorageReason.LEDGER_CORRUPT) from exc
            if data is None:
                return None
            try:
                return BootstrapMarker.from_canonical_json(data)
            except ValueError as exc:
                raise WorkUnitStoreError(WorkUnitStorageReason.LEDGER_CORRUPT) from exc
        finally:
            os.close(current_fd)


__all__ = [
    "BootstrapBundleStore",
    "LOCK_RETRY_SECONDS",
    "LOCK_TIMEOUT_SECONDS",
    "MAX_MARKER_BYTES",
]
