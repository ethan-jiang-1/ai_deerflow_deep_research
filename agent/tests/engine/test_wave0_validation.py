"""Wave0 source-intake result-contract registry and submit validation.

@impl WAN-003
"""

from __future__ import annotations

import base64
import hashlib
from datetime import UTC, datetime

from deerflow_deep_research.domain.bundle import output_path, result_path, work_spec_path
from deerflow_deep_research.domain.work_units import (
    Attempt,
    CandidateResult,
    OutputRef,
    SourceRef,
    SubmissionValidationCode,
    Wave0SourceIntakeResult,
    Wave0SourceMeta,
    WorkSpec,
    canonical_json_bytes,
    compute_candidate_hash,
    compute_work_spec_hash,
)
from deerflow_deep_research.engine.work_units.validation import (
    ArtifactRead,
    get_result_contract_handler,
    validate_submission_candidate,
)

RESEARCH_ID = "r_" + "A" * 43
WORK_ID = "g0_wave0_w0000"
ATTEMPT_ID = "g0_wave0_w0000_a00"
NOW = datetime(2026, 7, 14, tzinfo=UTC)
SOURCE_REF = f"workspace/deep-research/{RESEARCH_ID}/evidence/source.json"
SOURCE_BYTES = b'{"source":"example"}'


def _hash(data: bytes) -> str:
    digest = hashlib.sha256(data).digest()
    return "h_" + base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def _spec(**overrides: object) -> WorkSpec:
    payload: dict[str, object] = {
        "schema_version": 1,
        "research_id": RESEARCH_ID,
        "generation": 0,
        "phase": "wave0",
        "work_id": WORK_ID,
        "work_ordinal": 0,
        "worker_role": "wave0_intake",
        "scope": ("topic-batteries",),
        "result_contract": "wave0.source-intake",
        "result_schema_version": 1,
        "required_outputs": ("claims.json",),
    }
    payload.update(overrides)
    payload["spec_hash"] = compute_work_spec_hash(payload)
    return WorkSpec.model_validate(payload)


def _attempt(spec: WorkSpec | None = None) -> Attempt:
    spec = spec or _spec()
    return Attempt.model_validate(
        {
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
    )


def _result_doc(spec: WorkSpec, **overrides: object) -> bytes:
    payload: dict[str, object] = {
        "schema_version": 1,
        "research_id": spec.research_id,
        "generation": spec.generation,
        "phase": spec.phase,
        "work_id": spec.work_id,
        "attempt_id": ATTEMPT_ID,
        "worker_role": spec.worker_role,
        "spec_hash": spec.spec_hash,
        "result_contract": "wave0.source-intake",
        "output_paths": ("claims.json",),
        "source_ids": ("source:1",),
        "sources": [
            {
                "source_id": "source:1",
                "canonical_url": "https://example.com/path",
                "title": "Example source",
                "content_ref": SOURCE_REF,
                "fetch_status": "fetched",
            }
        ],
        "baseline_facts": ("Fact one.",),
        "limitations": "",
    }
    payload.update(overrides)
    return canonical_json_bytes(Wave0SourceIntakeResult.model_validate(payload).model_dump(mode="python"))


def _source_ref() -> SourceRef:
    return SourceRef(
        source_id="source:1",
        canonical_url="https://example.com/path",
        content_ref=SOURCE_REF,
        content_hash=_hash(SOURCE_BYTES),
        byte_count=len(SOURCE_BYTES),
    )


def _candidate(spec: WorkSpec, result_bytes: bytes | None = None, **overrides: object) -> CandidateResult:
    result_bytes = result_bytes or _result_doc(spec)
    output_bytes = b'{"claims":[]}'
    source = _source_ref()
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
        "source_refs": (source,),
    }
    payload.update(overrides)
    payload["candidate_hash"] = compute_candidate_hash(payload)
    return CandidateResult.model_validate(payload)


def _artifacts(
    spec: WorkSpec, candidate: CandidateResult, result_bytes: bytes | None = None
) -> dict[str, ArtifactRead]:
    result_bytes = result_bytes or _result_doc(spec)
    output_bytes = b'{"claims":[]}'
    artifacts: dict[str, ArtifactRead] = {
        work_spec_path(RESEARCH_ID, WORK_ID, ATTEMPT_ID): ArtifactRead(data=canonical_json_bytes(spec)),
        candidate.result_ref: ArtifactRead(data=result_bytes),
        candidate.output_refs[0].path: ArtifactRead(data=output_bytes),
        SOURCE_REF: ArtifactRead(data=SOURCE_BYTES),
    }
    return artifacts


def test_registry_registers_fixture_and_wave0_and_rejects_unknown() -> None:
    assert get_result_contract_handler("fixture.work-unit", 1) is not None
    assert get_result_contract_handler("wave0.source-intake", 1) is not None
    assert get_result_contract_handler("unknown.contract", 1) is None


def test_valid_wave0_candidate_passes_validation() -> None:
    spec, attempt = _spec(), _attempt()
    candidate = _candidate(spec)
    assert validate_submission_candidate(spec, attempt, candidate, _artifacts(spec, candidate)) == ()


def test_wave0_result_contract_mismatch_is_rejected() -> None:
    spec, attempt = _spec(), _attempt()
    candidate = _candidate(spec).model_copy(update={"result_contract": "unknown.contract"})
    candidate = candidate.model_copy(update={"candidate_hash": compute_candidate_hash(candidate)})
    assert SubmissionValidationCode.RESULT_CONTRACT_UNSUPPORTED in validate_submission_candidate(
        spec, attempt, candidate, _artifacts(spec, _candidate(spec))
    )


def test_wave0_result_identity_mismatch_is_rejected() -> None:
    spec, attempt = _spec(), _attempt()
    bad_doc = _result_doc(spec, worker_role="other_worker")
    candidate = _candidate(spec, result_bytes=bad_doc)
    artifacts = _artifacts(spec, candidate, result_bytes=bad_doc)
    codes = validate_submission_candidate(spec, attempt, candidate, artifacts)
    assert SubmissionValidationCode.IDENTITY_MISMATCH in codes


def test_wave0_non_canonical_source_url_is_rejected() -> None:
    spec, attempt = _spec(), _attempt()
    bad_source = _source_ref().model_copy(update={"canonical_url": "HTTPS://Example.com:443/path/#frag"})
    candidate = _candidate(spec).model_copy(update={"source_refs": (bad_source,)})
    candidate = candidate.model_copy(update={"candidate_hash": compute_candidate_hash(candidate)})
    assert SubmissionValidationCode.SOURCE_REF_INVALID in validate_submission_candidate(
        spec, attempt, candidate, _artifacts(spec, _candidate(spec))
    )


def test_wave0_source_ids_diverging_from_doc_is_rejected() -> None:
    spec, attempt = _spec(), _attempt()
    diverged = Wave0SourceMeta.model_validate(
        {
            "source_id": "source:2",
            "canonical_url": "https://example.com/other",
            "title": "Other",
            "content_ref": SOURCE_REF,
            "fetch_status": "fetched",
        }
    )
    # Document claims source:1 and source:2 but candidate only carries source:1.
    doc = _result_doc(
        spec,
        source_ids=("source:1", "source:2"),
        sources=[
            {
                "source_id": "source:1",
                "canonical_url": "https://example.com/path",
                "title": "A",
                "content_ref": SOURCE_REF,
                "fetch_status": "fetched",
            },
            diverged.model_dump(mode="python"),
        ],
    )
    candidate = _candidate(spec, result_bytes=doc)
    artifacts = _artifacts(spec, candidate, result_bytes=doc)
    codes = validate_submission_candidate(spec, attempt, candidate, artifacts)
    assert SubmissionValidationCode.INVALID_OUTPUT_SCHEMA in codes
