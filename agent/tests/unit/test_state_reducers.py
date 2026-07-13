"""Pure change-02 ResearchState reducer invariants (REG-007)."""

from __future__ import annotations

import pytest

from deerflow_deep_research.domain.state import (
    ContentRef,
    WorkStatus,
    WriterRole,
    apply_research_update,
    merge_accepted_refs,
    merge_content_refs,
    merge_work_status,
)

CURRENT = {"research_id": "r_" + "A" * 43, "outer_thread_id": "thread-1", "generation": 1}


def test_terminal_work_status_cannot_be_downgraded() -> None:
    current = {"w1": WorkStatus.SUBMITTED}
    with pytest.raises(ValueError, match="work_status_terminal_conflict"):
        merge_work_status(current, {"w1": WorkStatus.RUNNING})


def test_terminal_work_status_rejects_different_terminal() -> None:
    current = {"w1": WorkStatus.FAILED}
    with pytest.raises(ValueError, match="work_status_terminal_conflict"):
        merge_work_status(current, {"w1": WorkStatus.CANCELLED})


def test_one_terminal_winner_per_work_attempt() -> None:
    merged = merge_work_status({}, {"w1": WorkStatus.SUBMITTED})
    assert merged["w1"] is WorkStatus.SUBMITTED
    # replaying the same terminal value is idempotent
    merged = merge_work_status(merged, {"w1": WorkStatus.SUBMITTED})
    assert merged["w1"] is WorkStatus.SUBMITTED


def test_generation_cannot_decrease() -> None:
    with pytest.raises(ValueError, match="generation_decrease"):
        apply_research_update({"generation": 2}, {"generation": 1}, writer=WriterRole.CONTROLLER)


def test_generation_monotonic_non_decrease_allows_equal_and_increase() -> None:
    assert apply_research_update({"generation": 1}, {"generation": 1}, writer=WriterRole.CONTROLLER)["generation"] == 1
    assert apply_research_update({"generation": 1}, {"generation": 2}, writer=WriterRole.CONTROLLER)["generation"] == 2


def test_same_hash_replay_is_idempotent() -> None:
    ref = ContentRef(
        sandbox_path="workspace/deep-research/r_" + "A" * 43 + "/work/w1/g0-w1-a1/outputs/page.html",
        content_hash="h_" + "B" * 43,
    )
    merged = merge_content_refs((ref,), (ref,))
    assert len(merged) == 1


def test_different_hash_for_same_path_is_a_conflict() -> None:
    path = "workspace/deep-research/r_" + "A" * 43 + "/work/w1/g0-w1-a1/outputs/page.html"
    a = ContentRef(sandbox_path=path, content_hash="h_" + "B" * 43)
    b = ContentRef(sandbox_path=path, content_hash="h_" + "C" * 43)
    with pytest.raises(ValueError, match="content_ref_conflict"):
        merge_content_refs((a,), (b,))


def test_accepted_submission_refs_dedupe_append() -> None:
    merged = merge_accepted_refs(("rec_1", "rec_2"), ("rec_2", "rec_3"))
    assert merged == ("rec_1", "rec_2", "rec_3")


def test_accepted_submission_refs_reject_non_string() -> None:
    with pytest.raises(ValueError, match="accepted_ref_invalid"):
        merge_accepted_refs((), (123,))  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "field, value",
    [
        ("latest_gate_feedback", {"verdict": "repair"}),
        ("gate_attempts_by_phase", {"wave0": 1}),
        ("repair_budget_by_phase", {"wave0": 2}),
        ("phase", "wave0"),
        ("accepted_submission_refs", ("rec_1",)),
        ("terminal_status", "completed"),
    ],
)
def test_workers_cannot_write_gated_authority(field: str, value) -> None:
    with pytest.raises(ValueError, match="writer_not_authorized"):
        apply_research_update(CURRENT, {field: value}, writer=WriterRole.WORKER)
    with pytest.raises(ValueError, match="writer_not_authorized"):
        apply_research_update(CURRENT, {field: value}, writer=WriterRole.REPAIR)


def test_gate_writer_can_write_gate_feedback() -> None:
    update = apply_research_update(
        CURRENT,
        {"latest_gate_feedback": {"verdict": "repair"}},
        writer=WriterRole.GATE,
    )
    assert update["latest_gate_feedback"] == {"verdict": "repair"}


def test_worker_can_write_non_gated_fields() -> None:
    # Workers may contribute branch results and content refs, but not gated authority.
    update = apply_research_update(CURRENT, {"wave0_results": ()}, writer=WriterRole.WORKER)
    assert update["wave0_results"] == ()


def test_accepted_refs_merge_is_order_independent() -> None:
    a = ("rec_1", "rec_2")
    b = ("rec_2", "rec_3")
    left = merge_accepted_refs(merge_accepted_refs((), a), b)
    right = merge_accepted_refs(merge_accepted_refs((), b), a)
    assert set(left) == set(right) == {"rec_1", "rec_2", "rec_3"}


def test_content_refs_merge_is_order_independent() -> None:
    path_a = "workspace/deep-research/r_" + "A" * 43 + "/work/w1/g0-w1-a1/outputs/a.html"
    path_b = "workspace/deep-research/r_" + "A" * 43 + "/work/w1/g0-w1-a1/outputs/b.html"
    a = ContentRef(sandbox_path=path_a, content_hash="h_" + "B" * 43)
    b = ContentRef(sandbox_path=path_b, content_hash="h_" + "C" * 43)
    left = merge_content_refs(merge_content_refs((), (a,)), (b,))
    right = merge_content_refs(merge_content_refs((), (b,)), (a,))
    assert {ref.content_hash for ref in left} == {ref.content_hash for ref in right}


def test_work_status_non_terminal_is_last_write_wins() -> None:
    # Non-terminal transitions are last-write-wins; only terminal statuses are protected
    # from downgrade (REG-007: a terminal cannot be downgraded by a later running/stale
    # value). Work status is therefore intentionally not order-independent.
    merged = merge_work_status({"w1": WorkStatus.RUNNING}, {"w1": WorkStatus.PENDING})
    assert merged["w1"] is WorkStatus.PENDING
