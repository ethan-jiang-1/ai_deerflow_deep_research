"""Typed ResearchState persistence and structure contracts (REG-005, REG-006, REG-011)."""

from __future__ import annotations

import importlib

import pytest

from deerflow_deep_research.domain.lifecycle import LifecycleStatus
from deerflow_deep_research.domain.state import (
    MAX_CHECKPOINT_STATE_BYTES,
    RESEARCH_STATE_SCHEMA_VERSION,
    PhaseStatus,
    ResearchCheckpoint,
    ResearchState,
    project_lifecycle_status,
    serialize_research_state,
    validate_research_state,
)

RESEARCH_ID = "r_" + "A" * 43


def _values(**overrides):
    values: dict = {
        "research_id": RESEARCH_ID,
        "outer_thread_id": "thread-1",
        "generation": 0,
    }
    values.update(overrides)
    return values


def test_research_state_control_fields_round_trip_through_serialization() -> None:
    waiting = _values(phase_status=PhaseStatus.WAITING.value, waiting_for="hitl1")
    restored = validate_research_state(waiting)
    assert restored.schema_version == RESEARCH_STATE_SCHEMA_VERSION
    assert restored.phase_status is PhaseStatus.WAITING
    assert project_lifecycle_status(restored) is LifecycleStatus.SUSPENDED

    terminal = _values(
        phase_status=PhaseStatus.TERMINAL.value,
        terminal_status=LifecycleStatus.COMPLETED.value,
    )
    restored_terminal = validate_research_state(terminal)
    assert restored_terminal.terminal_status is LifecycleStatus.COMPLETED
    assert project_lifecycle_status(restored_terminal) is LifecycleStatus.COMPLETED


def test_research_state_serialization_is_bounded() -> None:
    payload = serialize_research_state(_values())
    assert len(payload) <= MAX_CHECKPOINT_STATE_BYTES


def test_research_checkpoint_rejects_unknown_extra_field() -> None:
    # Raw runtime authority fields (app_config, user_id, handles) cannot enter the
    # checkpoint: the frozen dataclass forbids unknown fields.
    with pytest.raises(TypeError):
        ResearchCheckpoint(**_values(app_config={"db": "secret"}))  # type: ignore[call-arg]
    with pytest.raises(TypeError):
        ResearchCheckpoint(**_values(user_id="alice"))  # type: ignore[call-arg]


def test_skeleton_state_module_is_removed_and_graph_binds_research_state() -> None:
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("deerflow_deep_research.graph.skeleton_state")
    from deerflow_deep_research.graph import builder

    assert builder.ResearchState is ResearchState


def test_research_state_declares_no_legacy_status_field() -> None:
    assert "status" not in ResearchState.__annotations__
