from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from deerflow_deep_research.domain.failure_codes import FailureCode
from deerflow_deep_research.domain.work_units import (
    AttemptStatus,
    AttemptTerminalCode,
    SubmissionValidationCode,
)
from deerflow_deep_research.engine.work_units.ids import allocate_attempt_id, allocate_work_id
from deerflow_deep_research.engine.work_units.kernel import (
    ConcurrencyPolicy,
    WorkIntent,
    allocate_attempt,
    materialize_work_spec,
    project_terminal_failure,
    require_attempt_submittable,
    retry_allowed,
    select_batch,
    transition_attempt,
    validate_parent_projection,
    work_is_drained,
)

RESEARCH_ID = "r_" + "A" * 43
NOW = datetime(2026, 7, 14, tzinfo=UTC)


def _intent() -> WorkIntent:
    return WorkIntent(
        worker_role="fixture_worker",
        scope=("topic",),
        result_contract="fixture.work-unit",
        result_schema_version=1,
        required_outputs=("claims.json",),
    )


def _spec(ordinal: int = 0):
    return materialize_work_spec(
        research_id=RESEARCH_ID,
        generation=0,
        phase="wave0",
        work_ordinal=ordinal,
        intent=_intent(),
    )


def test_ids_are_exact_stable_and_range_checked() -> None:
    assert allocate_work_id(0, "wave0", 0) == "g0_wave0_w0000"
    assert allocate_attempt_id("g0_wave0_w0000", 0) == "g0_wave0_w0000_a00"
    with pytest.raises(ValueError, match="work_ordinal"):
        allocate_work_id(0, "wave0", 10_000)
    with pytest.raises(ValueError, match="attempt_ordinal"):
        allocate_attempt_id("g0_wave0_w0000", 100)


def test_materialization_replays_same_spec_and_exposes_same_id_conflict() -> None:
    first = _spec()
    assert first == _spec()
    changed = WorkIntent(
        worker_role="fixture_worker",
        scope=("different",),
        result_contract="fixture.work-unit",
        result_schema_version=1,
        required_outputs=("claims.json",),
    )
    other = materialize_work_spec(
        research_id=RESEARCH_ID,
        generation=0,
        phase="wave0",
        work_ordinal=0,
        intent=changed,
    )
    assert other.work_id == first.work_id and other.spec_hash != first.spec_hash


def test_concurrency_and_cursor_batching_are_bounded_and_completion_independent() -> None:
    assert ConcurrencyPolicy(max_concurrency=3).max_concurrency == 3
    for invalid in (0, 17):
        with pytest.raises(ValueError, match="max_concurrency"):
            ConcurrencyPolicy(max_concurrency=invalid)
    planned = tuple(allocate_work_id(0, "wave0", ordinal) for ordinal in range(7))
    batch, cursor = select_batch(planned, cursor=0, max_concurrency=3)
    assert batch == planned[:3] and cursor == 3
    second, cursor = select_batch(planned, cursor=cursor, max_concurrency=3)
    assert second == planned[3:6] and cursor == 6


def test_attempt_transition_table_timestamps_and_exact_replay() -> None:
    spec = _spec()
    pending = allocate_attempt(spec, attempt_ordinal=0, created_at=NOW, expires_at=NOW + timedelta(minutes=1))
    running = transition_attempt(pending, status="running", at=NOW)
    assert transition_attempt(running, status="running", at=NOW) == running
    submitted = transition_attempt(
        running,
        status="submitted",
        at=NOW + timedelta(seconds=1),
        terminal_code="accepted",
    )
    assert submitted.status is AttemptStatus.SUBMITTED
    with pytest.raises(ValueError, match="terminal"):
        transition_attempt(submitted, status="running", at=NOW + timedelta(seconds=2))
    with pytest.raises(ValueError, match="transition"):
        transition_attempt(pending, status="failed", at=NOW, terminal_code="worker_failed")


def test_expiry_boundary_and_direct_pending_cancel() -> None:
    spec = _spec()
    expiry = NOW + timedelta(seconds=10)
    pending = allocate_attempt(spec, attempt_ordinal=0, created_at=NOW, expires_at=expiry)
    cancelled = transition_attempt(pending, status="cancelled", at=NOW, terminal_code="cancelled")
    assert cancelled.started_at is None
    running = transition_attempt(
        allocate_attempt(spec, attempt_ordinal=1, created_at=NOW, expires_at=expiry), status="running", at=NOW
    )
    with pytest.raises(ValueError, match="expired"):
        transition_attempt(running, status="timed_out", at=expiry - timedelta(microseconds=1), terminal_code="expired")
    assert (
        transition_attempt(running, status="timed_out", at=expiry, terminal_code="expired").terminal_code
        is AttemptTerminalCode.EXPIRED
    )


def test_submit_guard_rejects_inactive_terminal_and_expired_attempts() -> None:
    spec = _spec()
    expiry = NOW + timedelta(seconds=10)
    pending = allocate_attempt(spec, attempt_ordinal=0, created_at=NOW, expires_at=expiry)
    require_attempt_submittable(pending, active_attempt_id=pending.attempt_id, now=NOW)
    with pytest.raises(ValueError, match="not_active"):
        require_attempt_submittable(pending, active_attempt_id=None, now=NOW)
    with pytest.raises(ValueError, match="expired"):
        require_attempt_submittable(pending, active_attempt_id=pending.attempt_id, now=expiry)
    cancelled = transition_attempt(pending, status="cancelled", at=NOW, terminal_code="cancelled")
    with pytest.raises(ValueError, match="terminal"):
        require_attempt_submittable(cancelled, active_attempt_id=cancelled.attempt_id, now=NOW)


@pytest.mark.parametrize(
    ("status", "code", "allowed"),
    [
        ("failed", "worker_failed", True),
        ("timed_out", "deadline_exceeded", True),
        ("cancelled", "cancelled", False),
        ("cancelled", "superseded", False),
        ("submitted", "accepted", False),
    ],
)
def test_retry_policy_is_one_way_and_acceptance_wins(status: str, code: str, allowed: bool) -> None:
    spec = _spec()
    pending = allocate_attempt(spec, attempt_ordinal=0, created_at=NOW)
    running = transition_attempt(pending, status="running", at=NOW)
    terminal = transition_attempt(running, status=status, at=NOW, terminal_code=code)
    assert retry_allowed(terminal, accepted=False) is allowed
    assert not retry_allowed(terminal, accepted=True)


@pytest.mark.parametrize(
    ("terminal_code", "validation_codes", "failure"),
    [
        ("worker_failed", (), FailureCode.WORK_FAILED),
        ("deadline_exceeded", (), FailureCode.WORK_TIMED_OUT),
        ("cancelled", (), FailureCode.WORK_CANCELLED),
        (
            "validation_failed",
            (SubmissionValidationCode.WORK_SPEC_MISSING,),
            FailureCode.MISSING_WORK_SPEC,
        ),
        (
            "validation_failed",
            (SubmissionValidationCode.CONTENT_HASH_MISMATCH,),
            FailureCode.CONTENT_HASH_MISMATCH,
        ),
    ],
)
def test_terminal_failure_projection_is_total_and_stable(terminal_code, validation_codes, failure) -> None:
    summary = project_terminal_failure(terminal_code=terminal_code, validation_codes=validation_codes)
    assert summary.failure_code is failure
    assert summary.detail_hash.startswith("h_")


def test_drain_is_structural_only() -> None:
    assert work_is_drained((), {})
    assert not work_is_drained(("g0_wave0_w0000",), {})
    assert not work_is_drained((), {"g0_wave0_w0000_a00": "g0_wave0_w0000"})


def test_final_parent_projection_requires_status_active_failure_and_acceptance_consistency() -> None:
    spec = _spec()
    pending = allocate_attempt(spec, attempt_ordinal=0, created_at=NOW)
    running = transition_attempt(pending, status="running", at=NOW)
    submitted = transition_attempt(running, status="submitted", at=NOW, terminal_code="accepted")
    projection = {
        "work_specs_by_id": {spec.work_id: {"worker_role": spec.worker_role, "spec_hash": spec.spec_hash}},
        "attempts_by_id": {
            submitted.attempt_id: {
                "created_at": submitted.created_at,
                "started_at": submitted.started_at,
                "expires_at": submitted.expires_at,
                "terminal_at": submitted.terminal_at,
                "terminal_code": submitted.terminal_code,
            }
        },
        "work_status_by_id": {submitted.attempt_id: submitted.status},
        "active_attempt_by_work_id": {},
        "terminal_failures_by_attempt_id": {},
        "accepted_submission_refs": ("h_" + "B" * 43,),
    }
    validate_parent_projection(projection)
    with pytest.raises(ValueError, match="submitted_ref"):
        validate_parent_projection({**projection, "accepted_submission_refs": ()})
