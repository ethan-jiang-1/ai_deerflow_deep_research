"""Immutable work-unit identity contracts.

@impl WOU-001
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from deerflow_deep_research.domain.work_units import (
    MAX_CANDIDATE_BYTES,
    MAX_OUTPUT_BYTES,
    MAX_REFERENCED_BYTES,
    MAX_RESULT_BYTES,
    MAX_SOURCE_BYTES,
    Attempt,
    AttemptStatus,
    AttemptTerminalCode,
    CandidateResult,
    FixtureResultDocument,
    OutputRef,
    SourceRef,
    SubmissionRecord,
    SubmissionValidationCode,
    WorkSpec,
    canonical_json_bytes,
    canonicalize_source_url,
    compute_candidate_hash,
    compute_failure_detail_hash,
    compute_record_hash,
    compute_work_spec_hash,
)

RESEARCH_ID = "r_" + "A" * 43
WORK_ID = "g0_wave0_w0000"
ATTEMPT_ID = f"{WORK_ID}_a00"
NOW = datetime(2026, 7, 14, 1, 2, 3, 4, tzinfo=UTC)


def _work_spec_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema_version": 1,
        "research_id": RESEARCH_ID,
        "generation": 0,
        "phase": "wave0",
        "work_id": WORK_ID,
        "work_ordinal": 0,
        "worker_role": "fixture_worker",
        "scope": ("topic:alpha",),
        "result_contract": "fixture.work-unit",
        "result_schema_version": 1,
        "required_outputs": ("claims.json",),
    }
    payload.update(overrides)
    payload["spec_hash"] = compute_work_spec_hash(payload)
    return payload


def _work_spec(**overrides: object) -> WorkSpec:
    return WorkSpec.model_validate(_work_spec_payload(**overrides))


def _attempt(**overrides: object) -> Attempt:
    payload: dict[str, object] = {
        "schema_version": 1,
        "research_id": RESEARCH_ID,
        "generation": 0,
        "phase": "wave0",
        "work_id": WORK_ID,
        "attempt_id": ATTEMPT_ID,
        "attempt_ordinal": 0,
        "spec_hash": _work_spec().spec_hash,
        "status": "pending",
        "created_at": NOW,
        "started_at": None,
        "expires_at": None,
        "terminal_at": None,
        "terminal_code": None,
    }
    payload.update(overrides)
    return Attempt.model_validate(payload)


def _candidate_payload(**overrides: object) -> dict[str, object]:
    spec = _work_spec()
    attempt_root = f"workspace/deep-research/{RESEARCH_ID}/work/{WORK_ID}/{ATTEMPT_ID}"
    payload: dict[str, object] = {
        "schema_version": 1,
        "research_id": RESEARCH_ID,
        "generation": 0,
        "phase": "wave0",
        "work_id": WORK_ID,
        "attempt_id": ATTEMPT_ID,
        "worker_role": spec.worker_role,
        "spec_hash": spec.spec_hash,
        "result_contract": spec.result_contract,
        "result_ref": f"{attempt_root}/result.json",
        "result_hash": "h_" + "B" * 43,
        "result_schema_version": 1,
        "result_byte_count": 123,
        "output_refs": (
            {
                "path": f"{attempt_root}/outputs/claims.json",
                "content_hash": "h_" + "C" * 43,
                "schema_version": 1,
                "byte_count": 456,
            },
        ),
        "source_refs": (),
    }
    payload.update(overrides)
    payload["candidate_hash"] = compute_candidate_hash(payload)
    return payload


def _candidate(**overrides: object) -> CandidateResult:
    return CandidateResult.model_validate(_candidate_payload(**overrides))


def _record_payload(**overrides: object) -> dict[str, object]:
    payload = _candidate().model_dump(mode="python")
    payload.update(
        {
            "scope": ("topic:alpha",),
            "validator_version": 1,
            "passed_checks": (
                "artifact_hashes",
                "candidate_hash",
                "identity",
                "logical_work_unique",
                "paths",
                "result_contract",
                "source_refs",
                "work_spec",
            ),
            "submitted_at": NOW,
            "previous_record_hash": None,
        }
    )
    payload.update(overrides)
    payload["record_hash"] = compute_record_hash(payload)
    return payload


def test_models_are_frozen_and_extra_forbid() -> None:
    spec = _work_spec()
    with pytest.raises(ValidationError, match="frozen"):
        spec.worker_role = "other"  # type: ignore[misc]
    with pytest.raises(ValidationError, match="extra_forbidden"):
        WorkSpec.model_validate({**_work_spec_payload(), "host_path": "/tmp/leak"})


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"generation": 3, "work_id": "g3_wave0_w0000"}, "generation"),
        ({"work_id": "g0_wave0_w000"}, "work_id"),
        ({"work_id": "g0_wave1_w0000"}, "work_id"),
        ({"work_id": "g0_wave0_w0001"}, "work_id"),
        ({"work_ordinal": 10_000, "work_id": "g0_wave0_w9999"}, "work_ordinal"),
        ({"worker_role": "Bad-Role"}, "worker_role"),
        ({"result_contract": "Fixture Work"}, "result_contract"),
    ],
)
def test_work_spec_identity_grammar_is_exact(overrides: dict[str, object], message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        _work_spec(**overrides)


@pytest.mark.parametrize(
    "attempt_id",
    [
        "g0_wave0_w0000-a00",
        "g0_wave0_w0000_a0",
        "g0_wave0_w0000_a100",
        "g0_wave1_w0000_a00",
    ],
)
def test_attempt_id_and_identity_must_match(attempt_id: str) -> None:
    with pytest.raises(ValidationError, match="attempt_id"):
        _attempt(attempt_id=attempt_id)


def test_attempt_lifecycle_requires_explicit_nulls_and_utc() -> None:
    attempt = _attempt()
    dumped = attempt.model_dump(mode="json")
    assert dumped["started_at"] is None
    assert dumped["expires_at"] is None
    assert dumped["terminal_at"] is None
    assert dumped["terminal_code"] is None
    assert canonical_json_bytes(attempt).decode().count('"terminal_at":null') == 1

    with pytest.raises(ValidationError, match="timezone"):
        _attempt(created_at=datetime(2026, 7, 14))
    with pytest.raises(ValidationError, match="terminal"):
        _attempt(status="submitted", terminal_at=NOW, terminal_code="worker_failed")


def test_terminal_status_and_code_table_is_closed() -> None:
    submitted = _attempt(
        status=AttemptStatus.SUBMITTED,
        started_at=NOW,
        terminal_at=NOW,
        terminal_code=AttemptTerminalCode.ACCEPTED,
    )
    assert submitted.terminal_code is AttemptTerminalCode.ACCEPTED
    with pytest.raises(ValidationError, match="terminal_code"):
        _attempt(
            status="timed_out",
            started_at=NOW,
            terminal_at=NOW,
            terminal_code="worker_failed",
        )


@pytest.mark.parametrize(
    "required_outputs",
    [
        ("b.json", "a.json"),
        ("a.json", "a.json"),
        ("outputs/a.json",),
        ("../a.json",),
        ("/a.json",),
        ("a\\b.json",),
        ("a/./b.json",),
    ],
)
def test_required_outputs_must_be_canonical_sorted_and_unique(required_outputs: tuple[str, ...]) -> None:
    with pytest.raises(ValidationError, match="required_outputs"):
        _work_spec(required_outputs=required_outputs)


def test_scope_and_collection_bounds_are_enforced() -> None:
    with pytest.raises(ValidationError, match="scope"):
        _work_spec(scope=())
    with pytest.raises(ValidationError, match="scope"):
        _work_spec(scope=("x",) * 17)
    with pytest.raises(ValidationError, match="required_outputs"):
        _work_spec(required_outputs=tuple(f"{index:02d}.json" for index in range(17)))


def test_output_and_source_refs_are_bounded_canonical_and_sorted() -> None:
    output = OutputRef(
        path=f"workspace/deep-research/{RESEARCH_ID}/work/{WORK_ID}/{ATTEMPT_ID}/outputs/a.json",
        content_hash="h_" + "B" * 43,
        schema_version=1,
        byte_count=MAX_OUTPUT_BYTES,
    )
    assert output.byte_count == MAX_OUTPUT_BYTES
    with pytest.raises(ValidationError, match="byte_count"):
        OutputRef.model_validate({**output.model_dump(), "byte_count": MAX_OUTPUT_BYTES + 1})

    canonical_url = canonicalize_source_url("HTTPS://Example.COM:443/path/#fragment")
    assert canonical_url == "https://example.com/path"
    source = SourceRef(
        source_id="src:1",
        canonical_url=canonical_url,
        content_ref=f"workspace/deep-research/{RESEARCH_ID}/work/{WORK_ID}/{ATTEMPT_ID}/sources/src-1.json",
        content_hash="h_" + "C" * 43,
        byte_count=MAX_SOURCE_BYTES,
    )
    assert source.canonical_url == canonical_url
    with pytest.raises(ValidationError, match="canonical_url"):
        SourceRef(**{**source.model_dump(), "canonical_url": "https://EXAMPLE.com/path/"})


def test_candidate_collections_and_referenced_bytes_are_exact() -> None:
    candidate = _candidate()
    assert candidate.result_byte_count == 123
    with pytest.raises(ValidationError, match="output_refs"):
        _candidate(output_refs=(candidate.output_refs[0], candidate.output_refs[0]))
    with pytest.raises(ValidationError, match="referenced_bytes"):
        _candidate(
            result_byte_count=MAX_RESULT_BYTES,
            output_refs=tuple(
                {
                    "path": f"workspace/deep-research/{RESEARCH_ID}/work/{WORK_ID}/{ATTEMPT_ID}/outputs/{i:02d}.json",
                    "content_hash": "h_" + chr(66 + i) * 43,
                    "schema_version": 1,
                    "byte_count": MAX_OUTPUT_BYTES,
                }
                for i in range(5)
            ),
        )
    assert MAX_REFERENCED_BYTES == 32 * 1024 * 1024


def test_canonical_models_enforce_encoded_size_bounds() -> None:
    candidate = _candidate()
    assert len(canonical_json_bytes(candidate)) <= MAX_CANDIDATE_BYTES
    with pytest.raises(ValidationError, match="canonical_size"):
        _work_spec(scope=("\U0001f600" * 512,) * 16, required_outputs=tuple(f"{i:02d}.json" for i in range(16)))


def test_hashes_are_domain_separated_and_self_validating() -> None:
    spec_payload = _work_spec_payload()
    assert compute_work_spec_hash(spec_payload) == "h_6iFcPxO_wrcH-sYq3caTpKyRctm0muR0iJWEv3mZxE8"
    assert _work_spec().spec_hash == spec_payload["spec_hash"]

    candidate_payload = _candidate_payload()
    assert compute_candidate_hash(candidate_payload) == "h_R05J3DPDjtlGxFIC9rlbR8nDmVUyIxQOyiva7ccLtx0"
    assert _candidate().candidate_hash == candidate_payload["candidate_hash"]

    record_payload = _record_payload()
    assert compute_record_hash(record_payload) == "h_EH2pCtbV9yc0IP9STSaJSn2k8wL6532mBHTfs7LD27g"
    assert SubmissionRecord.model_validate(record_payload).record_hash == record_payload["record_hash"]

    assert (
        compute_failure_detail_hash(
            terminal_code=AttemptTerminalCode.VALIDATION_FAILED,
            validation_codes=(
                SubmissionValidationCode.WORK_SPEC_MISSING,
                SubmissionValidationCode.ARTIFACT_MISSING,
            ),
        )
        == "h_pqEaXD22PIwR4Z0XZOkxHIrbwRFo1GdTbxuLAmoBiZE"
    )


def test_hash_mismatch_and_identity_mutation_are_rejected() -> None:
    with pytest.raises(ValidationError, match="spec_hash"):
        WorkSpec.model_validate({**_work_spec_payload(), "spec_hash": "h_" + "Z" * 43})
    with pytest.raises(ValidationError, match="candidate_hash"):
        CandidateResult.model_validate({**_candidate_payload(), "worker_role": "other_worker"})


def test_submission_record_validator_v1_shape_is_exact() -> None:
    record = SubmissionRecord.model_validate(_record_payload())
    assert record.previous_record_hash is None
    with pytest.raises(ValidationError, match="passed_checks"):
        SubmissionRecord.model_validate(_record_payload(passed_checks=("identity",)))


def test_fixture_result_document_is_exactly_non_research() -> None:
    spec = _work_spec()
    fixture = FixtureResultDocument(
        schema_version=1,
        research_id=RESEARCH_ID,
        generation=0,
        phase="wave0",
        work_id=WORK_ID,
        attempt_id=ATTEMPT_ID,
        worker_role=spec.worker_role,
        spec_hash=spec.spec_hash,
        result_contract="fixture.work-unit",
        fixture_marker="non_research_fixture",
        output_paths=spec.required_outputs,
        source_ids=(),
    )
    assert fixture.source_ids == ()
    with pytest.raises(ValidationError, match="fixture_marker"):
        FixtureResultDocument.model_validate({**fixture.model_dump(), "fixture_marker": "research"})


def test_per_file_bounds_are_not_interchangeable() -> None:
    assert MAX_RESULT_BYTES == 256 * 1024
    assert MAX_OUTPUT_BYTES == 8 * 1024 * 1024
    assert MAX_SOURCE_BYTES == 8 * 1024 * 1024
