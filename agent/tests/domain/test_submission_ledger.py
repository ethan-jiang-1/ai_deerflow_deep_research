from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest

from deerflow_deep_research.domain.bundle import (
    BundlePathKind,
    classify_bundle_path,
    evidence_ledger_path,
    evidence_staging_path,
)
from deerflow_deep_research.domain.work_units import (
    MAX_SUBMISSION_LEDGER_BYTES,
    MAX_SUBMISSION_LEDGER_RECORDS,
    MAX_SUBMISSION_RECORD_BYTES,
    VALIDATOR_V1_PASSED_CHECKS,
    CandidateResult,
    SubmissionRecord,
    canonical_json_bytes,
    compute_candidate_hash,
    compute_record_hash,
    compute_work_spec_hash,
    encode_submission_ledger,
    parse_submission_ledger,
    submission_record_matches_candidate,
)

RESEARCH_ID = "r_" + "A" * 43
NOW = datetime(2026, 7, 14, 1, 2, 3, 4, tzinfo=UTC)


def _candidate(work_ordinal: int = 0, attempt_ordinal: int = 0, **overrides: object) -> CandidateResult:
    work_id = f"g0_wave0_w{work_ordinal:04d}"
    attempt_id = f"{work_id}_a{attempt_ordinal:02d}"
    spec_payload: dict[str, object] = {
        "schema_version": 1,
        "research_id": RESEARCH_ID,
        "generation": 0,
        "phase": "wave0",
        "work_id": work_id,
        "work_ordinal": work_ordinal,
        "worker_role": "fixture_worker",
        "scope": (f"topic:{work_ordinal}",),
        "result_contract": "fixture.work-unit",
        "result_schema_version": 1,
        "required_outputs": (),
    }
    spec_hash = compute_work_spec_hash(spec_payload)
    attempt_root = f"workspace/deep-research/{RESEARCH_ID}/work/{work_id}/{attempt_id}"
    payload: dict[str, object] = {
        "schema_version": 1,
        "research_id": RESEARCH_ID,
        "generation": 0,
        "phase": "wave0",
        "work_id": work_id,
        "attempt_id": attempt_id,
        "worker_role": "fixture_worker",
        "spec_hash": spec_hash,
        "result_contract": "fixture.work-unit",
        "result_ref": f"{attempt_root}/result.json",
        "result_hash": "h_" + "B" * 43,
        "result_schema_version": 1,
        "result_byte_count": 123,
        "output_refs": (),
        "source_refs": (),
    }
    payload.update(overrides)
    payload["candidate_hash"] = compute_candidate_hash(payload)
    return CandidateResult.model_validate(payload)


def _record(
    work_ordinal: int = 0,
    attempt_ordinal: int = 0,
    *,
    previous_record_hash: str | None = None,
    submitted_at: datetime | None = None,
    candidate: CandidateResult | None = None,
    **overrides: object,
) -> SubmissionRecord:
    candidate = candidate or _candidate(work_ordinal, attempt_ordinal)
    payload = candidate.model_dump(mode="python")
    payload.update(
        {
            "scope": (f"topic:{work_ordinal}",),
            "validator_version": 1,
            "passed_checks": VALIDATOR_V1_PASSED_CHECKS,
            "submitted_at": submitted_at or NOW + timedelta(microseconds=work_ordinal + attempt_ordinal),
            "previous_record_hash": previous_record_hash,
        }
    )
    payload.update(overrides)
    payload["record_hash"] = compute_record_hash(payload)
    return SubmissionRecord.model_validate(payload)


def test_empty_ledger_and_genesis_null_are_canonical() -> None:
    assert parse_submission_ledger(b"") == ()
    assert encode_submission_ledger(()) == b""

    record = _record()
    encoded = encode_submission_ledger((record,))
    assert record.previous_record_hash is None
    assert encoded == canonical_json_bytes(record) + b"\n"
    assert parse_submission_ledger(encoded) == (record,)


def test_submission_record_requires_scope_and_validator_v1_checks() -> None:
    record = _record()
    assert record.scope == ("topic:0",)
    assert record.passed_checks == VALIDATOR_V1_PASSED_CHECKS

    payload = record.model_dump(mode="python")
    payload.pop("scope")
    payload["record_hash"] = compute_record_hash(payload)
    with pytest.raises(ValueError, match="scope"):
        SubmissionRecord.model_validate(payload)

    with pytest.raises(ValueError, match="passed_checks"):
        _record(passed_checks=("identity",))


def test_parser_requires_exact_lf_only_canonical_jsonl() -> None:
    record = _record()
    line = canonical_json_bytes(record)
    invalid = (
        line,
        line + b"\r\n",
        line + b"\n\n",
        json.dumps(record.model_dump(mode="json"), indent=2).encode("utf-8") + b"\n",
        b"\xff\n",
    )
    for payload in invalid:
        with pytest.raises(ValueError, match="submission_ledger"):
            parse_submission_ledger(payload)


def test_parser_validates_schema_and_full_hash_chain() -> None:
    first = _record()
    second = _record(1, previous_record_hash=first.record_hash)
    assert parse_submission_ledger(encode_submission_ledger((first, second))) == (first, second)

    broken = _record(1, previous_record_hash="h_" + "Z" * 43)
    with pytest.raises(ValueError, match="chain"):
        parse_submission_ledger(canonical_json_bytes(first) + b"\n" + canonical_json_bytes(broken) + b"\n")

    unknown = first.model_dump(mode="json")
    unknown["unexpected"] = True
    with pytest.raises(ValueError, match="record_invalid"):
        parse_submission_ledger(canonical_json_bytes(unknown) + b"\n")


def test_replay_comparison_excludes_only_ledger_assigned_fields() -> None:
    candidate = _candidate()
    first = _record(candidate=candidate)
    replay_record = _record(
        candidate=candidate,
        submitted_at=NOW + timedelta(days=1),
        validator_version=2,
        passed_checks=("identity",),
    )
    assert submission_record_matches_candidate(first, candidate)
    assert submission_record_matches_candidate(replay_record, candidate)

    changed_candidate = _candidate(result_hash="h_" + "C" * 43)
    assert not submission_record_matches_candidate(first, changed_candidate)


def test_duplicate_attempt_and_duplicate_logical_work_are_rejected() -> None:
    first = _record()
    duplicate_attempt = _record(previous_record_hash=first.record_hash, submitted_at=NOW + timedelta(seconds=1))
    with pytest.raises(ValueError, match="duplicate_attempt"):
        encode_submission_ledger((first, duplicate_attempt))

    sibling_attempt = _record(0, 1, previous_record_hash=first.record_hash)
    with pytest.raises(ValueError, match="duplicate_work"):
        encode_submission_ledger((first, sibling_attempt))


def test_record_count_and_ledger_byte_bounds_fail_before_parsing() -> None:
    assert MAX_SUBMISSION_RECORD_BYTES == 64 * 1024
    assert MAX_SUBMISSION_LEDGER_RECORDS == 4096
    assert MAX_SUBMISSION_LEDGER_BYTES == 8 * 1024 * 1024

    with pytest.raises(ValueError, match="record_too_large"):
        parse_submission_ledger(b"{" + b" " * MAX_SUBMISSION_RECORD_BYTES + b"}\n")
    with pytest.raises(ValueError, match="too_many_records"):
        parse_submission_ledger(b"{}\n" * (MAX_SUBMISSION_LEDGER_RECORDS + 1))
    with pytest.raises(ValueError, match="too_large"):
        parse_submission_ledger(b"x" * (MAX_SUBMISSION_LEDGER_BYTES + 1))


def test_exact_record_count_limit_round_trips() -> None:
    records: list[SubmissionRecord] = []
    previous: str | None = None
    for ordinal in range(MAX_SUBMISSION_LEDGER_RECORDS):
        record = _record(ordinal, previous_record_hash=previous)
        records.append(record)
        previous = record.record_hash
    encoded = encode_submission_ledger(records)
    assert len(encoded) <= MAX_SUBMISSION_LEDGER_BYTES
    assert len(parse_submission_ledger(encoded)) == MAX_SUBMISSION_LEDGER_RECORDS


def test_staging_path_is_audit_only_and_never_ledger_authority() -> None:
    ledger_path = evidence_ledger_path(RESEARCH_ID)
    staging_path = evidence_staging_path(RESEARCH_ID, "a" * 32)
    assert classify_bundle_path(ledger_path) is BundlePathKind.EVIDENCE
    assert classify_bundle_path(staging_path) is BundlePathKind.AUDIT
