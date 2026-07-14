from __future__ import annotations

import pytest

from deerflow_deep_research.domain.state import WriterRole, apply_research_update


@pytest.mark.parametrize("writer", [WriterRole.PLANNER, WriterRole.WORKER, WriterRole.REPAIR, WriterRole.GATE])
@pytest.mark.parametrize(
    "field",
    [
        "next_work_ordinal",
        "work_specs_by_id",
        "attempts_by_id",
        "work_status_by_id",
        "active_attempt_by_work_id",
        "terminal_failures_by_attempt_id",
        "accepted_submission_refs",
    ],
)
def test_agents_and_gate_cannot_write_work_unit_authority(writer: WriterRole, field: str) -> None:
    with pytest.raises(ValueError, match="writer_not_authorized"):
        apply_research_update({}, {field: {} if field.endswith("_id") else ()}, writer=writer)


def test_controller_materializes_but_cannot_publish_acceptance() -> None:
    apply_research_update(
        {},
        {
            "next_work_ordinal": 1,
            "work_specs_by_id": {},
            "attempts_by_id": {},
            "work_status_by_id": {},
            "active_attempt_by_work_id": {},
        },
        writer=WriterRole.CONTROLLER,
    )
    for field in ("terminal_failures_by_attempt_id", "accepted_submission_refs"):
        with pytest.raises(ValueError, match="writer_not_authorized"):
            apply_research_update({}, {field: ()}, writer=WriterRole.CONTROLLER)


def test_submit_has_only_terminal_projection_and_acceptance_fields() -> None:
    apply_research_update(
        {},
        {
            "attempts_by_id": {},
            "work_status_by_id": {},
            "active_attempt_by_work_id": {},
            "terminal_failures_by_attempt_id": {},
            "accepted_submission_refs": (),
        },
        writer=WriterRole.SUBMIT,
    )
    for field in ("next_work_ordinal", "work_specs_by_id", "pending_work_ids", "route"):
        with pytest.raises(ValueError, match="writer_not_authorized"):
            apply_research_update({}, {field: 0}, writer=WriterRole.SUBMIT)


def test_gate_retains_only_route_feedback_budget_and_phase_fields() -> None:
    apply_research_update(
        {},
        {
            "route": "repair",
            "latest_gate_feedback": {},
            "gate_attempts_by_phase": {},
            "repair_budget_by_phase": {},
            "phase": "wave0",
        },
        writer=WriterRole.GATE,
    )
    with pytest.raises(ValueError, match="writer_not_authorized"):
        apply_research_update({}, {"accepted_submission_refs": ()}, writer=WriterRole.GATE)
