from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from deerflow_deep_research.domain.failure_codes import FailureCode, get_classification
from deerflow_deep_research.domain.state import preview_work_unit_update
from deerflow_deep_research.domain.work_units import (
    WORK_UNIT_GATE_VIEW_KEY,
    SubmissionRecord,
    WorkUnitGateFailure,
    WorkUnitGateView,
    validate_component_gate_view,
    validate_wrapper_gate_view,
)
from deerflow_deep_research.engine.work_units.kernel import WorkUnitCompletionRule

WORK_ID = "g0_wave0_w0000"
ATTEMPT_ID = f"{WORK_ID}_a00"
HASH = "h_" + "B" * 43
NOW = datetime(2026, 7, 14, tzinfo=UTC)


def _failure() -> WorkUnitGateFailure:
    return WorkUnitGateFailure(
        work_id=WORK_ID,
        attempt_id=ATTEMPT_ID,
        failure_code=FailureCode.WORK_FAILED,
        classification=get_classification(FailureCode.WORK_FAILED),
        detail_hash="h_" + "C" * 43,
    )


def _view(*, accepted: bool = True, failures=()) -> WorkUnitGateView:
    return WorkUnitGateView(
        drained=True,
        planned_work_ids=(WORK_ID,),
        terminal_attempt_by_work_id={WORK_ID: ATTEMPT_ID},
        accepted_record_by_work_id={WORK_ID: HASH} if accepted else {},
        failure_summaries=failures,
    )


def _state(*, submitted: bool = True, failure: bool = False) -> dict:
    return {
        "work_specs_by_id": {WORK_ID: {"worker_role": "fixture_worker", "spec_hash": "h_" + "D" * 43}},
        "attempts_by_id": {
            ATTEMPT_ID: {
                "created_at": NOW.isoformat().replace("+00:00", "Z"),
                "started_at": NOW.isoformat().replace("+00:00", "Z"),
                "expires_at": None,
                "terminal_at": NOW.isoformat().replace("+00:00", "Z"),
                "terminal_code": "accepted" if submitted else "worker_failed",
            }
        },
        "work_status_by_id": {ATTEMPT_ID: "submitted" if submitted else "failed"},
        "active_attempt_by_work_id": {},
        "terminal_failures_by_attempt_id": (
            {ATTEMPT_ID: {"failure_code": "work_failed", "detail_hash": "h_" + "C" * 43}} if failure else {}
        ),
        "accepted_submission_refs": (HASH,) if submitted else (),
    }


def test_gate_models_are_exact_frozen_bounded_and_path_free() -> None:
    view = _view()
    assert set(WorkUnitGateView.model_fields) == {
        "drained",
        "planned_work_ids",
        "terminal_attempt_by_work_id",
        "accepted_record_by_work_id",
        "failure_summaries",
    }
    assert WORK_UNIT_GATE_VIEW_KEY == "__work_unit_gate_view__"
    with pytest.raises(ValidationError):
        WorkUnitGateView.model_validate({**view.model_dump(), "artifact_path": "/tmp/secret"})
    with pytest.raises(ValidationError):
        view.drained = False  # type: ignore[misc]


def test_component_validator_detects_swapped_or_unassociated_record_hash() -> None:
    record = SubmissionRecord.model_construct(work_id=WORK_ID, attempt_id=ATTEMPT_ID, record_hash=HASH)
    projection = _state()
    validate_component_gate_view(
        _view(),
        planned_work_ids=(WORK_ID,),
        records_by_work_id={WORK_ID: record},
        parent_projection=projection,
    )
    with pytest.raises(ValueError, match="work_unit_gate_view_inconsistent"):
        validate_component_gate_view(
            _view(),
            planned_work_ids=(WORK_ID,),
            records_by_work_id={WORK_ID: record.model_copy(update={"record_hash": "h_" + "Z" * 43})},
            parent_projection=projection,
        )


def test_wrapper_validator_checks_only_preview_provable_membership() -> None:
    validate_wrapper_gate_view(_view(), _state(), phase="wave0")
    with pytest.raises(ValueError, match="work_unit_gate_view_inconsistent"):
        validate_wrapper_gate_view(_view(), {**_state(), "accepted_submission_refs": ()}, phase="wave0")
    failure_view = _view(accepted=False, failures=(_failure(),))
    validate_wrapper_gate_view(failure_view, _state(submitted=False, failure=True), phase="wave0")


def test_completion_rule_uses_only_validated_view_and_never_masks_failure() -> None:
    rule = WorkUnitCompletionRule()
    assert rule.evaluate({WORK_UNIT_GATE_VIEW_KEY: _view()}) is None
    failure = rule.evaluate({WORK_UNIT_GATE_VIEW_KEY: _view(accepted=False, failures=(_failure(),))})
    assert failure is not None and failure.code is FailureCode.WORK_FAILED
    missing = rule.evaluate(
        {
            WORK_UNIT_GATE_VIEW_KEY: WorkUnitGateView(
                drained=False,
                planned_work_ids=(WORK_ID,),
                terminal_attempt_by_work_id={},
                accepted_record_by_work_id={},
                failure_summaries=(),
            )
        }
    )
    assert missing is not None


def test_preview_applies_only_six_real_reducers_without_mutating_inputs() -> None:
    state = _state(submitted=False, failure=True)
    original = dict(state)
    delta = {"accepted_submission_refs": (HASH,)}
    preview = preview_work_unit_update(state, delta)
    assert preview["accepted_submission_refs"] == (HASH,)
    assert state == original and delta == {"accepted_submission_refs": (HASH,)}
    with pytest.raises(ValueError, match="work_unit_preview_field_forbidden"):
        preview_work_unit_update(state, {"phase": "wave1"})
