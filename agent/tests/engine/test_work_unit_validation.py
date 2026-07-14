from __future__ import annotations

import base64
import hashlib
from datetime import UTC, datetime

import pytest

from deerflow_deep_research.domain.bundle import output_path, result_path, work_spec_path
from deerflow_deep_research.domain.work_units import (
    SUBMISSION_VALIDATION_PRECEDENCE,
    Attempt,
    CandidateResult,
    OutputRef,
    SourceRef,
    SubmissionRecord,
    SubmissionValidationCode,
    WorkSpec,
    canonical_json_bytes,
    compute_candidate_hash,
    compute_record_hash,
    compute_work_spec_hash,
)
from deerflow_deep_research.engine.work_units.validation import (
    ArtifactRead,
    build_validation_plan,
    validate_submission_candidate,
)

RESEARCH_ID = "r_" + "A" * 43
WORK_ID = "g0_wave0_w0000"
ATTEMPT_ID = f"{WORK_ID}_a00"
NOW = datetime(2026, 7, 14, tzinfo=UTC)


def _hash(data: bytes) -> str:
    digest = hashlib.sha256(data).digest()
    return "h_" + base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def _fixture(output_paths: tuple[str, ...] = ("claims.json",), **overrides: object) -> bytes:
    payload: dict[str, object] = {
        "schema_version": 1,
        "research_id": RESEARCH_ID,
        "generation": 0,
        "phase": "wave0",
        "work_id": WORK_ID,
        "attempt_id": ATTEMPT_ID,
        "worker_role": "fixture_worker",
        "spec_hash": _spec().spec_hash,
        "result_contract": "fixture.work-unit",
        "fixture_marker": "non_research_fixture",
        "output_paths": output_paths,
        "source_ids": (),
    }
    payload.update(overrides)
    return canonical_json_bytes(payload)


def _spec(**overrides: object) -> WorkSpec:
    payload: dict[str, object] = {
        "schema_version": 1,
        "research_id": RESEARCH_ID,
        "generation": 0,
        "phase": "wave0",
        "work_id": WORK_ID,
        "work_ordinal": 0,
        "worker_role": "fixture_worker",
        "scope": ("topic",),
        "result_contract": "fixture.work-unit",
        "result_schema_version": 1,
        "required_outputs": ("claims.json",),
    }
    payload.update(overrides)
    payload["spec_hash"] = compute_work_spec_hash(payload)
    return WorkSpec.model_validate(payload)


def _attempt(spec: WorkSpec | None = None, **overrides: object) -> Attempt:
    spec = spec or _spec()
    payload: dict[str, object] = {
        "schema_version": 1,
        "research_id": spec.research_id,
        "generation": spec.generation,
        "phase": spec.phase,
        "work_id": spec.work_id,
        "attempt_id": ATTEMPT_ID,
        "attempt_ordinal": 0,
        "spec_hash": spec.spec_hash,
        "status": "running",
        "created_at": NOW,
        "started_at": NOW,
        "expires_at": None,
        "terminal_at": None,
        "terminal_code": None,
    }
    payload.update(overrides)
    return Attempt.model_validate(payload)


def _candidate(spec: WorkSpec | None = None, result_bytes: bytes | None = None, **overrides: object) -> CandidateResult:
    spec = spec or _spec()
    result_bytes = result_bytes or _fixture()
    output_bytes = b'{"claims":[]}'
    payload: dict[str, object] = {
        "schema_version": 1,
        "research_id": spec.research_id,
        "generation": spec.generation,
        "phase": spec.phase,
        "work_id": spec.work_id,
        "attempt_id": ATTEMPT_ID,
        "worker_role": spec.worker_role,
        "spec_hash": spec.spec_hash,
        "result_contract": spec.result_contract,
        "result_ref": result_path(RESEARCH_ID, WORK_ID, ATTEMPT_ID),
        "result_hash": _hash(result_bytes),
        "result_schema_version": 1,
        "result_byte_count": len(result_bytes),
        "output_refs": (
            OutputRef(
                path=output_path(RESEARCH_ID, WORK_ID, ATTEMPT_ID, "claims.json"),
                content_hash=_hash(output_bytes),
                schema_version=1,
                byte_count=len(output_bytes),
            ),
        ),
        "source_refs": (),
    }
    payload.update(overrides)
    payload["candidate_hash"] = compute_candidate_hash(payload)
    return CandidateResult.model_validate(payload)


def _artifacts(spec: WorkSpec | None = None, candidate: CandidateResult | None = None) -> dict[str, ArtifactRead]:
    spec = spec or _spec()
    candidate = candidate or _candidate(spec)
    result_bytes = _fixture()
    output_bytes = b'{"claims":[]}'
    return {
        work_spec_path(RESEARCH_ID, WORK_ID, ATTEMPT_ID): ArtifactRead(data=canonical_json_bytes(spec)),
        candidate.result_ref: ArtifactRead(data=result_bytes),
        candidate.output_refs[0].path: ArtifactRead(data=output_bytes),
    }


def test_validation_registry_order_is_exact_and_valid_fixture_passes() -> None:
    assert tuple(SubmissionValidationCode) == SUBMISSION_VALIDATION_PRECEDENCE
    spec, attempt = _spec(), _attempt()
    candidate = _candidate(spec)
    plan = build_validation_plan(spec, attempt, candidate)
    assert tuple(item.ref for item in plan.reads) == tuple(_artifacts(spec, candidate))
    assert validate_submission_candidate(spec, attempt, candidate, _artifacts(spec, candidate)) == ()


@pytest.mark.parametrize(
    ("mutate", "expected"),
    [
        ({"research_id": "r_" + "B" * 43}, SubmissionValidationCode.IDENTITY_MISMATCH),
        ({"worker_role": "other_worker"}, SubmissionValidationCode.IDENTITY_MISMATCH),
        ({"spec_hash": "h_" + "Z" * 43}, SubmissionValidationCode.SPEC_HASH_MISMATCH),
        ({"result_contract": "unknown.contract"}, SubmissionValidationCode.RESULT_CONTRACT_UNSUPPORTED),
        ({"result_schema_version": 2}, SubmissionValidationCode.SCHEMA_VERSION_UNSUPPORTED),
        ({"candidate_hash": "h_" + "Z" * 43}, SubmissionValidationCode.CANDIDATE_HASH_MISMATCH),
    ],
)
def test_identity_schema_contract_and_candidate_hash_denials(
    mutate: dict[str, object],
    expected: SubmissionValidationCode,
) -> None:
    spec, attempt = _spec(), _attempt()
    candidate = _candidate(spec).model_copy(update=mutate)
    assert expected in validate_submission_candidate(spec, attempt, candidate, _artifacts(spec, _candidate(spec)))


@pytest.mark.parametrize(
    ("ref", "read", "expected"),
    [
        ("result", ArtifactRead(data=None), SubmissionValidationCode.ARTIFACT_MISSING),
        ("result", ArtifactRead(data=b""), SubmissionValidationCode.ARTIFACT_EMPTY),
        ("result", ArtifactRead(data=b"wrong"), SubmissionValidationCode.CONTENT_HASH_MISMATCH),
        ("result", ArtifactRead(data=_fixture(), contained=False), SubmissionValidationCode.PATH_NOT_CONTAINED),
        ("result", ArtifactRead(data=_fixture(), stable=False), SubmissionValidationCode.PATH_NOT_CONTAINED),
    ],
)
def test_artifact_read_failures_are_typed(ref: str, read: ArtifactRead, expected: SubmissionValidationCode) -> None:
    spec, attempt, candidate = _spec(), _attempt(), _candidate()
    artifacts = _artifacts(spec, candidate)
    artifacts[candidate.result_ref] = read
    assert expected in validate_submission_candidate(spec, attempt, candidate, artifacts)


def test_fixture_schema_and_exact_output_set_are_enforced() -> None:
    spec, attempt = _spec(), _attempt()
    bad_result = _fixture(output_paths=())
    candidate = _candidate(spec, result_bytes=bad_result)
    artifacts = _artifacts(spec, candidate)
    artifacts[candidate.result_ref] = ArtifactRead(data=bad_result)
    assert SubmissionValidationCode.INVALID_OUTPUT_SCHEMA in validate_submission_candidate(
        spec, attempt, candidate, artifacts
    )

    missing_output = candidate.model_copy(update={"output_refs": ()})
    missing_output = missing_output.model_copy(update={"candidate_hash": compute_candidate_hash(missing_output)})
    missing_codes = validate_submission_candidate(spec, attempt, missing_output, artifacts)
    assert SubmissionValidationCode.INVALID_OUTPUT_SCHEMA in missing_codes
    assert SubmissionValidationCode.PATH_NOT_CANONICAL in missing_codes


def test_noncanonical_path_and_source_url_are_rejected_without_rewriting() -> None:
    spec, attempt, candidate = _spec(), _attempt(), _candidate()
    bad_path = candidate.model_copy(update={"result_ref": "../result.json"})
    bad_path = bad_path.model_copy(update={"candidate_hash": compute_candidate_hash(bad_path)})
    assert SubmissionValidationCode.PATH_NOT_CANONICAL in validate_submission_candidate(
        spec, attempt, bad_path, _artifacts(spec, candidate)
    )

    source_bytes = b"source"
    source = SourceRef(
        source_id="source:1",
        canonical_url="https://example.com/path",
        content_ref=f"workspace/deep-research/{RESEARCH_ID}/evidence/source.txt",
        content_hash=_hash(source_bytes),
        byte_count=len(source_bytes),
    )
    bad_source = source.model_copy(update={"canonical_url": "HTTPS://EXAMPLE.COM:443/path/#fragment"})
    with_source = candidate.model_copy(update={"source_refs": (bad_source,)})
    with_source = with_source.model_copy(update={"candidate_hash": compute_candidate_hash(with_source)})
    artifacts = _artifacts(spec, candidate)
    artifacts[source.content_ref] = ArtifactRead(data=source_bytes)
    assert SubmissionValidationCode.SOURCE_REF_INVALID in validate_submission_candidate(
        spec, attempt, with_source, artifacts
    )


def test_unknown_fixture_marker_and_wrong_embedded_identity_fail_schema_or_identity() -> None:
    spec, attempt = _spec(), _attempt()
    for result_bytes, expected in (
        (_fixture(fixture_marker="research"), SubmissionValidationCode.INVALID_OUTPUT_SCHEMA),
        (_fixture(worker_role="other_worker"), SubmissionValidationCode.IDENTITY_MISMATCH),
    ):
        candidate = _candidate(spec, result_bytes=result_bytes)
        artifacts = _artifacts(spec, candidate)
        artifacts[candidate.result_ref] = ArtifactRead(data=result_bytes)
        assert expected in validate_submission_candidate(spec, attempt, candidate, artifacts)


def test_work_spec_missing_and_noncanonical_bytes_are_distinct() -> None:
    spec, attempt, candidate = _spec(), _attempt(), _candidate()
    artifacts = _artifacts(spec, candidate)
    spec_ref = work_spec_path(RESEARCH_ID, WORK_ID, ATTEMPT_ID)
    artifacts[spec_ref] = ArtifactRead(data=None)
    assert SubmissionValidationCode.WORK_SPEC_MISSING in validate_submission_candidate(
        spec, attempt, candidate, artifacts
    )
    artifacts[spec_ref] = ArtifactRead(data=canonical_json_bytes(spec) + b" ")
    codes = validate_submission_candidate(spec, attempt, candidate, artifacts)
    assert SubmissionValidationCode.SPEC_HASH_MISMATCH in codes


def test_candidate_conflict_is_last_and_collect_all_is_deduplicated() -> None:
    spec, attempt, candidate = _spec(), _attempt(), _candidate()
    record_payload = candidate.model_dump(mode="python")
    record_payload.update(
        scope=spec.scope,
        validator_version=1,
        passed_checks=(
            "artifact_hashes",
            "candidate_hash",
            "identity",
            "logical_work_unique",
            "paths",
            "result_contract",
            "source_refs",
            "work_spec",
        ),
        submitted_at=NOW,
        previous_record_hash=None,
    )
    record_payload["record_hash"] = compute_record_hash(record_payload)
    record = SubmissionRecord.model_validate(record_payload)
    changed = candidate.model_copy(update={"candidate_hash": "h_" + "Z" * 43})
    codes = validate_submission_candidate(
        spec, attempt, changed, _artifacts(spec, candidate), accepted_records=(record,)
    )
    assert codes == (
        SubmissionValidationCode.CANDIDATE_HASH_MISMATCH,
        SubmissionValidationCode.CANDIDATE_CONFLICT,
    )
