"""Pure change-01 skeleton contracts (REG-002/003/004/005)."""

from __future__ import annotations

from dataclasses import fields

import pytest
from pydantic import ValidationError

from deerflow_deep_research.domain.lifecycle import (
    AcceptedHumanResponse,
    DeepResearchControlResult,
    LifecycleAction,
    LifecycleStatus,
    ResponseKind,
    ResultCode,
    serialize_control_result,
)
from deerflow_deep_research.graph.skeleton_state import (
    MAX_CONTROL_RESULT_CHARS,
    BranchResult,
    FakeFixturePlan,
    SkeletonCheckpoint,
    merge_branch_results,
)


def test_control_result_is_closed_bounded_and_full_fake() -> None:
    result = DeepResearchControlResult(
        action=LifecycleAction.START,
        code=ResultCode.SUSPENDED,
        durability="same_process",
        research_id="r_" + "A" * 43,
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


def test_skeleton_checkpoint_has_no_duplicate_pending_authority() -> None:
    names = {item.name for item in fields(SkeletonCheckpoint)}
    assert "pending_hitl" not in names
    assert "suspension_cursor" not in names
    with pytest.raises(TypeError):
        SkeletonCheckpoint(
            research_id="r_" + "A" * 43,
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
