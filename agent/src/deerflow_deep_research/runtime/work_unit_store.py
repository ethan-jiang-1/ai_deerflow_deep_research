"""Runtime-owned atomic submission ledger store.

@impl WOU-004
@impl WOU-006
"""

from __future__ import annotations

import asyncio
import fcntl
import os
import stat
import threading
import time
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

from deerflow_deep_research.domain.bundle import (
    BUNDLE_ROOT,
    EVIDENCE_LEDGER,
    EVIDENCE_LOCK,
    EVIDENCE_SUBTREE,
    WORK_SUBTREE,
    bundle_ref_to_virtual,
    bundle_root,
    evidence_staging_path,
    is_evidence_staging_name,
)
from deerflow_deep_research.domain.lifecycle import WorkUnitStorageReason
from deerflow_deep_research.domain.work_units import (
    MAX_SUBMISSION_LEDGER_BYTES,
    VALIDATOR_V1_PASSED_CHECKS,
    ArtifactRead,
    Attempt,
    CandidateResult,
    FixtureResultDocument,
    PlannedRead,
    SubmissionRecord,
    WorkSpec,
    WorkUnitValidationPlan,
    canonical_json_bytes,
    compute_record_hash,
    encode_submission_ledger,
    parse_submission_ledger,
    submission_record_matches_candidate,
)
from deerflow_deep_research.runtime.work_unit_storage import (
    WorkUnitStorageCheck,
    WorkUnitStoreError,
    verify_runtime_work_unit_storage,
)

LOCK_TIMEOUT_SECONDS = 2.0
LOCK_RETRY_SECONDS = 0.025
_BUNDLE_DIRECTORY = BUNDLE_ROOT.rsplit("/", 1)[-1]


class CommitDisposition(StrEnum):
    APPENDED = "appended"
    REPLAYED = "replayed"
    WORK_ALREADY_ACCEPTED = "work_already_accepted"


class _CommitCancelled(RuntimeError):
    pass


@dataclass(frozen=True)
class WorkUnitCommitResult:
    disposition: CommitDisposition
    record: SubmissionRecord


class _AttemptArtifactWriter:
    def __init__(self, store: WorkUnitStore, spec: WorkSpec, attempt: Attempt) -> None:
        self._store = store
        self._spec = spec
        self._attempt = attempt

    async def write_result(self, document: FixtureResultDocument) -> None:
        identity = (
            document.research_id,
            document.generation,
            document.phase,
            document.work_id,
            document.attempt_id,
            document.worker_role,
            document.spec_hash,
            document.output_paths,
            document.source_ids,
        )
        expected = (
            self._spec.research_id,
            self._spec.generation,
            self._spec.phase,
            self._spec.work_id,
            self._attempt.attempt_id,
            self._spec.worker_role,
            self._spec.spec_hash,
            self._spec.required_outputs,
            (),
        )
        if identity != expected:
            raise ValueError("fixture_identity_mismatch")
        await self._store._write_attempt_file(
            self._spec,
            self._attempt,
            ("result.json",),
            canonical_json_bytes(document),
        )

    async def write_output(self, relative_path: str, content: bytes) -> None:
        if relative_path not in self._spec.required_outputs:
            raise ValueError("output_not_declared")
        if not isinstance(content, bytes) or not content:
            raise ValueError("output_content_invalid")
        await self._store._write_attempt_file(
            self._spec,
            self._attempt,
            ("outputs", *relative_path.split("/")),
            content,
        )


StorageVerifier = Callable[..., Awaitable[WorkUnitStorageCheck]]
FaultHook = Callable[[str, int], None]


def _utc_now() -> datetime:
    return datetime.now(UTC)


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


class WorkUnitStore:
    """One verified research-scoped ledger authority."""

    def __init__(
        self,
        *,
        workspace_host_path: Path,
        research_id: str,
        clock: Callable[[], datetime],
        monotonic: Callable[[], float],
        lock_sleep: Callable[[float], None],
        token_factory: Callable[[], str],
        fault_hook: FaultHook | None,
    ) -> None:
        self._workspace_host_path = workspace_host_path
        self.research_id = research_id
        self._clock = clock
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
        clock: Callable[[], datetime] = _utc_now,
        monotonic: Callable[[], float] = time.monotonic,
        lock_sleep: Callable[[float], None] = time.sleep,
        token_factory: Callable[[], str] = _token,
        fault_hook: FaultHook | None = None,
    ) -> WorkUnitStore:
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
            clock=clock,
            monotonic=monotonic,
            lock_sleep=lock_sleep,
            token_factory=token_factory,
            fault_hook=fault_hook,
        )

    async def load_records(self) -> tuple[SubmissionRecord, ...]:
        return await asyncio.to_thread(self._load_records_sync)

    @staticmethod
    def infrastructure_error(reason: WorkUnitStorageReason) -> WorkUnitStoreError:
        return WorkUnitStoreError(reason)

    async def read_canonical_bytes(self, relative_ref: str, *, max_bytes: int) -> bytes:
        read = await asyncio.to_thread(self._read_one_sync, PlannedRead(relative_ref, max_bytes))
        if not read.contained or not read.stable or not read.regular:
            raise ValueError("canonical_read_not_contained")
        if read.data is None:
            raise FileNotFoundError("artifact_missing")
        return read.data

    async def write_work_spec(self, spec: WorkSpec, attempt: Attempt) -> None:
        self._validate_spec_attempt(spec, attempt)
        await self._write_attempt_file(spec, attempt, ("work-spec.json",), canonical_json_bytes(spec))

    def attempt_artifact_writer(self, spec: WorkSpec, attempt: Attempt) -> _AttemptArtifactWriter:
        self._validate_spec_attempt(spec, attempt)
        return _AttemptArtifactWriter(self, spec, attempt)

    def _validate_spec_attempt(self, spec: WorkSpec, attempt: Attempt) -> None:
        if not isinstance(spec, WorkSpec) or not isinstance(attempt, Attempt):
            raise TypeError("validated_spec_attempt_required")
        if (
            spec.research_id != self.research_id
            or attempt.research_id != spec.research_id
            or attempt.generation != spec.generation
            or attempt.phase != spec.phase
            or attempt.work_id != spec.work_id
            or attempt.spec_hash != spec.spec_hash
        ):
            raise ValueError("work_attempt_mismatch")

    async def _write_attempt_file(
        self,
        spec: WorkSpec,
        attempt: Attempt,
        relative_parts: tuple[str, ...],
        content: bytes,
    ) -> None:
        self._validate_spec_attempt(spec, attempt)
        await asyncio.to_thread(
            self._write_attempt_file_sync,
            spec,
            attempt,
            relative_parts,
            content,
        )

    def virtual_ref(self, ref: str) -> str:
        prefix = f"workspace/deep-research/{self.research_id}/"
        if not isinstance(ref, str) or not ref.startswith(prefix):
            raise ValueError("path_not_contained")
        return bundle_ref_to_virtual(ref)

    async def read_validation_plan(self, plan: WorkUnitValidationPlan) -> dict[str, ArtifactRead]:
        if not isinstance(plan, WorkUnitValidationPlan):
            raise TypeError("validation_plan_required")
        return await asyncio.to_thread(self._read_validation_plan_sync, plan)

    async def commit_candidate(
        self,
        candidate: CandidateResult,
        *,
        scope: Sequence[str],
        validator_version: int = 1,
        passed_checks: Sequence[str] = VALIDATOR_V1_PASSED_CHECKS,
    ) -> WorkUnitCommitResult:
        cancel_requested = threading.Event()
        worker = asyncio.create_task(
            asyncio.to_thread(
                self._commit_candidate_sync,
                candidate,
                tuple(scope),
                validator_version,
                tuple(passed_checks),
                cancel_requested,
            )
        )
        try:
            return await asyncio.shield(worker)
        except asyncio.CancelledError:
            cancel_requested.set()
            try:
                await asyncio.shield(worker)
            except _CommitCancelled:
                pass
            raise

    def _open_evidence(self) -> tuple[int, int, int, int]:
        try:
            workspace_fd = os.open(self._workspace_host_path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        except OSError as exc:
            raise WorkUnitStoreError(WorkUnitStorageReason.THREAD_MOUNT_UNAVAILABLE) from exc
        deep_fd = research_fd = evidence_fd = -1
        try:
            deep_fd = _open_directory(workspace_fd, _BUNDLE_DIRECTORY, create=True)
            research_fd = _open_directory(deep_fd, self.research_id, create=True)
            evidence_fd = _open_directory(research_fd, EVIDENCE_SUBTREE, create=True)
            return workspace_fd, deep_fd, research_fd, evidence_fd
        except BaseException:
            for fd in (evidence_fd, research_fd, deep_fd, workspace_fd):
                if fd >= 0:
                    os.close(fd)
            raise

    def _write_attempt_file_sync(
        self,
        spec: WorkSpec,
        attempt: Attempt,
        relative_parts: tuple[str, ...],
        content: bytes,
    ) -> None:
        try:
            workspace_fd = os.open(self._workspace_host_path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        except OSError as exc:
            raise WorkUnitStoreError(WorkUnitStorageReason.THREAD_MOUNT_UNAVAILABLE) from exc
        opened = [workspace_fd]
        try:
            current = workspace_fd
            for part in (
                _BUNDLE_DIRECTORY,
                self.research_id,
                WORK_SUBTREE,
                spec.work_id,
                attempt.attempt_id,
                *relative_parts[:-1],
            ):
                current = _open_directory(current, part, create=True)
                opened.append(current)
            name = relative_parts[-1]
            try:
                fd = os.open(
                    name,
                    os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW,
                    0o600,
                    dir_fd=current,
                )
            except FileExistsError:
                fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=current)
                try:
                    _require_secure_regular(fd)
                    existing = os.read(fd, len(content) + 1)
                finally:
                    os.close(fd)
                if existing != content:
                    raise ValueError("artifact_write_conflict") from None
                return
            try:
                _require_secure_regular(fd)
                view = memoryview(content)
                while view:
                    written = os.write(fd, view)
                    view = view[written:]
                os.fsync(fd)
            finally:
                os.close(fd)
            os.fsync(current)
        finally:
            for fd in reversed(opened):
                os.close(fd)

    def _read_validation_plan_sync(self, plan: WorkUnitValidationPlan) -> dict[str, ArtifactRead]:
        return {request.ref: self._read_one_sync(request) for request in plan.reads}

    def _read_one_sync(self, request: PlannedRead) -> ArtifactRead:
        prefix = f"{bundle_root(self.research_id)}/"
        if (
            not isinstance(request, PlannedRead)
            or not request.ref.startswith(prefix)
            or not 0 < request.max_bytes <= 8 * 1024 * 1024
        ):
            return ArtifactRead(data=None, contained=False, stable=False, regular=False)
        parts = request.ref.split("/")
        if any(part in {"", ".", ".."} for part in parts) or parts[0] != "workspace":
            return ArtifactRead(data=None, contained=False, stable=False, regular=False)
        try:
            current_fd = os.open(self._workspace_host_path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        except OSError:
            return ArtifactRead(data=None, contained=False, stable=False, regular=False)
        try:
            for part in parts[1:-1]:
                try:
                    next_fd = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=current_fd)
                except FileNotFoundError:
                    return ArtifactRead(data=None)
                except OSError:
                    return ArtifactRead(data=None, contained=False, stable=False, regular=False)
                os.close(current_fd)
                current_fd = next_fd
            try:
                file_fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW, dir_fd=current_fd)
            except FileNotFoundError:
                return ArtifactRead(data=None)
            except OSError:
                return ArtifactRead(data=None, contained=False, stable=False, regular=False)
            try:
                before = os.fstat(file_fd)
                if not stat.S_ISREG(before.st_mode):
                    return ArtifactRead(data=None, regular=False)
                if before.st_size > request.max_bytes:
                    return ArtifactRead(data=None)
                chunks: list[bytes] = []
                remaining = before.st_size
                while remaining:
                    chunk = os.read(file_fd, min(remaining, 64 * 1024))
                    if not chunk:
                        break
                    chunks.append(chunk)
                    remaining -= len(chunk)
                after = os.fstat(file_fd)
                stable = (
                    before.st_dev,
                    before.st_ino,
                    before.st_size,
                    before.st_mtime_ns,
                ) == (
                    after.st_dev,
                    after.st_ino,
                    after.st_size,
                    after.st_mtime_ns,
                )
                data = b"".join(chunks)
                if len(data) != before.st_size:
                    stable = False
                return ArtifactRead(data=data, stable=stable)
            finally:
                os.close(file_fd)
        finally:
            os.close(current_fd)

    @staticmethod
    def _close_directories(fds: tuple[int, int, int, int]) -> None:
        for fd in reversed(fds):
            os.close(fd)

    def _open_lock(self, evidence_fd: int) -> int:
        try:
            fd = -1
            for _ in range(3):
                try:
                    fd = os.open(
                        EVIDENCE_LOCK,
                        os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW,
                        0o600,
                        dir_fd=evidence_fd,
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
                raise _CommitCancelled
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
    def _read_ledger(evidence_fd: int) -> bytes:
        try:
            ledger_fd = os.open(EVIDENCE_LEDGER, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=evidence_fd)
        except FileNotFoundError:
            return b""
        except OSError as exc:
            raise WorkUnitStoreError(WorkUnitStorageReason.LEDGER_CORRUPT) from exc
        try:
            _require_secure_regular(ledger_fd)
            size = os.fstat(ledger_fd).st_size
            if size > MAX_SUBMISSION_LEDGER_BYTES:
                raise WorkUnitStoreError(WorkUnitStorageReason.LEDGER_CORRUPT)
            chunks: list[bytes] = []
            remaining = size
            while remaining:
                chunk = os.read(ledger_fd, min(remaining, 64 * 1024))
                if not chunk:
                    break
                chunks.append(chunk)
                remaining -= len(chunk)
            data = b"".join(chunks)
            if len(data) != size:
                raise WorkUnitStoreError(WorkUnitStorageReason.LEDGER_CORRUPT)
            return data
        finally:
            os.close(ledger_fd)

    @staticmethod
    def _parse_ledger(data: bytes) -> tuple[SubmissionRecord, ...]:
        try:
            return parse_submission_ledger(data)
        except ValueError as exc:
            raise WorkUnitStoreError(WorkUnitStorageReason.LEDGER_CORRUPT) from exc

    @staticmethod
    def _clean_staging(evidence_fd: int) -> None:
        for name in os.listdir(evidence_fd):
            if is_evidence_staging_name(name):
                try:
                    os.unlink(name, dir_fd=evidence_fd)
                except OSError as exc:
                    raise WorkUnitStoreError(WorkUnitStorageReason.PROBE_CLEANUP_FAILED) from exc

    def _locked_records(
        self,
        cancel_requested: threading.Event | None = None,
    ) -> tuple[tuple[int, int, int, int], int, tuple[SubmissionRecord, ...]]:
        directories = self._open_evidence()
        evidence_fd = directories[-1]
        lock_fd = self._open_lock(evidence_fd)
        try:
            self._acquire_lock(lock_fd, cancel_requested)
            self._clean_staging(evidence_fd)
            records = self._parse_ledger(self._read_ledger(evidence_fd))
            return directories, lock_fd, records
        except BaseException:
            os.close(lock_fd)
            self._close_directories(directories)
            raise

    @staticmethod
    def _release_locked(directories: tuple[int, int, int, int], lock_fd: int) -> None:
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
        finally:
            os.close(lock_fd)
            WorkUnitStore._close_directories(directories)

    def _load_records_sync(self) -> tuple[SubmissionRecord, ...]:
        directories, lock_fd, records = self._locked_records()
        try:
            return records
        finally:
            self._release_locked(directories, lock_fd)

    def _fault(self, point: str, evidence_fd: int) -> None:
        if self._fault_hook is not None:
            self._fault_hook(point, evidence_fd)

    def _commit_candidate_sync(
        self,
        candidate: CandidateResult,
        scope: tuple[str, ...],
        validator_version: int,
        passed_checks: tuple[str, ...],
        cancel_requested: threading.Event,
    ) -> WorkUnitCommitResult:
        directories, lock_fd, records = self._locked_records(cancel_requested)
        evidence_fd = directories[-1]
        staging_name: str | None = None
        try:
            by_attempt = {record.attempt_id: record for record in records}
            existing_attempt = by_attempt.get(candidate.attempt_id)
            if existing_attempt is not None:
                if not submission_record_matches_candidate(existing_attempt, candidate):
                    raise ValueError("candidate_conflict")
                return WorkUnitCommitResult(CommitDisposition.REPLAYED, existing_attempt)
            by_work = {record.work_id: record for record in records}
            existing_work = by_work.get(candidate.work_id)
            if existing_work is not None:
                return WorkUnitCommitResult(CommitDisposition.WORK_ALREADY_ACCEPTED, existing_work)

            payload = candidate.model_dump(mode="python")
            payload.update(
                {
                    "scope": scope,
                    "validator_version": validator_version,
                    "passed_checks": passed_checks,
                    "submitted_at": self._clock(),
                    "previous_record_hash": records[-1].record_hash if records else None,
                }
            )
            payload["record_hash"] = compute_record_hash(payload)
            record = SubmissionRecord.model_validate(payload)
            replacement = encode_submission_ledger((*records, record))
            staging_name = evidence_staging_path(self.research_id, self._token_factory()).rsplit("/", 1)[-1]
            self._fault("before_staging_write", evidence_fd)
            staging_fd = os.open(
                staging_name,
                os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW,
                0o600,
                dir_fd=evidence_fd,
            )
            try:
                _require_secure_regular(staging_fd)
                view = memoryview(replacement)
                while view:
                    written = os.write(staging_fd, view)
                    view = view[written:]
                os.fsync(staging_fd)
            finally:
                os.close(staging_fd)
            self._fault("after_staging_fsync", evidence_fd)
            os.replace(staging_name, EVIDENCE_LEDGER, src_dir_fd=evidence_fd, dst_dir_fd=evidence_fd)
            staging_name = None
            self._fault("after_ledger_replace", evidence_fd)
            os.fsync(evidence_fd)
            self._fault("after_directory_fsync", evidence_fd)
            return WorkUnitCommitResult(CommitDisposition.APPENDED, record)
        finally:
            if staging_name is not None:
                try:
                    os.unlink(staging_name, dir_fd=evidence_fd)
                except FileNotFoundError:
                    pass
            self._release_locked(directories, lock_fd)


__all__ = [
    "CommitDisposition",
    "LOCK_RETRY_SECONDS",
    "LOCK_TIMEOUT_SECONDS",
    "WorkUnitCommitResult",
    "WorkUnitStore",
]
