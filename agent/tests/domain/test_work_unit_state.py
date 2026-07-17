"""Work-unit state and one-way attempt lifecycle contracts.

@impl WOU-002
@impl WOU-007
"""

from __future__ import annotations

import json
import typing
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from deerflow_deep_research.domain.failure_codes import FailureCode
from deerflow_deep_research.domain.state import (
    MAX_CHECKPOINT_STATE_BYTES,
    MAX_WORK_UNIT_BLOCK_BYTES,
    ResearchCheckpoint,
    ResearchState,
    WriterRole,
    apply_research_update,
    merge_active_attempts,
    merge_attempt_refs,
    merge_terminal_failures,
    merge_work_spec_refs,
    merge_work_status,
    serialize_research_state,
    serialize_work_unit_block,
    validate_research_state,
)
from deerflow_deep_research.domain.work_units import (
    AttemptRef,
    AttemptStatus,
    AttemptTerminalCode,
    AttemptTerminalUpdate,
    CandidateResult,
    SubmissionValidationCode,
    TerminalFailureSummary,
    WorkSpecRef,
    WorkUnitComponentState,
    compute_failure_detail_hash,
    merge_candidates,
    merge_in_flight,
    merge_terminal_updates,
)

RESEARCH_ID = "r_" + "A" * 43
NOW = datetime(2026, 7, 14, tzinfo=UTC)


def _hash(index: int) -> str:
    return "h_" + f"{index:043d}"


def _work_id(index: int) -> str:
    return f"g0_wave0_w{index:04d}"


def _attempt_id(work_index: int, attempt_index: int) -> str:
    return f"{_work_id(work_index)}_a{attempt_index:02d}"


def _attempt_ref(*, terminal: bool = False, code: AttemptTerminalCode = AttemptTerminalCode.WORKER_FAILED):
    return AttemptRef(
        created_at=NOW,
        started_at=NOW if terminal else None,
        expires_at=None,
        terminal_at=NOW if terminal else None,
        terminal_code=code if terminal else None,
    )


def _base_state(**overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        "research_id": RESEARCH_ID,
        "outer_thread_id": "thread-1",
        "generation": 0,
    }
    values.update(overrides)
    return values


def test_old_v2_checkpoint_defaults_every_new_work_field() -> None:
    checkpoint = validate_research_state(_base_state())
    assert checkpoint.work_specs_by_id == {}
    assert checkpoint.attempts_by_id == {}
    assert checkpoint.work_status_by_id == {}
    assert checkpoint.active_attempt_by_work_id == {}
    assert checkpoint.terminal_failures_by_attempt_id == {}
    assert checkpoint.accepted_submission_refs == ()
    assert checkpoint.next_work_ordinal == 0
    assert checkpoint.next_attempt_ordinal_by_work_id == {}


def test_json_checkpoint_list_channels_normalize_to_plain_tuple_contracts() -> None:
    checkpoint = validate_research_state({**_base_state(), "pending_work_ids": []})
    assert checkpoint.pending_work_ids == ()


def test_pre_change_v2_reader_rejects_new_fields_instead_of_ignoring_them() -> None:
    @dataclass(frozen=True)
    class PreChangeV2Reader:
        research_id: str
        outer_thread_id: str
        generation: int = 0
        schema_version: int = 2

    with pytest.raises(TypeError):
        PreChangeV2Reader(**_base_state(attempts_by_id={}))  # type: ignore[call-arg]


def test_compact_models_are_frozen_extra_forbid_and_dump_to_plain_json() -> None:
    spec = WorkSpecRef(worker_role="fixture_worker", spec_hash=_hash(1))
    with pytest.raises(ValidationError, match="extra_forbidden"):
        WorkSpecRef.model_validate({**spec.model_dump(), "work_id": _work_id(0)})
    with pytest.raises(ValidationError, match="frozen"):
        spec.worker_role = "other"  # type: ignore[misc]

    checkpoint = ResearchCheckpoint(
        **_base_state(
            work_specs_by_id={_work_id(0): spec},
            attempts_by_id={_attempt_id(0, 0): _attempt_ref()},
            work_status_by_id={_attempt_id(0, 0): AttemptStatus.PENDING},
            active_attempt_by_work_id={_work_id(0): _attempt_id(0, 0)},
            next_attempt_ordinal_by_work_id={_work_id(0): 1},
        )
    )
    assert checkpoint.work_specs_by_id[_work_id(0)] == spec.model_dump(mode="json")
    attempt_mapping = checkpoint.attempts_by_id[_attempt_id(0, 0)]
    assert isinstance(attempt_mapping, dict)
    assert attempt_mapping["created_at"].endswith("Z")


def test_compact_values_omit_key_derived_identity_and_classification() -> None:
    assert set(WorkSpecRef.model_fields) == {"worker_role", "spec_hash"}
    assert set(AttemptRef.model_fields) == {
        "created_at",
        "started_at",
        "expires_at",
        "terminal_at",
        "terminal_code",
    }
    assert set(TerminalFailureSummary.model_fields) == {"failure_code", "detail_hash"}
    failure = TerminalFailureSummary(
        failure_code=FailureCode.WORK_FAILED,
        detail_hash=compute_failure_detail_hash(terminal_code=AttemptTerminalCode.WORKER_FAILED),
    )
    assert "classification" not in failure.model_dump()


def test_parent_keyed_reducers_are_idempotent_and_conflict_on_divergence() -> None:
    work_id = _work_id(0)
    attempt_id = _attempt_id(0, 0)
    spec = WorkSpecRef(worker_role="fixture_worker", spec_hash=_hash(1))
    assert merge_work_spec_refs({work_id: spec}, {work_id: spec})[work_id] == spec.model_dump(mode="json")
    with pytest.raises(ValueError, match="work_spec_ref_conflict"):
        merge_work_spec_refs(
            {work_id: spec},
            {work_id: WorkSpecRef(worker_role="fixture_worker", spec_hash=_hash(2))},
        )

    pending = _attempt_ref()
    terminal = _attempt_ref(terminal=True)
    merged_attempt = merge_attempt_refs({attempt_id: pending}, {attempt_id: terminal})[attempt_id]
    assert merged_attempt["terminal_code"] == "worker_failed"
    with pytest.raises(ValueError, match="attempt_terminal_conflict"):
        merge_attempt_refs(
            {attempt_id: terminal},
            {attempt_id: _attempt_ref(terminal=True, code=AttemptTerminalCode.CANDIDATE_CONFLICT)},
        )


def test_status_active_and_failure_maps_are_bounded_complete_projections() -> None:
    attempt_id = _attempt_id(0, 0)
    assert merge_work_status({attempt_id: "failed"}, {attempt_id: "failed"})[attempt_id] is AttemptStatus.FAILED
    with pytest.raises(ValueError, match="work_status_terminal_conflict"):
        merge_work_status({attempt_id: "failed"}, {attempt_id: "running"})

    active = merge_active_attempts({}, {_work_id(0): attempt_id})
    assert active == {_work_id(0): attempt_id}
    failure = TerminalFailureSummary(
        failure_code=FailureCode.WORK_FAILED,
        detail_hash=compute_failure_detail_hash(terminal_code=AttemptTerminalCode.WORKER_FAILED),
    )
    assert merge_terminal_failures({}, {attempt_id: failure}) == {attempt_id: failure.model_dump(mode="json")}
    assert merge_terminal_failures({attempt_id: failure}, {}) == {}


def test_checkpoint_cross_field_projection_fails_closed() -> None:
    work_id = _work_id(0)
    attempt_id = _attempt_id(0, 0)
    common = {
        "work_specs_by_id": {work_id: WorkSpecRef(worker_role="fixture_worker", spec_hash=_hash(1))},
        "attempts_by_id": {attempt_id: _attempt_ref(terminal=True)},
        "work_status_by_id": {attempt_id: AttemptStatus.FAILED},
    }
    with pytest.raises(ValueError, match="active_attempt_status_invalid"):
        ResearchCheckpoint(**_base_state(**common, active_attempt_by_work_id={work_id: attempt_id}))
    with pytest.raises(ValueError, match="terminal_failure_status_invalid"):
        ResearchCheckpoint(
            **_base_state(
                **{**common, "work_status_by_id": {attempt_id: AttemptStatus.SUBMITTED}},
                terminal_failures_by_attempt_id={
                    attempt_id: TerminalFailureSummary(
                        failure_code=FailureCode.WORK_FAILED,
                        detail_hash=compute_failure_detail_hash(terminal_code=AttemptTerminalCode.WORKER_FAILED),
                    )
                },
            )
        )


def test_retry_appends_without_rewriting_terminal_history() -> None:
    old_id = _attempt_id(0, 0)
    retry_id = _attempt_id(0, 1)
    merged = merge_attempt_refs(
        {old_id: _attempt_ref(terminal=True)},
        {retry_id: AttemptRef(created_at=NOW + timedelta(seconds=1))},
    )
    assert set(merged) == {old_id, retry_id}
    assert merged[old_id]["terminal_code"] == "worker_failed"


def test_child_state_has_exactly_six_channels_and_closed_terminal_updates() -> None:
    assert set(typing.get_type_hints(WorkUnitComponentState, include_extras=True)) == {
        "planned_work_ids",
        "pending_work_ids",
        "batch_cursor",
        "in_flight_by_attempt_id",
        "candidates_by_attempt_id",
        "terminal_updates_by_attempt_id",
    }
    update = AttemptTerminalUpdate(
        attempt_id=_attempt_id(0, 0),
        status="failed",
        terminal_at=NOW,
        terminal_code="validation_failed",
        validation_codes=(SubmissionValidationCode.ARTIFACT_MISSING,),
    )
    assert update.validation_codes == (SubmissionValidationCode.ARTIFACT_MISSING,)
    with pytest.raises(ValidationError, match="validation_codes"):
        AttemptTerminalUpdate(
            attempt_id=_attempt_id(0, 0),
            status="failed",
            terminal_at=NOW,
            terminal_code="worker_failed",
            validation_codes=(SubmissionValidationCode.ARTIFACT_MISSING,),
        )


def test_child_keyed_reducers_are_idempotent_and_conflicting() -> None:
    attempt_id = _attempt_id(0, 0)
    assert merge_in_flight({attempt_id: _work_id(0)}, {attempt_id: _work_id(0)}) == {attempt_id: _work_id(0)}
    with pytest.raises(ValueError, match="in_flight_conflict"):
        merge_in_flight({attempt_id: _work_id(0)}, {attempt_id: _work_id(1)})

    candidate = CandidateResult.model_construct(candidate_hash=_hash(1))
    assert merge_candidates({attempt_id: candidate}, {attempt_id: candidate})[attempt_id] is candidate
    other = CandidateResult.model_construct(candidate_hash=_hash(2))
    with pytest.raises(ValueError, match="candidate_conflict"):
        merge_candidates({attempt_id: candidate}, {attempt_id: other})

    terminal = AttemptTerminalUpdate(
        attempt_id=attempt_id,
        status="failed",
        terminal_at=NOW,
        terminal_code="worker_failed",
    )
    assert merge_terminal_updates({attempt_id: terminal}, {attempt_id: terminal})[attempt_id] == terminal
    with pytest.raises(ValueError, match="terminal_update_conflict"):
        merge_terminal_updates(
            {attempt_id: terminal},
            {
                attempt_id: AttemptTerminalUpdate(
                    attempt_id=attempt_id,
                    status="failed",
                    terminal_at=NOW + timedelta(seconds=1),
                    terminal_code="worker_failed",
                )
            },
        )


def test_writer_role_submit_is_closed_and_field_specific() -> None:
    assert WriterRole.SUBMIT.value == "submit"
    with pytest.raises(ValueError, match="writer_not_authorized"):
        apply_research_update({}, {"accepted_submission_refs": (_hash(1),)}, writer=WriterRole.CONTROLLER)
    update = apply_research_update({}, {"accepted_submission_refs": (_hash(1),)}, writer=WriterRole.SUBMIT)
    assert update["accepted_submission_refs"] == (_hash(1),)
    with pytest.raises(ValueError, match="writer_not_authorized"):
        apply_research_update({}, {"phase": "wave1"}, writer=WriterRole.SUBMIT)


def _maximum_work_fields() -> dict[str, object]:
    specs: dict[str, object] = {}
    attempts: dict[str, object] = {}
    statuses: dict[str, object] = {}
    failures: dict[str, object] = {}
    next_attempts: dict[str, int] = {}
    for work_index in range(32):
        work_id = _work_id(work_index)
        specs[work_id] = WorkSpecRef(worker_role="w" * 64, spec_hash=_hash(work_index)).model_dump(mode="json")
        next_attempts[work_id] = 2
        for attempt_index in range(2):
            attempt_id = _attempt_id(work_index, attempt_index)
            code = AttemptTerminalCode.WORKER_FAILED
            attempts[attempt_id] = _attempt_ref(terminal=True, code=code).model_dump(mode="json")
            statuses[attempt_id] = AttemptStatus.FAILED
        selected_id = _attempt_id(work_index, 1)
        failures[selected_id] = TerminalFailureSummary(
            failure_code=FailureCode.WORK_FAILED,
            detail_hash=compute_failure_detail_hash(terminal_code=AttemptTerminalCode.WORKER_FAILED),
        ).model_dump(mode="json")
    return {
        "pending_work_ids": tuple(_work_id(index) for index in range(32)),
        "batch_cursor": 32,
        "next_work_ordinal": 32,
        "next_attempt_ordinal_by_work_id": next_attempts,
        "work_specs_by_id": specs,
        "attempts_by_id": attempts,
        "work_status_by_id": statuses,
        "active_attempt_by_work_id": {_work_id(index): _attempt_id(index, 1) for index in range(32)},
        "terminal_failures_by_attempt_id": failures,
        "accepted_submission_refs": tuple(_hash(index + 100) for index in range(64)),
    }


def test_independent_work_block_and_legal_whole_state_budgets() -> None:
    maximum = _maximum_work_fields()
    encoded = serialize_work_unit_block(maximum)
    assert len(encoded.encode()) <= MAX_WORK_UNIT_BLOCK_BYTES == 40_960

    legal = {
        **maximum,
        "pending_work_ids": (),
        "active_attempt_by_work_id": {},
    }
    whole = serialize_research_state(_base_state(request_text="a" * 16_384, **legal))
    assert len(whole.encode()) <= MAX_CHECKPOINT_STATE_BYTES == 65_536


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("work_specs_by_id", {_work_id(i): WorkSpecRef(worker_role="w", spec_hash=_hash(i)) for i in range(33)}),
        ("accepted_submission_refs", tuple(_hash(i) for i in range(65))),
        ("pending_work_ids", tuple(_work_id(i % 32) for i in range(33))),
    ],
)
def test_parent_collection_bounds_fail_closed(field: str, value: object) -> None:
    with pytest.raises((ValueError, ValidationError), match="bound|too_many|duplicate"):
        validate_research_state(_base_state(**{field: value}))


def test_work_block_serialization_uses_exact_sorted_field_set() -> None:
    values = _maximum_work_fields()
    decoded = json.loads(serialize_work_unit_block(values))
    assert tuple(sorted(decoded)) == tuple(
        sorted(
            {
                "pending_work_ids",
                "batch_cursor",
                "next_work_ordinal",
                "next_attempt_ordinal_by_work_id",
                "work_specs_by_id",
                "attempts_by_id",
                "work_status_by_id",
                "active_attempt_by_work_id",
                "terminal_failures_by_attempt_id",
                "accepted_submission_refs",
            }
        )
    )
    assert set(ResearchState.__annotations__) >= set(decoded)
