"""Progress event projection contract (NOA-005)."""

from __future__ import annotations

from deerflow_deep_research.runtime.events import (
    build_progress_event,
    make_progress_emitter,
)


def test_event_has_stable_fields() -> None:
    event = build_progress_event(
        kind="node_agent",
        ref="r1",
        operation="collect.run_agent",
        status="started",
    )
    assert set(event) == {"kind", "ref", "operation", "status", "detail"}
    assert event["kind"] == "node_agent"
    assert event["ref"] == "r1"
    assert event["status"] == "started"
    assert event["detail"] == ""


def test_event_detail_is_redacted_and_bounded() -> None:
    event = build_progress_event(
        kind="node_agent",
        ref="r1",
        operation="collect.run_agent",
        status="failed",
        detail="token=sk-abcdef123456 at /Users/alice/secret " + "x" * 500,
    )
    assert "sk-abcdef123456" not in event["detail"]
    assert "/Users/alice/secret" not in event["detail"]
    assert len(event["detail"]) <= 256


def test_emitter_collects_and_forwards_to_sink() -> None:
    seen: list[dict] = []
    emitter = make_progress_emitter(sink=seen.append)
    event = build_progress_event(kind="k", ref="r", operation="op", status="s")
    emitter.emit(event)
    assert emitter.collected == [event]
    assert seen == [event]


def test_emitter_degrades_to_noop_without_writer() -> None:
    # With no stream writer bound, the emitter still records for tests and never
    # reaches into a private Gateway event store.
    emitter = make_progress_emitter()
    emitter.emit({"kind": "k", "ref": "r", "operation": "op", "status": "s", "detail": ""})
    assert len(emitter.collected) == 1
