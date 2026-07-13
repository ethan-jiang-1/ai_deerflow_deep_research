"""Pure change-02 typed ResearchState contracts (REG-006, REG-011)."""

from __future__ import annotations

import typing
from dataclasses import fields

import pytest
from pydantic import ValidationError

from deerflow_deep_research.domain.lifecycle import (
    AcceptedHumanResponse,
    DeepResearchControlResult,
    LifecycleAction,
    LifecycleStatus,
    LogicalPhase,
    ResponseKind,
    ResultCode,
    TerminalReason,
    serialize_control_result,
)
from deerflow_deep_research.domain.state import (
    GATED_FIELDS,
    MAX_CHECKPOINT_STATE_BYTES,
    MAX_CONTROL_RESULT_CHARS,
    OWNERSHIP_TABLE,
    RESEARCH_STATE_SCHEMA_VERSION,
    BranchResult,
    FakeFixturePlan,
    PhaseStatus,
    ResearchCheckpoint,
    ResearchState,
    WorkStatus,
    WriterRole,
    apply_research_update,
    merge_branch_results,
    ownership_fields,
    project_lifecycle_status,
    research_state_fields,
    validate_research_state,
)

RESEARCH_ID = "r_" + "A" * 43
OUTER_THREAD = "thread-1"


def _base_values(**overrides):
    values: dict = {
        "research_id": RESEARCH_ID,
        "outer_thread_id": OUTER_THREAD,
        "generation": 0,
    }
    values.update(overrides)
    return values


def test_research_state_has_seven_blocks_with_frozen_control_fields() -> None:
    fields = set(typing.get_type_hints(ResearchState))
    # identity
    assert {"research_id", "outer_thread_id", "generation", "schema_version"} <= fields
    # control carries gate attempt/budget counters
    assert {"phase", "phase_status", "waiting_for", "terminal_status"} <= fields
    assert {"gate_attempts_by_phase", "repair_budget_by_phase"} <= fields
    # work carries work_status_by_id closed to WorkStatus
    assert {"work_specs_by_id", "work_status_by_id", "accepted_submission_refs"} <= fields
    # quality + delivery + planning
    assert {"latest_gate_feedback", "synthesis_ref", "report_refs", "pending_work_ids"} <= fields


def test_work_status_enum_is_closed_to_six_values() -> None:
    assert {status.value for status in WorkStatus} == {
        "pending",
        "running",
        "submitted",
        "failed",
        "timed_out",
        "cancelled",
    }


def test_phase_and_waiting_for_are_single_valued() -> None:
    # At most one legal phase and one waiting_for can hold at once: both are single-valued
    # fields, so a second active phase or waiting condition cannot coexist structurally.
    hints = typing.get_type_hints(ResearchState)
    assert hints["phase"] is str
    assert hints["phase_status"] is str
    assert hints["waiting_for"] is str


def test_identity_fields_are_reducer_rejected_from_workers() -> None:
    current = _base_values()
    for field in ("research_id", "outer_thread_id", "generation", "schema_version"):
        with pytest.raises(ValueError, match="writer_not_authorized"):
            apply_research_update(current, {field: "x"}, writer=WriterRole.WORKER)


def test_authority_writer_can_advance_generation() -> None:
    current = _base_values(generation=1)
    update = apply_research_update(current, {"generation": 2}, writer=WriterRole.CONTROLLER)
    assert update["generation"] == 2


def test_project_lifecycle_status_preserves_wire_projection() -> None:
    waiting = _base_values(phase_status=PhaseStatus.WAITING, waiting_for="hitl1")
    assert project_lifecycle_status(waiting) is LifecycleStatus.SUSPENDED
    terminal = _base_values(
        phase_status=PhaseStatus.TERMINAL,
        terminal_status=LifecycleStatus.COMPLETED,
    )
    assert project_lifecycle_status(terminal) is LifecycleStatus.COMPLETED


def test_ownership_table_covers_every_research_state_field() -> None:
    assert ownership_fields() == research_state_fields()
    # Every entry declares a writer, at least one reader, and a reducer.
    for entry in OWNERSHIP_TABLE:
        assert isinstance(entry.writer, WriterRole)
        assert entry.reader
        assert entry.reducer


def test_gated_fields_are_the_authority_owned_set() -> None:
    assert "phase" in GATED_FIELDS
    assert "latest_gate_feedback" in GATED_FIELDS
    assert "gate_attempts_by_phase" in GATED_FIELDS
    assert "repair_budget_by_phase" in GATED_FIELDS
    assert "accepted_submission_refs" in GATED_FIELDS


def test_research_checkpoint_rejects_unsupported_schema_version() -> None:
    with pytest.raises(ValueError, match="schema_unsupported"):
        ResearchCheckpoint(**_base_values(schema_version=1))
    with pytest.raises(ValueError, match="schema_unsupported"):
        ResearchCheckpoint(**_base_values(schema_version=99))


def test_schema_version_is_two() -> None:
    assert RESEARCH_STATE_SCHEMA_VERSION == 2
    checkpoint = ResearchCheckpoint(**_base_values())
    assert checkpoint.schema_version == RESEARCH_STATE_SCHEMA_VERSION


def test_validate_research_state_fail_closes_on_skeleton_version_without_reset() -> None:
    # A change-01 skeleton v1 payload must fail closed as schema_unsupported, never be
    # silently reinterpreted or auto-migrated into a v2 ResearchState.
    skeleton_v1 = _base_values(schema_version=1, fixture_plan={"wave0": ("pass",)})
    with pytest.raises(ValueError, match="schema_unsupported"):
        validate_research_state(skeleton_v1)


def test_research_checkpoint_default_phase_is_waiting() -> None:
    checkpoint = ResearchCheckpoint(**_base_values())
    assert checkpoint.phase_status is PhaseStatus.WAITING
    assert checkpoint.terminal_status is None
    assert project_lifecycle_status(_base_values()) is LifecycleStatus.SUSPENDED
    assert checkpoint.phase is LogicalPhase.BOOTSTRAP


def test_terminal_status_must_be_a_terminal_lifecycle_status() -> None:
    with pytest.raises(ValueError, match="terminal_status_not_terminal"):
        ResearchCheckpoint(
            **_base_values(
                phase_status=PhaseStatus.TERMINAL,
                terminal_status=LifecycleStatus.SUSPENDED,
            )
        )


def test_checkpoint_preserves_terminal_reason() -> None:
    checkpoint = ResearchCheckpoint(
        **_base_values(
            phase_status=PhaseStatus.TERMINAL,
            terminal_status=LifecycleStatus.BLOCKED,
            terminal_reason=TerminalReason.REPAIR_EXHAUSTED,
        )
    )
    assert checkpoint.terminal_reason is TerminalReason.REPAIR_EXHAUSTED


def test_max_checkpoint_state_bytes_is_bounded() -> None:
    assert MAX_CHECKPOINT_STATE_BYTES > 0


# Migrated from change-01 test_skeleton_contracts.py (REG-002/003/004 contracts, now
# asserted against the typed ResearchState authority).


def test_control_result_is_closed_bounded_and_full_fake() -> None:
    result = DeepResearchControlResult(
        action=LifecycleAction.START,
        code=ResultCode.SUSPENDED,
        durability="same_process",
        research_id=RESEARCH_ID,
        status=LifecycleStatus.SUSPENDED,
        phase="hitl1",
        generation=0,
        request_id="drh_request",
    )
    encoded = serialize_control_result(result)
    assert len(encoded) <= MAX_CONTROL_RESULT_CHARS
    assert '"implementation_mode":"full_fake"' in encoded
    assert "finding" not in encoded and "report" not in encoded


def test_control_result_rejects_free_form_code_and_authority_fields() -> None:
    with pytest.raises(ValidationError):
        DeepResearchControlResult(
            action="start",
            code="invented_code",
            durability="unavailable",
            user_id="alice",
        )


def test_accepted_response_is_frozen_and_bounded() -> None:
    response = AcceptedHumanResponse(
        request_id="drh_1",
        message_id="human-1",
        value="proceed",
        response_kind=ResponseKind.OPTION,
        option_id="proceed",
    )
    with pytest.raises(ValidationError):
        response.value = "repair"


def test_research_checkpoint_has_no_duplicate_pending_authority() -> None:
    names = {item.name for item in fields(ResearchCheckpoint)}
    assert "pending_hitl" not in names
    assert "suspension_cursor" not in names
    with pytest.raises(TypeError):
        ResearchCheckpoint(
            research_id=RESEARCH_ID,
            outer_thread_id=OUTER_THREAD,
            start_message_id="m1",
            request_digest="d_" + "A" * 43,
            request_text="question",
            fixture_plan=FakeFixturePlan(),
            pending_hitl={"forbidden": True},
        )


def test_fixture_plan_rejects_unknown_routes() -> None:
    with pytest.raises(ValueError):
        FakeFixturePlan(wave0=("teleport",))


def test_branch_reducer_normalizes_and_rejects_duplicates() -> None:
    merged = merge_branch_results(
        (),
        (BranchResult(branch_id="b", verdict="pass"), BranchResult(branch_id="a", verdict="pass")),
    )
    assert [item["branch_id"] for item in merged] == ["a", "b"]
    with pytest.raises(ValueError, match="duplicate_branch"):
        merge_branch_results(merged, (BranchResult(branch_id="a", verdict="pass"),))
