"""Runtime-owned atomic submission ledger store.

@impl WOU-004
@impl WOU-006
"""

from __future__ import annotations

import asyncio
import base64
import fcntl
import hashlib
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
    FINAL_CITATION_MAP_FILENAME,
    FINAL_REPORT_FILENAME,
    FINAL_SUBTREE,
    WORK_SUBTREE,
    bundle_ref_to_virtual,
    bundle_root,
    evidence_staging_path,
    final_citation_map_path,
    final_report_path,
    is_evidence_staging_name,
    synthesis_findings_path,
)
from deerflow_deep_research.domain.lifecycle import WorkUnitStorageReason
from deerflow_deep_research.domain.state import ContentRef
from deerflow_deep_research.domain.synthesis import (
    MAX_SYNTHESIS_EVIDENCE_ENTRY_BYTES,
    MAX_SYNTHESIS_EVIDENCE_TOTAL_BYTES,
    SynthesisEvidence,
    SynthesisResult,
)
from deerflow_deep_research.domain.work_units import (
    MAX_RESULT_BYTES,
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
MAX_FINAL_ARTIFACT_BYTES = 2 * 1024 * 1024
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

    async def write_source(self, relative_path: str, content: bytes) -> None:
        """Write a fetched/cached source artifact under the attempt ``cache/`` root.

        Source content is not a declared output; it is containment-checked
        per-attempt content written by the worker (the fetch tool's product, or
        a deterministic representation in tests).
        """
        if not isinstance(content, bytes) or not content:
            raise ValueError("source_content_invalid")
        await self._store._write_attempt_file(
            self._spec,
            self._attempt,
            ("cache", *relative_path.split("/")),
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

    async def write_synthesis(self, result: SynthesisResult) -> None:
        if not isinstance(result, SynthesisResult):
            raise TypeError("synthesis_result_required")
        await asyncio.to_thread(self._write_synthesis_sync, canonical_json_bytes(result))

    async def read_synthesis_evidence(self, accepted_refs: tuple[str, ...]) -> tuple[SynthesisEvidence, ...]:
        records = await self.load_records()
        records_by_hash = {record.record_hash: record for record in records}
        evidence: list[SynthesisEvidence] = []
        remaining_bytes = MAX_SYNTHESIS_EVIDENCE_TOTAL_BYTES
        for index, accepted_ref in enumerate(accepted_refs):
            try:
                record = records_by_hash[accepted_ref]
            except KeyError as exc:
                raise ValueError("synthesis_accepted_record_missing") from exc
            remaining_records = len(accepted_refs) - index
            entry_budget = min(
                MAX_SYNTHESIS_EVIDENCE_ENTRY_BYTES,
                remaining_bytes // remaining_records,
            )
            raw = await self.read_canonical_bytes(record.result_ref, max_bytes=MAX_RESULT_BYTES)
            digest = base64.urlsafe_b64encode(hashlib.sha256(raw).digest()).decode("ascii").rstrip("=")
            if len(raw) != record.result_byte_count or f"h_{digest}" != record.result_hash:
                raise ValueError("synthesis_evidence_integrity_mismatch")
            bounded = raw[:entry_budget]
            content = bounded.decode("utf-8", "ignore")
            evidence.append(
                SynthesisEvidence(
                    submission_ref=record.record_hash,
                    phase=record.phase.value,
                    result_contract=record.result_contract,
                    content=content,
                    truncated=len(bounded) < len(raw),
                )
            )
            remaining_bytes -= len(bounded)
        return tuple(evidence)

    async def publish_final(self, report: bytes, citation_map: bytes) -> tuple[ContentRef, ContentRef]:
        if not isinstance(report, bytes) or not report or len(report) > MAX_FINAL_ARTIFACT_BYTES:
            raise ValueError("final_report_invalid")
        if not isinstance(citation_map, bytes) or not citation_map or len(citation_map) > MAX_FINAL_ARTIFACT_BYTES:
            raise ValueError("final_citation_map_invalid")
        await asyncio.to_thread(self._publish_final_sync, report, citation_map)
        return (
            self._final_content_ref(final_report_path(self.research_id), report, FINAL_REPORT_FILENAME),
            self._final_content_ref(
                final_citation_map_path(self.research_id),
                citation_map,
                FINAL_CITATION_MAP_FILENAME,
            ),
        )

    @staticmethod
    def _final_content_ref(path: str, content: bytes, summary: str) -> ContentRef:
        digest = base64.urlsafe_b64encode(hashlib.sha256(content).digest()).decode("ascii").rstrip("=")
        return ContentRef(
            sandbox_path=path,
            content_hash=f"h_{digest}",
            schema_version=1,
            short_summary=summary,
        )

    @staticmethod
    def _read_named_file(directory_fd: int, name: str, *, max_bytes: int) -> bytes | None:
        try:
            fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory_fd)
        except FileNotFoundError:
            return None
        try:
            _require_secure_regular(fd)
            size = os.fstat(fd).st_size
            if size > max_bytes:
                raise ValueError("final_artifact_oversize")
            chunks: list[bytes] = []
            remaining = size
            while remaining:
                chunk = os.read(fd, min(remaining, 64 * 1024))
                if not chunk:
                    break
                chunks.append(chunk)
                remaining -= len(chunk)
            content = b"".join(chunks)
            if len(content) != size:
                raise ValueError("final_artifact_short_read")
            return content
        finally:
            os.close(fd)

    @staticmethod
    def _write_named_file(directory_fd: int, name: str, content: bytes) -> None:
        fd = os.open(name, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600, dir_fd=directory_fd)
        try:
            _require_secure_regular(fd)
            view = memoryview(content)
            while view:
                written = os.write(fd, view)
                if written <= 0:
                    raise OSError("short final artifact write")
                view = view[written:]
            os.fsync(fd)
        finally:
            os.close(fd)

    def _publish_final_sync(self, report: bytes, citation_map: bytes) -> None:
        try:
            workspace_fd = os.open(self._workspace_host_path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        except OSError as exc:
            raise WorkUnitStoreError(WorkUnitStorageReason.THREAD_MOUNT_UNAVAILABLE) from exc
        opened = [workspace_fd]
        staging_name = f".final.{self._token_factory()}.tmp"
        staging_fd = -1
        try:
            current = workspace_fd
            for part in (_BUNDLE_DIRECTORY, self.research_id):
                current = _open_directory(current, part, create=True)
                opened.append(current)
            research_fd = current
            try:
                final_fd = os.open(
                    FINAL_SUBTREE,
                    os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                    dir_fd=research_fd,
                )
            except FileNotFoundError:
                final_fd = -1
            except OSError as exc:
                raise WorkUnitStoreError(WorkUnitStorageReason.POSIX_PRIMITIVES_UNAVAILABLE) from exc
            if final_fd >= 0:
                try:
                    existing = (
                        self._read_named_file(final_fd, FINAL_REPORT_FILENAME, max_bytes=MAX_FINAL_ARTIFACT_BYTES),
                        self._read_named_file(
                            final_fd,
                            FINAL_CITATION_MAP_FILENAME,
                            max_bytes=MAX_FINAL_ARTIFACT_BYTES,
                        ),
                    )
                finally:
                    os.close(final_fd)
                if existing == (report, citation_map):
                    return
                raise ValueError("final_artifact_write_conflict")

            try:
                os.mkdir(staging_name, 0o700, dir_fd=research_fd)
            except FileExistsError:
                raise ValueError("final_staging_conflict") from None
            staging_fd = os.open(staging_name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=research_fd)
            self._write_named_file(staging_fd, FINAL_REPORT_FILENAME, report)
            self._write_named_file(staging_fd, FINAL_CITATION_MAP_FILENAME, citation_map)
            os.fsync(staging_fd)
            os.rename(staging_name, FINAL_SUBTREE, src_dir_fd=research_fd, dst_dir_fd=research_fd)
            staging_name = ""
            os.fsync(research_fd)
        finally:
            if staging_fd >= 0:
                os.close(staging_fd)
            if staging_name:
                try:
                    staging_fd = os.open(
                        staging_name,
                        os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                        dir_fd=opened[-1],
                    )
                except OSError:
                    staging_fd = -1
                if staging_fd >= 0:
                    for name in (FINAL_REPORT_FILENAME, FINAL_CITATION_MAP_FILENAME):
                        try:
                            os.unlink(name, dir_fd=staging_fd)
                        except OSError:
                            pass
                    os.close(staging_fd)
                    try:
                        os.rmdir(staging_name, dir_fd=opened[-1])
                    except OSError:
                        pass
            for fd in reversed(opened):
                os.close(fd)

    def _write_synthesis_sync(self, content: bytes) -> None:
        try:
            workspace_fd = os.open(self._workspace_host_path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        except OSError as exc:
            raise WorkUnitStoreError(WorkUnitStorageReason.THREAD_MOUNT_UNAVAILABLE) from exc
        opened = [workspace_fd]
        temp_name = ".findings.tmp"
        try:
            current = workspace_fd
            for part in (_BUNDLE_DIRECTORY, self.research_id, "synthesis"):
                current = _open_directory(current, part, create=True)
                opened.append(current)
            try:
                fd = os.open(temp_name, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600, dir_fd=current)
            except FileExistsError:
                os.unlink(temp_name, dir_fd=current)
                fd = os.open(temp_name, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600, dir_fd=current)
            try:
                view = memoryview(content)
                while view:
                    written = os.write(fd, view)
                    if written <= 0:
                        raise OSError("short synthesis write")
                    view = view[written:]
                os.fsync(fd)
            finally:
                os.close(fd)
            final_name = synthesis_findings_path(self.research_id).rsplit("/", 1)[-1]
            os.replace(temp_name, final_name, src_dir_fd=current, dst_dir_fd=current)
            os.fsync(current)
        finally:
            try:
                os.unlink(temp_name, dir_fd=opened[-1])
            except OSError:
                pass
            for fd in reversed(opened):
                os.close(fd)

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
    "MAX_FINAL_ARTIFACT_BYTES",
    "WorkUnitCommitResult",
    "WorkUnitStore",
]
