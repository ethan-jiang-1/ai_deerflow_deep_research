"""Deterministic work allocation, lifecycle, retry, and drain policy.

@impl WOU-001
@impl WOU-002
@impl WOU-007
@impl WOU-008
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from deerflow_deep_research.domain.failure_codes import FailureCode
from deerflow_deep_research.domain.gate import Failure
from deerflow_deep_research.domain.lifecycle import LogicalPhase
from deerflow_deep_research.domain.work_units import (
    ATTEMPT_ID_RE,
    WORK_UNIT_GATE_VIEW_KEY,
    Attempt,
    AttemptStatus,
    AttemptTerminalCode,
    SubmissionValidationCode,
    TerminalFailureSummary,
    WorkSpec,
    WorkUnitGateView,
    compute_failure_detail_hash,
    compute_work_spec_hash,
)
from deerflow_deep_research.engine.work_units.ids import allocate_attempt_id, allocate_work_id


@dataclass(frozen=True)
class WorkIntent:
    worker_role: str
    scope: tuple[str, ...]
    result_contract: str
    result_schema_version: int
    required_outputs: tuple[str, ...] = ()


@dataclass(frozen=True)
class ConcurrencyPolicy:
    max_concurrency: int

    def __post_init__(self) -> None:
        if not isinstance(self.max_concurrency, int) or not 1 <= self.max_concurrency <= 16:
            raise ValueError("max_concurrency_invalid")


def materialize_work_spec(
    *,
    research_id: str,
    generation: int,
    phase: LogicalPhase | str,
    work_ordinal: int,
    intent: WorkIntent,
) -> WorkSpec:
    normalized_phase = phase if isinstance(phase, LogicalPhase) else LogicalPhase(phase)
    payload: dict[str, Any] = {
        "schema_version": 1,
        "research_id": research_id,
        "generation": generation,
        "phase": normalized_phase,
        "work_id": allocate_work_id(generation, normalized_phase, work_ordinal),
        "work_ordinal": work_ordinal,
        "worker_role": intent.worker_role,
        "scope": intent.scope,
        "result_contract": intent.result_contract,
        "result_schema_version": intent.result_schema_version,
        "required_outputs": intent.required_outputs,
    }
    payload["spec_hash"] = compute_work_spec_hash(payload)
    return WorkSpec.model_validate(payload)


def allocate_attempt(
    spec: WorkSpec,
    *,
    attempt_ordinal: int,
    created_at: datetime,
    expires_at: datetime | None = None,
) -> Attempt:
    return Attempt(
        schema_version=1,
        research_id=spec.research_id,
        generation=spec.generation,
        phase=spec.phase,
        work_id=spec.work_id,
        attempt_id=allocate_attempt_id(spec.work_id, attempt_ordinal),
        attempt_ordinal=attempt_ordinal,
        spec_hash=spec.spec_hash,
        status=AttemptStatus.PENDING,
        created_at=created_at,
        started_at=None,
        expires_at=expires_at,
        terminal_at=None,
        terminal_code=None,
    )


def transition_attempt(
    attempt: Attempt,
    *,
    status: AttemptStatus | str,
    at: datetime,
    terminal_code: AttemptTerminalCode | str | None = None,
) -> Attempt:
    target = status if isinstance(status, AttemptStatus) else AttemptStatus(status)
    code = (
        terminal_code
        if isinstance(terminal_code, AttemptTerminalCode)
        else (AttemptTerminalCode(terminal_code) if terminal_code is not None else None)
    )
    if target is attempt.status:
        expected_at = attempt.started_at if target is AttemptStatus.RUNNING else attempt.terminal_at
        if target is AttemptStatus.PENDING or expected_at != at or attempt.terminal_code is not code:
            raise ValueError("same_status_detail_conflict")
        return attempt
    if attempt.status in {
        AttemptStatus.SUBMITTED,
        AttemptStatus.FAILED,
        AttemptStatus.TIMED_OUT,
        AttemptStatus.CANCELLED,
    }:
        raise ValueError("terminal_transition_conflict")
    allowed = (
        (attempt.status is AttemptStatus.PENDING and target is AttemptStatus.RUNNING)
        or (attempt.status is AttemptStatus.PENDING and target is AttemptStatus.CANCELLED)
        or (
            attempt.status is AttemptStatus.RUNNING
            and target
            in {AttemptStatus.SUBMITTED, AttemptStatus.FAILED, AttemptStatus.TIMED_OUT, AttemptStatus.CANCELLED}
        )
    )
    if not allowed:
        raise ValueError("attempt_transition_invalid")
    if target is AttemptStatus.RUNNING:
        if code is not None:
            raise ValueError("terminal_code_forbidden")
        payload = attempt.model_dump(mode="python")
        payload.update(status=target, started_at=at)
        return Attempt.model_validate(payload)
    if code is AttemptTerminalCode.EXPIRED and (attempt.expires_at is None or at < attempt.expires_at):
        raise ValueError("expired_boundary_invalid")
    payload = attempt.model_dump(mode="python")
    payload.update(status=target, terminal_at=at, terminal_code=code)
    return Attempt.model_validate(payload)


def retry_allowed(attempt: Attempt, *, accepted: bool) -> bool:
    return not accepted and attempt.status in {AttemptStatus.FAILED, AttemptStatus.TIMED_OUT}


def require_attempt_submittable(
    attempt: Attempt,
    *,
    active_attempt_id: str | None,
    now: datetime,
) -> None:
    if active_attempt_id != attempt.attempt_id:
        raise ValueError("attempt_not_active")
    if attempt.status not in {AttemptStatus.PENDING, AttemptStatus.RUNNING}:
        raise ValueError("attempt_terminal")
    if attempt.expires_at is not None and now >= attempt.expires_at:
        raise ValueError("attempt_expired")


def select_batch(
    planned_work_ids: tuple[str, ...],
    *,
    cursor: int,
    max_concurrency: int,
) -> tuple[tuple[str, ...], int]:
    ConcurrencyPolicy(max_concurrency)
    if tuple(sorted(planned_work_ids)) != planned_work_ids or len(set(planned_work_ids)) != len(planned_work_ids):
        raise ValueError("planned_work_ids_not_canonical")
    if not 0 <= cursor <= len(planned_work_ids):
        raise ValueError("batch_cursor_invalid")
    selected = planned_work_ids[cursor : cursor + max_concurrency]
    return selected, cursor + len(selected)


_VALIDATION_FAILURE_MAP = {
    SubmissionValidationCode.WORK_SPEC_MISSING: FailureCode.MISSING_WORK_SPEC,
    SubmissionValidationCode.IDENTITY_MISMATCH: FailureCode.IDENTITY_MISMATCH,
    SubmissionValidationCode.SPEC_HASH_MISMATCH: FailureCode.IDENTITY_MISMATCH,
    SubmissionValidationCode.SCHEMA_VERSION_UNSUPPORTED: FailureCode.SCHEMA_VERSION_UNSUPPORTED,
    SubmissionValidationCode.CONTENT_HASH_MISMATCH: FailureCode.CONTENT_HASH_MISMATCH,
    SubmissionValidationCode.CANDIDATE_HASH_MISMATCH: FailureCode.CONTENT_HASH_MISMATCH,
    SubmissionValidationCode.CANDIDATE_CONFLICT: FailureCode.WORK_FAILED,
}


def project_terminal_failure(
    *,
    terminal_code: AttemptTerminalCode | str,
    validation_codes: tuple[SubmissionValidationCode, ...] = (),
) -> TerminalFailureSummary:
    code = terminal_code if isinstance(terminal_code, AttemptTerminalCode) else AttemptTerminalCode(terminal_code)
    if code is AttemptTerminalCode.VALIDATION_FAILED:
        if not validation_codes:
            raise ValueError("validation_codes_required")
        failure = _VALIDATION_FAILURE_MAP.get(validation_codes[0], FailureCode.INVALID_OUTPUT_SCHEMA)
    elif code in {AttemptTerminalCode.WORKER_FAILED, AttemptTerminalCode.CANDIDATE_CONFLICT}:
        failure = FailureCode.WORK_FAILED
    elif code in {AttemptTerminalCode.DEADLINE_EXCEEDED, AttemptTerminalCode.EXPIRED}:
        failure = FailureCode.WORK_TIMED_OUT
    elif code in {AttemptTerminalCode.CANCELLED, AttemptTerminalCode.SUPERSEDED}:
        failure = FailureCode.WORK_CANCELLED
    else:
        raise ValueError("accepted_has_no_failure")
    return TerminalFailureSummary(
        failure_code=failure,
        detail_hash=compute_failure_detail_hash(terminal_code=code, validation_codes=validation_codes),
    )


def work_is_drained(pending_work_ids: tuple[str, ...], in_flight_by_attempt_id: dict[str, str]) -> bool:
    return not pending_work_ids and not in_flight_by_attempt_id


def validate_parent_projection(values: dict[str, Any]) -> None:
    specs = values.get("work_specs_by_id", {})
    attempts = values.get("attempts_by_id", {})
    statuses = values.get("work_status_by_id", {})
    active = values.get("active_attempt_by_work_id", {})
    failures = values.get("terminal_failures_by_attempt_id", {})
    refs = values.get("accepted_submission_refs", ())
    if set(statuses) != set(attempts):
        raise ValueError("attempt_status_projection_mismatch")
    submitted = 0
    for attempt_id, raw_status in statuses.items():
        match = ATTEMPT_ID_RE.fullmatch(attempt_id)
        if match is None or match.group("work_id") not in specs:
            raise ValueError("attempt_work_projection_mismatch")
        status = raw_status if isinstance(raw_status, AttemptStatus) else AttemptStatus(raw_status)
        is_active = active.get(match.group("work_id")) == attempt_id
        if status in {AttemptStatus.PENDING, AttemptStatus.RUNNING} and not is_active:
            raise ValueError("active_attempt_projection_mismatch")
        if (
            status in {AttemptStatus.SUBMITTED, AttemptStatus.FAILED, AttemptStatus.TIMED_OUT, AttemptStatus.CANCELLED}
            and is_active
        ):
            raise ValueError("terminal_attempt_still_active")
        if status is AttemptStatus.SUBMITTED:
            submitted += 1
            if attempt_id in failures:
                raise ValueError("submitted_failure_projection_invalid")
        elif (
            status in {AttemptStatus.FAILED, AttemptStatus.TIMED_OUT, AttemptStatus.CANCELLED}
            and attempt_id not in failures
        ):
            raise ValueError("terminal_failure_projection_missing")
    if submitted and len(refs) < submitted:
        raise ValueError("submitted_ref_projection_missing")


class WorkUnitCompletionRule:
    """Pure gate rule over an already validated ephemeral work-unit view."""

    name = "work_unit_completion"
    failure_code = FailureCode.WORK_FAILED

    def evaluate(self, state: dict[str, Any]) -> Failure | None:
        view = state.get(WORK_UNIT_GATE_VIEW_KEY)
        if not isinstance(view, WorkUnitGateView):
            return Failure(FailureCode.WORK_FAILED, self.name, "validated work-unit gate view is missing")
        if not view.drained or set(view.terminal_attempt_by_work_id) != set(view.planned_work_ids):
            return Failure(FailureCode.WORK_FAILED, self.name, "planned work is not structurally drained")
        if view.failure_summaries:
            first = view.failure_summaries[0]
            return Failure(first.failure_code, self.name, ref=first.attempt_id)
        if set(view.accepted_record_by_work_id) != set(view.planned_work_ids):
            return Failure(FailureCode.MISSING_EVIDENCE, self.name, "planned work lacks accepted evidence")
        return None


__all__ = [
    "ConcurrencyPolicy",
    "WorkIntent",
    "WorkUnitCompletionRule",
    "allocate_attempt",
    "materialize_work_spec",
    "project_terminal_failure",
    "require_attempt_submittable",
    "retry_allowed",
    "select_batch",
    "transition_attempt",
    "validate_parent_projection",
    "work_is_drained",
]
