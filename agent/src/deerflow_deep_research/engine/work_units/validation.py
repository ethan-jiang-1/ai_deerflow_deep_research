"""Pure ordered work-unit submission validation.

@impl WOU-003
"""

from __future__ import annotations

import base64
import hashlib
from collections.abc import Mapping, Sequence

from deerflow_deep_research.domain.bundle import output_path, result_path, work_spec_path
from deerflow_deep_research.domain.work_units import (
    SUBMISSION_VALIDATION_PRECEDENCE,
    ArtifactRead,
    Attempt,
    CandidateResult,
    FixtureResultDocument,
    PlannedRead,
    SubmissionRecord,
    SubmissionValidationCode,
    WorkSpec,
    WorkUnitValidationPlan,
    canonical_json_bytes,
    canonicalize_source_url,
    compute_candidate_hash,
)


def _content_hash(data: bytes) -> str:
    digest = hashlib.sha256(data).digest()
    return "h_" + base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def build_validation_plan(spec: WorkSpec, attempt: Attempt, candidate: CandidateResult) -> WorkUnitValidationPlan:
    reads = [
        PlannedRead(work_spec_path(spec.research_id, spec.work_id, attempt.attempt_id), 16 * 1024),
        PlannedRead(candidate.result_ref, 256 * 1024),
    ]
    reads.extend(PlannedRead(ref.path, 8 * 1024 * 1024) for ref in candidate.output_refs)
    reads.extend(PlannedRead(ref.content_ref, 8 * 1024 * 1024) for ref in candidate.source_refs)
    return WorkUnitValidationPlan(tuple(reads))


def _ordered(codes: Sequence[SubmissionValidationCode]) -> tuple[SubmissionValidationCode, ...]:
    present = set(codes)
    return tuple(code for code in SUBMISSION_VALIDATION_PRECEDENCE if code in present)


def _read_codes(
    read: ArtifactRead | None,
    *,
    missing_code: SubmissionValidationCode,
    expected_hash: str | None = None,
    expected_bytes: int | None = None,
) -> list[SubmissionValidationCode]:
    codes: list[SubmissionValidationCode] = []
    if read is None or read.data is None:
        return [missing_code]
    if not read.contained or not read.stable or not read.regular:
        codes.append(SubmissionValidationCode.PATH_NOT_CONTAINED)
    if not read.data:
        codes.append(SubmissionValidationCode.ARTIFACT_EMPTY)
        return codes
    if expected_hash is not None and _content_hash(read.data) != expected_hash:
        codes.append(SubmissionValidationCode.CONTENT_HASH_MISMATCH)
    if expected_bytes is not None and len(read.data) != expected_bytes:
        codes.append(SubmissionValidationCode.CONTENT_HASH_MISMATCH)
    return codes


def validate_submission_candidate(
    spec: WorkSpec,
    attempt: Attempt,
    candidate: CandidateResult,
    artifacts: Mapping[str, ArtifactRead],
    *,
    accepted_records: Sequence[SubmissionRecord] = (),
) -> tuple[SubmissionValidationCode, ...]:
    codes: list[SubmissionValidationCode] = []

    identity = (
        candidate.research_id,
        candidate.generation,
        candidate.phase,
        candidate.work_id,
        candidate.attempt_id,
        candidate.worker_role,
    )
    expected_identity = (
        spec.research_id,
        spec.generation,
        spec.phase,
        spec.work_id,
        attempt.attempt_id,
        spec.worker_role,
    )
    if identity != expected_identity:
        codes.append(SubmissionValidationCode.IDENTITY_MISMATCH)
    if attempt.spec_hash != spec.spec_hash or candidate.spec_hash != spec.spec_hash:
        codes.append(SubmissionValidationCode.SPEC_HASH_MISMATCH)
    if candidate.schema_version != 1 or candidate.result_schema_version != 1:
        codes.append(SubmissionValidationCode.SCHEMA_VERSION_UNSUPPORTED)
    if (candidate.result_contract, candidate.result_schema_version) != ("fixture.work-unit", 1):
        codes.append(SubmissionValidationCode.RESULT_CONTRACT_UNSUPPORTED)

    expected_spec_ref = work_spec_path(spec.research_id, spec.work_id, attempt.attempt_id)
    expected_result_ref = result_path(spec.research_id, spec.work_id, attempt.attempt_id)
    expected_outputs = tuple(
        output_path(spec.research_id, spec.work_id, attempt.attempt_id, relative) for relative in spec.required_outputs
    )
    candidate_outputs = tuple(ref.path for ref in candidate.output_refs)
    if candidate.result_ref != expected_result_ref or candidate_outputs != expected_outputs:
        codes.append(SubmissionValidationCode.PATH_NOT_CANONICAL)

    spec_read = artifacts.get(expected_spec_ref)
    codes.extend(_read_codes(spec_read, missing_code=SubmissionValidationCode.WORK_SPEC_MISSING))
    if spec_read is not None and spec_read.data:
        try:
            parsed_spec = WorkSpec.model_validate_json(spec_read.data)
        except ValueError:
            codes.append(SubmissionValidationCode.SPEC_HASH_MISMATCH)
        else:
            if parsed_spec != spec or canonical_json_bytes(parsed_spec) != spec_read.data:
                codes.append(SubmissionValidationCode.SPEC_HASH_MISMATCH)

    result_read = artifacts.get(candidate.result_ref)
    codes.extend(
        _read_codes(
            result_read,
            missing_code=SubmissionValidationCode.ARTIFACT_MISSING,
            expected_hash=candidate.result_hash,
            expected_bytes=candidate.result_byte_count,
        )
    )
    if result_read is not None and result_read.data:
        try:
            fixture = FixtureResultDocument.model_validate_json(result_read.data)
        except ValueError:
            codes.append(SubmissionValidationCode.INVALID_OUTPUT_SCHEMA)
        else:
            fixture_identity = (
                fixture.research_id,
                fixture.generation,
                fixture.phase,
                fixture.work_id,
                fixture.attempt_id,
                fixture.worker_role,
                fixture.spec_hash,
            )
            expected_fixture_identity = (
                spec.research_id,
                spec.generation,
                spec.phase,
                spec.work_id,
                attempt.attempt_id,
                spec.worker_role,
                spec.spec_hash,
            )
            if fixture_identity != expected_fixture_identity:
                codes.append(SubmissionValidationCode.IDENTITY_MISMATCH)
            if (
                fixture.result_contract != spec.result_contract
                or fixture.output_paths != spec.required_outputs
                or fixture.source_ids != tuple(ref.source_id for ref in candidate.source_refs)
            ):
                codes.append(SubmissionValidationCode.INVALID_OUTPUT_SCHEMA)

    if candidate_outputs != expected_outputs or len(candidate.output_refs) != len(spec.required_outputs):
        codes.append(SubmissionValidationCode.INVALID_OUTPUT_SCHEMA)
    for output in candidate.output_refs:
        codes.extend(
            _read_codes(
                artifacts.get(output.path),
                missing_code=SubmissionValidationCode.ARTIFACT_MISSING,
                expected_hash=output.content_hash,
                expected_bytes=output.byte_count,
            )
        )

    for source in candidate.source_refs:
        try:
            if canonicalize_source_url(source.canonical_url) != source.canonical_url:
                raise ValueError
        except ValueError:
            codes.append(SubmissionValidationCode.SOURCE_REF_INVALID)
        source_codes = _read_codes(
            artifacts.get(source.content_ref),
            missing_code=SubmissionValidationCode.ARTIFACT_MISSING,
            expected_hash=source.content_hash,
            expected_bytes=source.byte_count,
        )
        if source_codes:
            codes.append(SubmissionValidationCode.SOURCE_REF_INVALID)
            codes.extend(source_codes)

    if compute_candidate_hash(candidate) != candidate.candidate_hash:
        codes.append(SubmissionValidationCode.CANDIDATE_HASH_MISMATCH)
    for record in accepted_records:
        if record.work_id == candidate.work_id and record.candidate_hash != candidate.candidate_hash:
            codes.append(SubmissionValidationCode.CANDIDATE_CONFLICT)
            break
    return _ordered(codes)


__all__ = [
    "ArtifactRead",
    "PlannedRead",
    "WorkUnitValidationPlan",
    "build_validation_plan",
    "validate_submission_candidate",
]
