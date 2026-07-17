"""Pure work-unit contracts, canonical encodings, and capability protocols.

@impl WOU-001
@impl WOU-003
@impl WOU-004
@impl WOU-005
"""

from __future__ import annotations

import base64
import hashlib
import json
import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated, Any, Literal, Protocol, TypedDict, runtime_checkable
from urllib.parse import urlsplit, urlunsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from deerflow_deep_research.domain.failure_codes import FailureCode, get_classification
from deerflow_deep_research.domain.lifecycle import LogicalPhase, WorkUnitStorageReason

SCHEMA_VERSION = 1

MAX_WORK_SPEC_BYTES = 16 * 1024
MAX_CANDIDATE_BYTES = 48 * 1024
MAX_SUBMISSION_RECORD_BYTES = 64 * 1024
MAX_SUBMISSION_LEDGER_RECORDS = 4096
MAX_SUBMISSION_LEDGER_BYTES = 8 * 1024 * 1024
MAX_RESULT_BYTES = 256 * 1024
MAX_OUTPUT_BYTES = 8 * 1024 * 1024
MAX_SOURCE_BYTES = 8 * 1024 * 1024
MAX_REFERENCED_BYTES = 32 * 1024 * 1024

MAX_SCOPE_ITEMS = 16
MAX_REQUIRED_OUTPUTS = 16
MAX_OUTPUT_REFS = 16
MAX_SOURCE_REFS = 32
MAX_PARENT_WORKS = 32
MAX_PARENT_ATTEMPTS = 64
MAX_PARENT_FAILURES = 32
MAX_PARENT_ACCEPTED_REFS = 64
MAX_CHILD_BATCH = 16
MAX_CHILD_TERMINAL_UPDATES = 64
MAX_SOURCE_TITLE_CHARS = 256
MAX_BASELINE_FACTS = 32
MAX_BASELINE_FACT_CHARS = 512
MAX_SOURCE_LIMITATIONS_CHARS = 2_048

RESEARCH_ID_RE = re.compile(r"^r_[A-Za-z0-9_-]{43}$")
CONTENT_HASH_RE = re.compile(r"^h_[A-Za-z0-9_-]{43}$")
WORK_ID_RE = re.compile(r"^g(?P<generation>[0-2])_(?P<phase>[a-z][a-z0-9_]*)_w(?P<ordinal>[0-9]{4})$")
ATTEMPT_ID_RE = re.compile(
    r"^(?P<work_id>g(?P<generation>[0-2])_(?P<phase>[a-z][a-z0-9_]*)_w(?P<work_ordinal>[0-9]{4}))"
    r"_a(?P<attempt_ordinal>[0-9]{2})$"
)
WORKER_ROLE_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
STABLE_ID_RE = re.compile(r"^[a-z][a-z0-9_.-]{0,63}$")
SOURCE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
VALIDATOR_CHECK_RE = re.compile(r"^[a-z][a-z0-9_.-]{0,63}$")
BUNDLE_REF_RE = re.compile(r"^workspace/deep-research/r_[A-Za-z0-9_-]{43}/.+$")

WORK_SPEC_HASH_DOMAIN = b"deerflow-deep-research:work-spec:v1\0"
CANDIDATE_HASH_DOMAIN = b"deerflow-deep-research:candidate-result:v1\0"
SUBMISSION_RECORD_HASH_DOMAIN = b"deerflow-deep-research:submission-record:v1\0"
FAILURE_DETAIL_HASH_DOMAIN = b"deerflow-deep-research:terminal-failure-detail:v1\0"

VALIDATOR_V1_PASSED_CHECKS = (
    "artifact_hashes",
    "candidate_hash",
    "identity",
    "logical_work_unique",
    "paths",
    "result_contract",
    "source_refs",
    "work_spec",
)
WORK_UNIT_GATE_VIEW_KEY = "__work_unit_gate_view__"


class AttemptStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUBMITTED = "submitted"
    FAILED = "failed"
    TIMED_OUT = "timed_out"
    CANCELLED = "cancelled"


class AttemptTerminalCode(StrEnum):
    ACCEPTED = "accepted"
    WORKER_FAILED = "worker_failed"
    VALIDATION_FAILED = "validation_failed"
    CANDIDATE_CONFLICT = "candidate_conflict"
    DEADLINE_EXCEEDED = "deadline_exceeded"
    EXPIRED = "expired"
    CANCELLED = "cancelled"
    SUPERSEDED = "superseded"


class SubmissionValidationCode(StrEnum):
    IDENTITY_MISMATCH = "identity_mismatch"
    WORK_SPEC_MISSING = "work_spec_missing"
    SPEC_HASH_MISMATCH = "spec_hash_mismatch"
    SCHEMA_VERSION_UNSUPPORTED = "schema_version_unsupported"
    RESULT_CONTRACT_UNSUPPORTED = "result_contract_unsupported"
    INVALID_OUTPUT_SCHEMA = "invalid_output_schema"
    PATH_NOT_CANONICAL = "path_not_canonical"
    PATH_NOT_CONTAINED = "path_not_contained"
    ARTIFACT_MISSING = "artifact_missing"
    ARTIFACT_EMPTY = "artifact_empty"
    CONTENT_HASH_MISMATCH = "content_hash_mismatch"
    SOURCE_REF_INVALID = "source_ref_invalid"
    CANDIDATE_HASH_MISMATCH = "candidate_hash_mismatch"
    CANDIDATE_CONFLICT = "candidate_conflict"


SUBMISSION_VALIDATION_PRECEDENCE = tuple(SubmissionValidationCode)


@dataclass(frozen=True)
class ArtifactRead:
    data: bytes | None
    contained: bool = True
    stable: bool = True
    regular: bool = True


@dataclass(frozen=True)
class PlannedRead:
    ref: str
    max_bytes: int


@dataclass(frozen=True)
class WorkUnitValidationPlan:
    reads: tuple[PlannedRead, ...]


class _FrozenModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


def _require_utc(value: datetime | None, *, field_name: str) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name}_timezone_invalid")
    return value.astimezone(UTC)


def _canonical_value(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return _canonical_value(value.model_dump(mode="python"))
    if isinstance(value, datetime):
        normalized = _require_utc(value, field_name="datetime")
        assert normalized is not None
        return normalized.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, Mapping):
        return {str(key): _canonical_value(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_canonical_value(item) for item in value]
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("canonical_number_invalid")
    return value


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        _canonical_value(value),
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _hash_payload(domain: bytes, payload: Mapping[str, Any]) -> str:
    digest = hashlib.sha256(domain + canonical_json_bytes(payload)).digest()
    return "h_" + base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def _without(payload: Mapping[str, Any], field_name: str) -> dict[str, Any]:
    result = dict(payload)
    result.pop(field_name, None)
    return result


def compute_work_spec_hash(value: WorkSpec | Mapping[str, Any]) -> str:
    payload = value.model_dump(mode="python") if isinstance(value, WorkSpec) else dict(value)
    return _hash_payload(WORK_SPEC_HASH_DOMAIN, _without(payload, "spec_hash"))


_CANDIDATE_HASH_FIELDS = (
    "schema_version",
    "research_id",
    "generation",
    "phase",
    "work_id",
    "attempt_id",
    "worker_role",
    "spec_hash",
    "result_contract",
    "result_ref",
    "result_hash",
    "result_schema_version",
    "result_byte_count",
    "output_refs",
    "source_refs",
)


def compute_candidate_hash(value: CandidateResult | Mapping[str, Any]) -> str:
    raw = value.model_dump(mode="python") if isinstance(value, CandidateResult) else dict(value)
    payload = {field: raw[field] for field in _CANDIDATE_HASH_FIELDS if field in raw}
    return _hash_payload(CANDIDATE_HASH_DOMAIN, payload)


def compute_record_hash(value: SubmissionRecord | Mapping[str, Any]) -> str:
    payload = value.model_dump(mode="python") if isinstance(value, SubmissionRecord) else dict(value)
    return _hash_payload(SUBMISSION_RECORD_HASH_DOMAIN, _without(payload, "record_hash"))


def compute_failure_detail_hash(
    *,
    terminal_code: AttemptTerminalCode | str,
    validation_codes: Sequence[SubmissionValidationCode | str] = (),
) -> str:
    terminal = terminal_code if isinstance(terminal_code, AttemptTerminalCode) else AttemptTerminalCode(terminal_code)
    codes = tuple(
        code if isinstance(code, SubmissionValidationCode) else SubmissionValidationCode(code)
        for code in validation_codes
    )
    if terminal is AttemptTerminalCode.VALIDATION_FAILED:
        if not codes:
            raise ValueError("validation_codes_required")
        if tuple(sorted(codes, key=SUBMISSION_VALIDATION_PRECEDENCE.index)) != codes or len(set(codes)) != len(codes):
            raise ValueError("validation_codes_not_canonical")
    elif codes:
        raise ValueError("validation_codes_forbidden")
    return _hash_payload(
        FAILURE_DETAIL_HASH_DOMAIN,
        {"terminal_code": terminal, "validation_codes": codes},
    )


def _validate_relative_posix_path(path: str, *, field_name: str, max_length: int = 256) -> str:
    if not isinstance(path, str) or not path or len(path) > max_length or not path.isascii():
        raise ValueError(f"{field_name}_invalid")
    if path.startswith("/") or path.endswith("/") or "\\" in path or "\x00" in path:
        raise ValueError(f"{field_name}_invalid")
    parts = path.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise ValueError(f"{field_name}_invalid")
    return path


def _validate_bundle_ref(path: str, *, field_name: str) -> str:
    if not isinstance(path, str) or len(path) > 1024 or not path.isascii() or not BUNDLE_REF_RE.fullmatch(path):
        raise ValueError(f"{field_name}_invalid")
    _validate_relative_posix_path(path, field_name=field_name, max_length=1024)
    return path


def canonicalize_source_url(url: str) -> str:
    if not isinstance(url, str) or not url or len(url) > 2048:
        raise ValueError("canonical_url_invalid")
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError as exc:
        raise ValueError("canonical_url_invalid") from exc
    scheme = parts.scheme.lower()
    if scheme not in {"http", "https"} or not parts.netloc or parts.username is not None or parts.password is not None:
        raise ValueError("canonical_url_invalid")
    host = parts.hostname
    if host is None or not host.isascii():
        raise ValueError("canonical_url_invalid")
    host = host.lower()
    rendered_host = f"[{host}]" if ":" in host else host
    if port is not None and not ((scheme == "http" and port == 80) or (scheme == "https" and port == 443)):
        rendered_host = f"{rendered_host}:{port}"
    path = parts.path or "/"
    if path != "/" and path.endswith("/"):
        path = path[:-1]
    return urlunsplit((scheme, rendered_host, path, parts.query, ""))


def _parse_work_id(work_id: str) -> tuple[int, LogicalPhase, int]:
    match = WORK_ID_RE.fullmatch(work_id) if isinstance(work_id, str) else None
    if match is None:
        raise ValueError("work_id_invalid")
    try:
        phase = LogicalPhase(match.group("phase"))
    except ValueError as exc:
        raise ValueError("work_id_invalid") from exc
    return int(match.group("generation")), phase, int(match.group("ordinal"))


def _parse_attempt_id(attempt_id: str) -> tuple[str, int, LogicalPhase, int, int]:
    match = ATTEMPT_ID_RE.fullmatch(attempt_id) if isinstance(attempt_id, str) else None
    if match is None:
        raise ValueError("attempt_id_invalid")
    try:
        phase = LogicalPhase(match.group("phase"))
    except ValueError as exc:
        raise ValueError("attempt_id_invalid") from exc
    return (
        match.group("work_id"),
        int(match.group("generation")),
        phase,
        int(match.group("work_ordinal")),
        int(match.group("attempt_ordinal")),
    )


class WorkSpec(_FrozenModel):
    schema_version: Literal[1]
    research_id: str = Field(pattern=RESEARCH_ID_RE.pattern)
    generation: int = Field(ge=0, le=2)
    phase: LogicalPhase
    work_id: str
    work_ordinal: int = Field(ge=0, le=9999)
    worker_role: str = Field(pattern=WORKER_ROLE_RE.pattern)
    scope: Annotated[tuple[str, ...], Field(min_length=1, max_length=MAX_SCOPE_ITEMS)]
    result_contract: str = Field(pattern=STABLE_ID_RE.pattern)
    result_schema_version: Literal[1]
    required_outputs: Annotated[tuple[str, ...], Field(max_length=MAX_REQUIRED_OUTPUTS)] = ()
    spec_hash: str = Field(pattern=CONTENT_HASH_RE.pattern)

    @field_validator("scope")
    @classmethod
    def validate_scope(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if any(not isinstance(value, str) or not value or len(value) > 512 for value in values):
            raise ValueError("scope_invalid")
        return values

    @field_validator("required_outputs")
    @classmethod
    def validate_required_outputs(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        canonical = tuple(_validate_relative_posix_path(value, field_name="required_outputs") for value in values)
        if any(value == "outputs" or value.startswith("outputs/") for value in canonical):
            raise ValueError("required_outputs_must_be_relative_to_outputs")
        sorted_values = tuple(sorted(canonical, key=lambda value: value.encode("ascii")))
        if canonical != sorted_values or len(set(canonical)) != len(canonical):
            raise ValueError("required_outputs_not_canonical")
        return canonical

    @model_validator(mode="after")
    def validate_identity_and_hash(self) -> WorkSpec:
        generation, phase, ordinal = _parse_work_id(self.work_id)
        if (generation, phase, ordinal) != (self.generation, self.phase, self.work_ordinal):
            raise ValueError("work_id_identity_mismatch")
        if compute_work_spec_hash(self) != self.spec_hash:
            raise ValueError("spec_hash_mismatch")
        if len(canonical_json_bytes(self)) > MAX_WORK_SPEC_BYTES:
            raise ValueError("work_spec_canonical_size_exceeded")
        return self


class Attempt(_FrozenModel):
    schema_version: Literal[1]
    research_id: str = Field(pattern=RESEARCH_ID_RE.pattern)
    generation: int = Field(ge=0, le=2)
    phase: LogicalPhase
    work_id: str
    attempt_id: str
    attempt_ordinal: int = Field(ge=0, le=99)
    spec_hash: str = Field(pattern=CONTENT_HASH_RE.pattern)
    status: AttemptStatus
    created_at: datetime
    started_at: datetime | None
    expires_at: datetime | None
    terminal_at: datetime | None
    terminal_code: AttemptTerminalCode | None

    @model_validator(mode="after")
    def validate_identity_and_lifecycle(self) -> Attempt:
        work_id, generation, phase, _work_ordinal, attempt_ordinal = _parse_attempt_id(self.attempt_id)
        if work_id != self.work_id or generation != self.generation or phase is not self.phase:
            raise ValueError("attempt_id_identity_mismatch")
        if attempt_ordinal != self.attempt_ordinal:
            raise ValueError("attempt_id_ordinal_mismatch")
        work_generation, work_phase, _ = _parse_work_id(self.work_id)
        if (work_generation, work_phase) != (self.generation, self.phase):
            raise ValueError("work_id_identity_mismatch")

        created = _require_utc(self.created_at, field_name="created_at")
        started = _require_utc(self.started_at, field_name="started_at")
        expires = _require_utc(self.expires_at, field_name="expires_at")
        terminal = _require_utc(self.terminal_at, field_name="terminal_at")
        object.__setattr__(self, "created_at", created)
        object.__setattr__(self, "started_at", started)
        object.__setattr__(self, "expires_at", expires)
        object.__setattr__(self, "terminal_at", terminal)
        assert created is not None
        if expires is not None and expires <= created:
            raise ValueError("expires_at_order_invalid")
        if started is not None and started < created:
            raise ValueError("started_at_order_invalid")
        if terminal is not None and terminal < (started or created):
            raise ValueError("terminal_at_order_invalid")

        terminal_codes = {
            AttemptStatus.SUBMITTED: {AttemptTerminalCode.ACCEPTED},
            AttemptStatus.FAILED: {
                AttemptTerminalCode.WORKER_FAILED,
                AttemptTerminalCode.VALIDATION_FAILED,
                AttemptTerminalCode.CANDIDATE_CONFLICT,
            },
            AttemptStatus.TIMED_OUT: {AttemptTerminalCode.DEADLINE_EXCEEDED, AttemptTerminalCode.EXPIRED},
            AttemptStatus.CANCELLED: {AttemptTerminalCode.CANCELLED, AttemptTerminalCode.SUPERSEDED},
        }
        if self.status is AttemptStatus.PENDING:
            if started is not None or terminal is not None or self.terminal_code is not None:
                raise ValueError("pending_lifecycle_invalid")
        elif self.status is AttemptStatus.RUNNING:
            if started is None or terminal is not None or self.terminal_code is not None:
                raise ValueError("running_lifecycle_invalid")
        else:
            if terminal is None or self.terminal_code not in terminal_codes[self.status]:
                raise ValueError("terminal_code_invalid")
            if self.status is not AttemptStatus.CANCELLED and started is None:
                raise ValueError("terminal_started_at_missing")
            if self.terminal_code is AttemptTerminalCode.EXPIRED and (expires is None or terminal < expires):
                raise ValueError("expired_terminal_invalid")
        return self


class OutputRef(_FrozenModel):
    path: str
    content_hash: str = Field(pattern=CONTENT_HASH_RE.pattern)
    schema_version: Literal[1]
    byte_count: int = Field(ge=1, le=MAX_OUTPUT_BYTES)

    @field_validator("path")
    @classmethod
    def validate_path(cls, value: str) -> str:
        return _validate_bundle_ref(value, field_name="path")


class SourceRef(_FrozenModel):
    source_id: str = Field(pattern=SOURCE_ID_RE.pattern)
    canonical_url: str = Field(min_length=1, max_length=2048)
    content_ref: str
    content_hash: str = Field(pattern=CONTENT_HASH_RE.pattern)
    byte_count: int = Field(ge=1, le=MAX_SOURCE_BYTES)

    @field_validator("canonical_url")
    @classmethod
    def validate_url(cls, value: str) -> str:
        if canonicalize_source_url(value) != value:
            raise ValueError("canonical_url_not_canonical")
        return value

    @field_validator("content_ref")
    @classmethod
    def validate_content_ref(cls, value: str) -> str:
        return _validate_bundle_ref(value, field_name="content_ref")


class CandidateResult(_FrozenModel):
    schema_version: Literal[1]
    research_id: str = Field(pattern=RESEARCH_ID_RE.pattern)
    generation: int = Field(ge=0, le=2)
    phase: LogicalPhase
    work_id: str
    attempt_id: str
    worker_role: str = Field(pattern=WORKER_ROLE_RE.pattern)
    spec_hash: str = Field(pattern=CONTENT_HASH_RE.pattern)
    result_contract: str = Field(pattern=STABLE_ID_RE.pattern)
    result_ref: str
    result_hash: str = Field(pattern=CONTENT_HASH_RE.pattern)
    result_schema_version: Literal[1]
    result_byte_count: int = Field(ge=1, le=MAX_RESULT_BYTES)
    output_refs: Annotated[tuple[OutputRef, ...], Field(max_length=MAX_OUTPUT_REFS)] = ()
    source_refs: Annotated[tuple[SourceRef, ...], Field(max_length=MAX_SOURCE_REFS)] = ()
    candidate_hash: str = Field(pattern=CONTENT_HASH_RE.pattern)

    @field_validator("result_ref")
    @classmethod
    def validate_result_ref(cls, value: str) -> str:
        return _validate_bundle_ref(value, field_name="result_ref")

    @field_validator("output_refs")
    @classmethod
    def validate_output_refs(cls, values: tuple[OutputRef, ...]) -> tuple[OutputRef, ...]:
        paths = tuple(value.path for value in values)
        if paths != tuple(sorted(paths, key=lambda value: value.encode("ascii"))) or len(set(paths)) != len(paths):
            raise ValueError("output_refs_not_canonical")
        return values

    @field_validator("source_refs")
    @classmethod
    def validate_source_refs(cls, values: tuple[SourceRef, ...]) -> tuple[SourceRef, ...]:
        keys = tuple((value.source_id, value.canonical_url) for value in values)
        if keys != tuple(sorted(keys)) or len(set(keys)) != len(keys):
            raise ValueError("source_refs_not_canonical")
        return values

    @model_validator(mode="after")
    def validate_identity_hash_and_bounds(self) -> CandidateResult:
        work_id, generation, phase, _work_ordinal, _attempt_ordinal = _parse_attempt_id(self.attempt_id)
        if work_id != self.work_id or generation != self.generation or phase is not self.phase:
            raise ValueError("attempt_id_identity_mismatch")
        expected_root = f"workspace/deep-research/{self.research_id}/work/{self.work_id}/{self.attempt_id}"
        if self.result_ref != f"{expected_root}/result.json":
            raise ValueError("result_ref_identity_mismatch")
        if any(not output.path.startswith(f"{expected_root}/outputs/") for output in self.output_refs):
            raise ValueError("output_refs_identity_mismatch")
        referenced_bytes = (
            self.result_byte_count
            + sum(output.byte_count for output in self.output_refs)
            + sum(source.byte_count for source in self.source_refs)
        )
        if referenced_bytes > MAX_REFERENCED_BYTES:
            raise ValueError("referenced_bytes_exceeded")
        if compute_candidate_hash(self) != self.candidate_hash:
            raise ValueError("candidate_hash_mismatch")
        if len(canonical_json_bytes(self)) > MAX_CANDIDATE_BYTES:
            raise ValueError("candidate_canonical_size_exceeded")
        return self


class SubmissionRecord(CandidateResult):
    scope: Annotated[tuple[str, ...], Field(min_length=1, max_length=MAX_SCOPE_ITEMS)]
    validator_version: int = Field(ge=1, le=32)
    passed_checks: Annotated[tuple[str, ...], Field(min_length=1, max_length=32)]
    submitted_at: datetime
    previous_record_hash: str | None = Field(default=None, pattern=CONTENT_HASH_RE.pattern)
    record_hash: str = Field(pattern=CONTENT_HASH_RE.pattern)

    @field_validator("scope")
    @classmethod
    def validate_scope(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if any(not isinstance(value, str) or not value or len(value) > 512 for value in values):
            raise ValueError("scope_invalid")
        return values

    @field_validator("passed_checks")
    @classmethod
    def validate_passed_checks(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if any(not VALIDATOR_CHECK_RE.fullmatch(value) for value in values):
            raise ValueError("passed_checks_invalid")
        if values != tuple(sorted(values, key=lambda value: value.encode("ascii"))) or len(set(values)) != len(values):
            raise ValueError("passed_checks_not_canonical")
        return values

    @model_validator(mode="after")
    def validate_record(self) -> SubmissionRecord:
        submitted = _require_utc(self.submitted_at, field_name="submitted_at")
        object.__setattr__(self, "submitted_at", submitted)
        if self.validator_version == 1 and self.passed_checks != VALIDATOR_V1_PASSED_CHECKS:
            raise ValueError("passed_checks_v1_mismatch")
        if compute_record_hash(self) != self.record_hash:
            raise ValueError("record_hash_mismatch")
        if len(canonical_json_bytes(self)) > MAX_SUBMISSION_RECORD_BYTES:
            raise ValueError("submission_record_canonical_size_exceeded")
        return self


def _reject_duplicate_json_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("submission_ledger_duplicate_json_key")
        result[key] = value
    return result


def _validate_submission_records(records: Sequence[SubmissionRecord]) -> tuple[SubmissionRecord, ...]:
    if len(records) > MAX_SUBMISSION_LEDGER_RECORDS:
        raise ValueError("submission_ledger_too_many_records")
    validated: list[SubmissionRecord] = []
    expected_previous: str | None = None
    seen_attempts: set[tuple[str, str]] = set()
    seen_work: set[tuple[str, str]] = set()
    for raw_record in records:
        try:
            payload = raw_record.model_dump(mode="python") if isinstance(raw_record, SubmissionRecord) else raw_record
            record = SubmissionRecord.model_validate(payload)
        except (TypeError, ValueError) as exc:
            raise ValueError("submission_ledger_record_invalid") from exc
        encoded = canonical_json_bytes(record)
        if len(encoded) > MAX_SUBMISSION_RECORD_BYTES:
            raise ValueError("submission_ledger_record_too_large")
        if record.previous_record_hash != expected_previous:
            raise ValueError("submission_ledger_chain_invalid")
        attempt_identity = (record.research_id, record.attempt_id)
        if attempt_identity in seen_attempts:
            raise ValueError("submission_ledger_duplicate_attempt")
        work_identity = (record.research_id, record.work_id)
        if work_identity in seen_work:
            raise ValueError("submission_ledger_duplicate_work")
        seen_attempts.add(attempt_identity)
        seen_work.add(work_identity)
        validated.append(record)
        expected_previous = record.record_hash
    return tuple(validated)


def encode_submission_ledger(records: Sequence[SubmissionRecord]) -> bytes:
    """Encode a fully validated submission chain as canonical LF-only JSONL."""
    validated = _validate_submission_records(records)
    lines: list[bytes] = []
    total_bytes = 0
    for record in validated:
        line = canonical_json_bytes(record) + b"\n"
        total_bytes += len(line)
        if total_bytes > MAX_SUBMISSION_LEDGER_BYTES:
            raise ValueError("submission_ledger_too_large")
        lines.append(line)
    return b"".join(lines)


def parse_submission_ledger(data: bytes) -> tuple[SubmissionRecord, ...]:
    """Parse canonical ledger bytes and verify schema, chain, and uniqueness."""
    if not isinstance(data, bytes):
        raise ValueError("submission_ledger_bytes_required")
    if len(data) > MAX_SUBMISSION_LEDGER_BYTES:
        raise ValueError("submission_ledger_too_large")
    if not data:
        return ()
    if b"\r" in data:
        raise ValueError("submission_ledger_newline_invalid")
    if not data.endswith(b"\n"):
        raise ValueError("submission_ledger_final_lf_missing")
    lines = data[:-1].split(b"\n")
    if len(lines) > MAX_SUBMISSION_LEDGER_RECORDS:
        raise ValueError("submission_ledger_too_many_records")
    if any(not line for line in lines):
        raise ValueError("submission_ledger_blank_line")

    records: list[SubmissionRecord] = []
    for line in lines:
        if len(line) > MAX_SUBMISSION_RECORD_BYTES:
            raise ValueError("submission_ledger_record_too_large")
        try:
            payload = json.loads(line.decode("utf-8"), object_pairs_hook=_reject_duplicate_json_keys)
            if not isinstance(payload, dict):
                raise ValueError("submission_ledger_record_not_object")
            record = SubmissionRecord.model_validate(payload)
        except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
            raise ValueError("submission_ledger_record_invalid") from exc
        if canonical_json_bytes(record) != line:
            raise ValueError("submission_ledger_record_not_canonical")
        records.append(record)
    return _validate_submission_records(records)


def submission_record_matches_candidate(record: SubmissionRecord, candidate: CandidateResult) -> bool:
    """Compare only stable candidate fields, excluding ledger-assigned metadata."""
    if not isinstance(record, SubmissionRecord) or not isinstance(candidate, CandidateResult):
        return False
    record_payload = record.model_dump(mode="python")
    candidate_payload = candidate.model_dump(mode="python")
    return canonical_json_bytes(
        {field: record_payload[field] for field in _CANDIDATE_HASH_FIELDS}
    ) == canonical_json_bytes({field: candidate_payload[field] for field in _CANDIDATE_HASH_FIELDS})


class FixtureResultDocument(_FrozenModel):
    schema_version: Literal[1]
    research_id: str = Field(pattern=RESEARCH_ID_RE.pattern)
    generation: int = Field(ge=0, le=2)
    phase: LogicalPhase
    work_id: str
    attempt_id: str
    worker_role: str = Field(pattern=WORKER_ROLE_RE.pattern)
    spec_hash: str = Field(pattern=CONTENT_HASH_RE.pattern)
    result_contract: Literal["fixture.work-unit"]
    fixture_marker: Literal["non_research_fixture"]
    output_paths: Annotated[tuple[str, ...], Field(max_length=MAX_REQUIRED_OUTPUTS)] = ()
    source_ids: tuple[()] = ()

    @field_validator("output_paths")
    @classmethod
    def validate_output_paths(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        canonical = tuple(_validate_relative_posix_path(value, field_name="output_paths") for value in values)
        sorted_values = tuple(sorted(canonical, key=lambda value: value.encode("ascii")))
        if canonical != sorted_values or len(set(canonical)) != len(canonical):
            raise ValueError("output_paths_not_canonical")
        return canonical

    @model_validator(mode="after")
    def validate_identity(self) -> FixtureResultDocument:
        work_id, generation, phase, _work_ordinal, _attempt_ordinal = _parse_attempt_id(self.attempt_id)
        if work_id != self.work_id or generation != self.generation or phase is not self.phase:
            raise ValueError("attempt_id_identity_mismatch")
        return self


class Wave0SourceMeta(_FrozenModel):
    """One fetched (or degraded) source recorded by a Wave0 source-intake worker."""

    source_id: str = Field(pattern=SOURCE_ID_RE.pattern)
    canonical_url: str = Field(min_length=1, max_length=2048)
    title: str = Field(min_length=1, max_length=MAX_SOURCE_TITLE_CHARS)
    content_ref: str
    fetch_status: Literal["fetched", "degraded"]

    @field_validator("canonical_url")
    @classmethod
    def validate_url(cls, value: str) -> str:
        if canonicalize_source_url(value) != value:
            raise ValueError("canonical_url_not_canonical")
        return value

    @field_validator("content_ref")
    @classmethod
    def validate_content_ref(cls, value: str) -> str:
        return _validate_bundle_ref(value, field_name="content_ref")


class Wave0SourceIntakeResult(_FrozenModel):
    """The real Wave0 source-intake result document (WAN-003)."""

    schema_version: Literal[1]
    research_id: str = Field(pattern=RESEARCH_ID_RE.pattern)
    generation: int = Field(ge=0, le=2)
    phase: LogicalPhase
    work_id: str
    attempt_id: str
    worker_role: str = Field(pattern=WORKER_ROLE_RE.pattern)
    spec_hash: str = Field(pattern=CONTENT_HASH_RE.pattern)
    result_contract: Literal["wave0.source-intake"]
    output_paths: Annotated[tuple[str, ...], Field(max_length=MAX_REQUIRED_OUTPUTS)] = ()
    source_ids: Annotated[tuple[str, ...], Field(max_length=MAX_SOURCE_REFS)] = ()
    sources: Annotated[tuple[Wave0SourceMeta, ...], Field(max_length=MAX_SOURCE_REFS)] = ()
    baseline_facts: Annotated[tuple[str, ...], Field(max_length=MAX_BASELINE_FACTS)] = ()
    limitations: str = Field(default="", max_length=MAX_SOURCE_LIMITATIONS_CHARS)

    @field_validator("baseline_facts")
    @classmethod
    def validate_baseline_facts(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        for item in values:
            if not isinstance(item, str) or not item.strip() or len(item) > MAX_BASELINE_FACT_CHARS:
                raise ValueError("baseline_fact_invalid")
        return values

    @field_validator("output_paths")
    @classmethod
    def validate_output_paths(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        canonical = tuple(_validate_relative_posix_path(value, field_name="output_paths") for value in values)
        sorted_values = tuple(sorted(canonical, key=lambda value: value.encode("ascii")))
        if canonical != sorted_values or len(set(canonical)) != len(canonical):
            raise ValueError("output_paths_not_canonical")
        return canonical

    @model_validator(mode="after")
    def validate_identity(self) -> Wave0SourceIntakeResult:
        work_id, generation, phase, _work_ordinal, _attempt_ordinal = _parse_attempt_id(self.attempt_id)
        if work_id != self.work_id or generation != self.generation or phase is not self.phase:
            raise ValueError("attempt_id_identity_mismatch")
        if tuple(source.source_id for source in self.sources) != self.source_ids:
            raise ValueError("source_ids_mismatch")
        return self


class WorkSpecRef(_FrozenModel):
    worker_role: str = Field(pattern=WORKER_ROLE_RE.pattern)
    spec_hash: str = Field(pattern=CONTENT_HASH_RE.pattern)


class WorkerSource(_FrozenModel):
    """One source a Wave0 worker proposes (metadata only).

    The worker owns the content artifact: it writes the fetched/cached bytes
    under its attempt root and derives ``content_ref``/``content_hash``/
    ``byte_count`` for the ``SourceRef``. The model never carries host paths or
    hashes.
    """

    source_id: str = Field(pattern=SOURCE_ID_RE.pattern)
    canonical_url: str = Field(min_length=1, max_length=2048)
    title: str = Field(min_length=1, max_length=MAX_SOURCE_TITLE_CHARS)
    fetch_status: Literal["fetched", "degraded"]

    @field_validator("canonical_url")
    @classmethod
    def validate_url(cls, value: str) -> str:
        return canonicalize_source_url(value)

    @field_validator("fetch_status", mode="before")
    @classmethod
    def normalize_fetch_status(cls, value: Any) -> str:
        if not isinstance(value, str):
            raise ValueError("fetch_status_invalid")
        normalized = value.strip().lower().replace("-", "_").replace(" ", "_")
        if normalized in {
            "fetched",
            "available",
            "accessible",
            "retrieved",
            "success",
            "successful",
            "successfully_fetched",
            "verified",
            "found",
            "ok",
            "complete",
            "completed",
        }:
            return "fetched"
        if normalized in {
            "degraded",
            "unavailable",
            "unreachable",
            "failed",
            "paywalled",
            "partial",
            "blocked",
            "timeout",
            "error",
            "not_found",
        }:
            return "degraded"
        negative_markers = (
            "degrad",
            "unavail",
            "unreach",
            "fail",
            "paywall",
            "partial",
            "block",
            "timeout",
            "error",
            "not_",
            "unverified",
            "denied",
        )
        if any(marker in normalized for marker in negative_markers):
            return "degraded"
        positive_markers = (
            "fetch",
            "avail",
            "access",
            "retriev",
            "success",
            "verif",
            "found",
            "complete",
            "search",
            "indexed",
            "live",
        )
        if any(marker in normalized for marker in positive_markers):
            return "fetched"
        raise ValueError("fetch_status_invalid")


WAVE0_WORKER_OUTPUT_SCHEMA_VERSION = 1


class Wave0WorkerOutput(_FrozenModel):
    """The bounded structured output a Wave0 worker returns from ``run_agent``."""

    schema_version: Literal[1] = WAVE0_WORKER_OUTPUT_SCHEMA_VERSION
    sources: Annotated[tuple[WorkerSource, ...], Field(min_length=1, max_length=MAX_SOURCE_REFS)]
    baseline_facts: Annotated[tuple[str, ...], Field(default=(), max_length=MAX_BASELINE_FACTS)] = ()
    limitations: str = Field(default="", max_length=MAX_SOURCE_LIMITATIONS_CHARS)

    @field_validator("limitations", mode="before")
    @classmethod
    def normalize_limitations(cls, value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, str):
            return value
        if isinstance(value, (tuple, list)) and all(isinstance(item, str) for item in value):
            return "; ".join(item.strip() for item in value if item.strip())
        raise ValueError("limitations_invalid")

    @field_validator("baseline_facts")
    @classmethod
    def validate_baseline_facts(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        for item in values:
            if not isinstance(item, str) or not item.strip() or len(item) > MAX_BASELINE_FACT_CHARS:
                raise ValueError("baseline_fact_invalid")
        return values

    @model_validator(mode="after")
    def validate_independent_sources(self) -> Wave0WorkerOutput:
        urls = [source.canonical_url for source in self.sources]
        if len(set(urls)) != len(urls):
            raise ValueError("sources_not_independent")
        return self


class AttemptRef(_FrozenModel):
    created_at: datetime
    started_at: datetime | None = None
    expires_at: datetime | None = None
    terminal_at: datetime | None = None
    terminal_code: AttemptTerminalCode | None = None

    @model_validator(mode="after")
    def validate_lifecycle(self) -> AttemptRef:
        created = _require_utc(self.created_at, field_name="created_at")
        started = _require_utc(self.started_at, field_name="started_at")
        expires = _require_utc(self.expires_at, field_name="expires_at")
        terminal = _require_utc(self.terminal_at, field_name="terminal_at")
        object.__setattr__(self, "created_at", created)
        object.__setattr__(self, "started_at", started)
        object.__setattr__(self, "expires_at", expires)
        object.__setattr__(self, "terminal_at", terminal)
        assert created is not None
        if expires is not None and expires <= created:
            raise ValueError("expires_at_order_invalid")
        if started is not None and started < created:
            raise ValueError("started_at_order_invalid")
        if terminal is not None and terminal < (started or created):
            raise ValueError("terminal_at_order_invalid")
        if (terminal is None) != (self.terminal_code is None):
            raise ValueError("terminal_detail_incomplete")
        invalid_expiry = expires is None or terminal is None or terminal < expires
        if self.terminal_code is AttemptTerminalCode.EXPIRED and invalid_expiry:
            raise ValueError("expired_terminal_invalid")
        return self


class TerminalFailureSummary(_FrozenModel):
    failure_code: FailureCode
    detail_hash: str = Field(pattern=CONTENT_HASH_RE.pattern)


class WorkUnitGateFailure(_FrozenModel):
    work_id: str
    attempt_id: str
    failure_code: FailureCode
    classification: Literal["hard", "semantic", "degradable", "repairable"]
    detail_hash: str = Field(pattern=CONTENT_HASH_RE.pattern)

    @model_validator(mode="after")
    def validate_identity(self) -> WorkUnitGateFailure:
        match = ATTEMPT_ID_RE.fullmatch(self.attempt_id)
        if match is None or match.group("work_id") != self.work_id:
            raise ValueError("gate_failure_identity_invalid")
        if get_classification(self.failure_code) != self.classification:
            raise ValueError("gate_failure_classification_invalid")
        return self


class WorkUnitGateView(_FrozenModel):
    drained: bool
    planned_work_ids: Annotated[tuple[str, ...], Field(max_length=MAX_PARENT_WORKS)]
    terminal_attempt_by_work_id: dict[str, str] = Field(default_factory=dict, max_length=MAX_PARENT_WORKS)
    accepted_record_by_work_id: dict[str, str] = Field(default_factory=dict, max_length=MAX_PARENT_WORKS)
    failure_summaries: Annotated[tuple[WorkUnitGateFailure, ...], Field(max_length=MAX_PARENT_FAILURES)] = ()

    @model_validator(mode="after")
    def validate_shape(self) -> WorkUnitGateView:
        if self.planned_work_ids != tuple(sorted(self.planned_work_ids)) or len(set(self.planned_work_ids)) != len(
            self.planned_work_ids
        ):
            raise ValueError("planned_work_ids_not_canonical")
        if any(not WORK_ID_RE.fullmatch(work_id) for work_id in self.planned_work_ids):
            raise ValueError("planned_work_id_invalid")
        if set(self.terminal_attempt_by_work_id) - set(self.planned_work_ids):
            raise ValueError("terminal_work_not_planned")
        if set(self.accepted_record_by_work_id) - set(self.planned_work_ids):
            raise ValueError("accepted_work_not_planned")
        if any(not CONTENT_HASH_RE.fullmatch(value) for value in self.accepted_record_by_work_id.values()):
            raise ValueError("accepted_record_hash_invalid")
        failure_works = tuple(failure.work_id for failure in self.failure_summaries)
        if failure_works != tuple(sorted(failure_works)) or len(set(failure_works)) != len(failure_works):
            raise ValueError("failure_summaries_not_canonical")
        return self


def _gate_inconsistent() -> None:
    raise ValueError("work_unit_gate_view_inconsistent")


def validate_wrapper_gate_view(view: WorkUnitGateView, state: Mapping[str, Any], *, phase: str) -> None:
    if not isinstance(view, WorkUnitGateView):
        _gate_inconsistent()
    specs = state.get("work_specs_by_id", {})
    attempts = state.get("attempts_by_id", {})
    statuses = state.get("work_status_by_id", {})
    failures = state.get("terminal_failures_by_attempt_id", {})
    accepted_refs = set(state.get("accepted_submission_refs", ()))
    if view.drained and set(view.terminal_attempt_by_work_id) != set(view.planned_work_ids):
        _gate_inconsistent()
    for work_id in view.planned_work_ids:
        match = WORK_ID_RE.fullmatch(work_id)
        if match is None or match.group("phase") != phase or work_id not in specs:
            _gate_inconsistent()
        attempt_id = view.terminal_attempt_by_work_id.get(work_id)
        if attempt_id is None or attempt_id not in attempts or not attempt_id.startswith(f"{work_id}_a"):
            _gate_inconsistent()
        try:
            status = AttemptStatus(statuses[attempt_id])
        except (KeyError, ValueError):
            _gate_inconsistent()
        accepted_hash = view.accepted_record_by_work_id.get(work_id)
        if accepted_hash is not None:
            if status is not AttemptStatus.SUBMITTED or accepted_hash not in accepted_refs:
                _gate_inconsistent()
        elif status is AttemptStatus.SUBMITTED:
            _gate_inconsistent()
    for failure in view.failure_summaries:
        selected = view.terminal_attempt_by_work_id.get(failure.work_id)
        checkpoint_failure = failures.get(failure.attempt_id)
        if (
            selected != failure.attempt_id
            or checkpoint_failure is None
            or checkpoint_failure.get("failure_code") != failure.failure_code.value
            or checkpoint_failure.get("detail_hash") != failure.detail_hash
        ):
            _gate_inconsistent()


def validate_component_gate_view(
    view: WorkUnitGateView,
    *,
    planned_work_ids: tuple[str, ...],
    records_by_work_id: Mapping[str, SubmissionRecord],
    parent_projection: Mapping[str, Any],
) -> None:
    if view.planned_work_ids != planned_work_ids:
        _gate_inconsistent()
    for work_id, record_hash in view.accepted_record_by_work_id.items():
        record = records_by_work_id.get(work_id)
        if (
            record is None
            or record.work_id != work_id
            or record.record_hash != record_hash
            or view.terminal_attempt_by_work_id.get(work_id) != record.attempt_id
        ):
            _gate_inconsistent()
    phase_match = WORK_ID_RE.fullmatch(planned_work_ids[0]) if planned_work_ids else None
    phase = phase_match.group("phase") if phase_match is not None else "wave0"
    validate_wrapper_gate_view(view, parent_projection, phase=phase)


class AttemptTerminalUpdate(_FrozenModel):
    attempt_id: str
    status: AttemptStatus
    terminal_at: datetime
    terminal_code: AttemptTerminalCode
    validation_codes: tuple[SubmissionValidationCode, ...] = ()

    @model_validator(mode="after")
    def validate_terminal_update(self) -> AttemptTerminalUpdate:
        _parse_attempt_id(self.attempt_id)
        terminal = _require_utc(self.terminal_at, field_name="terminal_at")
        object.__setattr__(self, "terminal_at", terminal)
        status_codes = {
            AttemptStatus.SUBMITTED: {AttemptTerminalCode.ACCEPTED},
            AttemptStatus.FAILED: {
                AttemptTerminalCode.WORKER_FAILED,
                AttemptTerminalCode.VALIDATION_FAILED,
                AttemptTerminalCode.CANDIDATE_CONFLICT,
            },
            AttemptStatus.TIMED_OUT: {AttemptTerminalCode.DEADLINE_EXCEEDED, AttemptTerminalCode.EXPIRED},
            AttemptStatus.CANCELLED: {AttemptTerminalCode.CANCELLED, AttemptTerminalCode.SUPERSEDED},
        }
        if self.status not in status_codes or self.terminal_code not in status_codes[self.status]:
            raise ValueError("terminal_status_code_invalid")
        if self.terminal_code is AttemptTerminalCode.VALIDATION_FAILED:
            if not self.validation_codes:
                raise ValueError("validation_codes_required")
            ordered = tuple(sorted(self.validation_codes, key=SUBMISSION_VALIDATION_PRECEDENCE.index))
            if ordered != self.validation_codes or len(set(self.validation_codes)) != len(self.validation_codes):
                raise ValueError("validation_codes_not_canonical")
        elif self.validation_codes:
            raise ValueError("validation_codes_forbidden")
        return self


def _merge_keyed(
    current: Mapping[str, Any],
    incoming: Mapping[str, Any],
    *,
    label: str,
    max_items: int,
) -> dict[str, Any]:
    merged = dict(current)
    for key, value in incoming.items():
        existing = merged.get(key)
        if existing is not None and existing != value:
            raise ValueError(f"{label}_conflict:{key}")
        merged[key] = value
    if len(merged) > max_items:
        raise ValueError(f"{label}_too_many")
    return merged


def merge_in_flight(current: Mapping[str, str], incoming: Mapping[str, str]) -> dict[str, str]:
    for attempt_id, work_id in incoming.items():
        existing = current.get(attempt_id)
        if existing is not None and existing != work_id:
            raise ValueError(f"in_flight_conflict:{attempt_id}")
        parsed_work_id, *_ = _parse_attempt_id(attempt_id)
        if parsed_work_id != work_id:
            raise ValueError("in_flight_identity_mismatch")
    return _merge_keyed(current, incoming, label="in_flight", max_items=MAX_CHILD_BATCH)


def merge_candidates(
    current: Mapping[str, CandidateResult],
    incoming: Mapping[str, CandidateResult],
) -> dict[str, CandidateResult]:
    merged = dict(current)
    for attempt_id, candidate in incoming.items():
        _parse_attempt_id(attempt_id)
        existing = merged.get(attempt_id)
        if existing is not None and existing.candidate_hash != candidate.candidate_hash:
            raise ValueError(f"candidate_conflict:{attempt_id}")
        merged[attempt_id] = existing or candidate
    if len(merged) > MAX_CHILD_BATCH:
        raise ValueError("candidates_too_many")
    return merged


def merge_terminal_updates(
    current: Mapping[str, AttemptTerminalUpdate],
    incoming: Mapping[str, AttemptTerminalUpdate],
) -> dict[str, AttemptTerminalUpdate]:
    for attempt_id, update in incoming.items():
        if update.attempt_id != attempt_id:
            raise ValueError("terminal_update_identity_mismatch")
    return _merge_keyed(
        current,
        incoming,
        label="terminal_update",
        max_items=MAX_CHILD_TERMINAL_UPDATES,
    )


class WorkUnitComponentState(TypedDict, total=False):
    planned_work_ids: tuple[str, ...]
    pending_work_ids: tuple[str, ...]
    batch_cursor: int
    in_flight_by_attempt_id: Annotated[dict[str, str], merge_in_flight]
    candidates_by_attempt_id: Annotated[dict[str, CandidateResult], merge_candidates]
    terminal_updates_by_attempt_id: Annotated[dict[str, AttemptTerminalUpdate], merge_terminal_updates]


def validate_work_unit_component_state(values: Mapping[str, Any]) -> None:
    planned = tuple(values.get("planned_work_ids", ()))
    pending = tuple(values.get("pending_work_ids", ()))
    for label, items in (("planned_work_ids", planned), ("pending_work_ids", pending)):
        if len(items) > MAX_PARENT_WORKS or len(set(items)) != len(items) or tuple(sorted(items)) != items:
            raise ValueError(f"{label}_invalid")
        for work_id in items:
            _parse_work_id(work_id)
    cursor = values.get("batch_cursor", 0)
    if not isinstance(cursor, int) or not 0 <= cursor <= len(planned):
        raise ValueError("batch_cursor_invalid")
    merge_in_flight({}, values.get("in_flight_by_attempt_id", {}))
    merge_candidates({}, values.get("candidates_by_attempt_id", {}))
    merge_terminal_updates({}, values.get("terminal_updates_by_attempt_id", {}))


@runtime_checkable
class AttemptArtifactWriter(Protocol):
    async def write_result(self, document: FixtureResultDocument) -> None: ...

    async def write_output(self, relative_path: str, content: bytes) -> None: ...


@runtime_checkable
class WorkUnitCommitReceipt(Protocol):
    record: SubmissionRecord


@runtime_checkable
class WorkUnitStoreProtocol(Protocol):
    async def read_canonical_bytes(self, relative_ref: str, *, max_bytes: int) -> bytes: ...

    async def load_records(self) -> tuple[SubmissionRecord, ...]: ...

    async def read_validation_plan(self, plan: WorkUnitValidationPlan) -> dict[str, ArtifactRead]: ...

    async def commit_candidate(
        self,
        candidate: CandidateResult,
        *,
        scope: Sequence[str],
        validator_version: int = 1,
        passed_checks: Sequence[str] = VALIDATOR_V1_PASSED_CHECKS,
    ) -> WorkUnitCommitReceipt: ...

    def infrastructure_error(self, reason: WorkUnitStorageReason) -> Exception: ...

    async def write_work_spec(self, spec: WorkSpec, attempt: Attempt) -> None: ...

    def attempt_artifact_writer(self, spec: WorkSpec, attempt: Attempt) -> AttemptArtifactWriter: ...


__all__ = [
    "ATTEMPT_ID_RE",
    "BUNDLE_REF_RE",
    "CANDIDATE_HASH_DOMAIN",
    "CONTENT_HASH_RE",
    "FAILURE_DETAIL_HASH_DOMAIN",
    "MAX_CANDIDATE_BYTES",
    "MAX_CHILD_BATCH",
    "MAX_CHILD_TERMINAL_UPDATES",
    "MAX_OUTPUT_BYTES",
    "MAX_OUTPUT_REFS",
    "MAX_REFERENCED_BYTES",
    "MAX_REQUIRED_OUTPUTS",
    "MAX_RESULT_BYTES",
    "MAX_SCOPE_ITEMS",
    "MAX_SOURCE_BYTES",
    "MAX_SOURCE_REFS",
    "MAX_SUBMISSION_LEDGER_BYTES",
    "MAX_SUBMISSION_LEDGER_RECORDS",
    "MAX_SUBMISSION_RECORD_BYTES",
    "MAX_WORK_SPEC_BYTES",
    "MAX_PARENT_ACCEPTED_REFS",
    "MAX_PARENT_ATTEMPTS",
    "MAX_PARENT_FAILURES",
    "MAX_PARENT_WORKS",
    "RESEARCH_ID_RE",
    "SCHEMA_VERSION",
    "SUBMISSION_RECORD_HASH_DOMAIN",
    "SUBMISSION_VALIDATION_PRECEDENCE",
    "VALIDATOR_V1_PASSED_CHECKS",
    "WORK_ID_RE",
    "WORK_UNIT_GATE_VIEW_KEY",
    "WORK_SPEC_HASH_DOMAIN",
    "Attempt",
    "ArtifactRead",
    "AttemptArtifactWriter",
    "AttemptRef",
    "AttemptStatus",
    "AttemptTerminalCode",
    "AttemptTerminalUpdate",
    "CandidateResult",
    "FixtureResultDocument",
    "WAVE0_WORKER_OUTPUT_SCHEMA_VERSION",
    "Wave0SourceIntakeResult",
    "Wave0SourceMeta",
    "Wave0WorkerOutput",
    "WorkerSource",
    "OutputRef",
    "PlannedRead",
    "SourceRef",
    "SubmissionRecord",
    "SubmissionValidationCode",
    "TerminalFailureSummary",
    "WorkSpec",
    "WorkSpecRef",
    "WorkUnitComponentState",
    "WorkUnitCommitReceipt",
    "WorkUnitGateFailure",
    "WorkUnitGateView",
    "WorkUnitValidationPlan",
    "WorkUnitStoreProtocol",
    "canonical_json_bytes",
    "canonicalize_source_url",
    "compute_candidate_hash",
    "compute_failure_detail_hash",
    "compute_record_hash",
    "compute_work_spec_hash",
    "encode_submission_ledger",
    "merge_candidates",
    "merge_in_flight",
    "merge_terminal_updates",
    "parse_submission_ledger",
    "submission_record_matches_candidate",
    "validate_work_unit_component_state",
    "validate_component_gate_view",
    "validate_wrapper_gate_view",
]
