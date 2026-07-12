"""Temporary checkpoint state for the change-01 fake graph.

@impl REG-002
@impl REG-003
@impl REG-004
@impl REG-005

Change 02 must migrate the graph builder to ``domain/state.py`` and remove this
module; both schemas must never coexist as authorities.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Annotated, Any, TypedDict

from deerflow_deep_research.domain.lifecycle import (
    MAX_CONTROL_RESULT_CHARS,
    MAX_FAKE_REPAIR_ATTEMPTS,
    MAX_FAKE_RERUN_GENERATIONS,
    MAX_FAKE_TRACE_ENTRIES,
    MAX_START_REQUEST_CHARS,
    BootstrapRoute,
    BranchResult,
    FinalVerdict,
    GateVerdict,
    Hitl2Decision,
    LifecycleStatus,
    LogicalPhase,
    ReadinessVerdict,
    SynthesisVerdict,
    TerminalReason,
)

SKELETON_SCHEMA_VERSION = 1


def merge_branch_results(
    current: Iterable[BranchResult | dict[str, Any]],
    incoming: Iterable[BranchResult | dict[str, Any]],
) -> tuple[dict[str, str], ...]:
    values = [item if isinstance(item, BranchResult) else BranchResult(**item) for item in (*current, *incoming)]
    ids = [item.branch_id for item in values]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate_branch")
    return tuple(item.model_dump(mode="json") for item in sorted(values, key=lambda item: item.branch_id))


def merge_trace(current: Iterable[str], incoming: Iterable[str]) -> tuple[str, ...]:
    values = (*current, *incoming)
    if len(values) > MAX_FAKE_TRACE_ENTRIES:
        raise ValueError("trace_too_large")
    return tuple(values)


def _enum_sequence(values: Iterable[Any], enum_type: type, field_name: str) -> tuple[Any, ...]:
    try:
        converted = tuple(value if isinstance(value, enum_type) else enum_type(value) for value in values)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"invalid fixture route for {field_name}") from exc
    if not converted or len(converted) > MAX_FAKE_TRACE_ENTRIES:
        raise ValueError(f"invalid fixture route sequence for {field_name}")
    return converted


@dataclass(frozen=True)
class FakeFixturePlan:
    bootstrap: tuple[BootstrapRoute, ...] = (BootstrapRoute.NEEDS_INPUT,)
    wave0: tuple[GateVerdict, ...] = (GateVerdict.PASS,)
    wave1: tuple[GateVerdict, ...] = (GateVerdict.PASS,)
    wave2_synthesis: tuple[SynthesisVerdict, ...] = (SynthesisVerdict.PASS,)
    hitl2: tuple[Hitl2Decision, ...] = (Hitl2Decision.PROCEED,)
    readiness: tuple[ReadinessVerdict, ...] = (ReadinessVerdict.PASS,)
    final_delivery: tuple[FinalVerdict, ...] = (FinalVerdict.PASS,)

    def __post_init__(self) -> None:
        object.__setattr__(self, "bootstrap", _enum_sequence(self.bootstrap, BootstrapRoute, "bootstrap"))
        object.__setattr__(self, "wave0", _enum_sequence(self.wave0, GateVerdict, "wave0"))
        object.__setattr__(self, "wave1", _enum_sequence(self.wave1, GateVerdict, "wave1"))
        object.__setattr__(
            self,
            "wave2_synthesis",
            _enum_sequence(self.wave2_synthesis, SynthesisVerdict, "wave2_synthesis"),
        )
        object.__setattr__(self, "hitl2", _enum_sequence(self.hitl2, Hitl2Decision, "hitl2"))
        object.__setattr__(self, "readiness", _enum_sequence(self.readiness, ReadinessVerdict, "readiness"))
        object.__setattr__(self, "final_delivery", _enum_sequence(self.final_delivery, FinalVerdict, "final_delivery"))
        if self.wave0[-1] is not GateVerdict.PASS or self.wave1[-1] is not GateVerdict.PASS:
            raise ValueError("wave fixture must converge to pass")
        if self.wave2_synthesis[-1] is not SynthesisVerdict.PASS:
            raise ValueError("synthesis fixture must converge to pass")
        if self.readiness[-1] is not ReadinessVerdict.PASS:
            raise ValueError("readiness fixture must converge to pass")
        if self.final_delivery[-1] is not FinalVerdict.PASS:
            raise ValueError("final fixture must converge to pass")


def fixture_plan_to_checkpoint(plan: FakeFixturePlan) -> dict[str, tuple[str, ...]]:
    return {
        "bootstrap": tuple(value.value for value in plan.bootstrap),
        "wave0": tuple(value.value for value in plan.wave0),
        "wave1": tuple(value.value for value in plan.wave1),
        "wave2_synthesis": tuple(value.value for value in plan.wave2_synthesis),
        "hitl2": tuple(value.value for value in plan.hitl2),
        "readiness": tuple(value.value for value in plan.readiness),
        "final_delivery": tuple(value.value for value in plan.final_delivery),
    }


@dataclass(frozen=True)
class SkeletonCheckpoint:
    research_id: str
    start_message_id: str
    request_digest: str
    request_text: str
    fixture_plan: FakeFixturePlan
    schema_version: int = SKELETON_SCHEMA_VERSION
    status: LifecycleStatus = LifecycleStatus.SUSPENDED
    phase: LogicalPhase = LogicalPhase.BOOTSTRAP
    generation: int = 0
    repair_counts: dict[str, int] = field(default_factory=dict)
    wave0_results: tuple[dict[str, str], ...] = ()
    wave1_results: tuple[dict[str, str], ...] = ()
    consumed_request_ids: tuple[str, ...] = ()
    consumed_message_ids: tuple[str, ...] = ()
    terminal_reason: TerminalReason | None = None
    route: str | None = None
    terminal_fixture_marker: str | None = None
    execution_trace: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.schema_version != SKELETON_SCHEMA_VERSION:
            raise ValueError("schema_unsupported")
        if not re.fullmatch(r"r_[A-Za-z0-9_-]{43}", self.research_id):
            raise ValueError("research_id_invalid")
        if not self.start_message_id or len(self.start_message_id) > 256:
            raise ValueError("start_message_id_invalid")
        if not re.fullmatch(r"d_[A-Za-z0-9_-]{43}", self.request_digest):
            raise ValueError("request_digest_invalid")
        if not self.request_text or len(self.request_text) > MAX_START_REQUEST_CHARS:
            raise ValueError("request_text_invalid")
        if isinstance(self.fixture_plan, dict):
            object.__setattr__(self, "fixture_plan", FakeFixturePlan(**self.fixture_plan))
        if not isinstance(self.fixture_plan, FakeFixturePlan):
            raise TypeError("fixture_plan_invalid")
        if not 0 <= self.generation <= MAX_FAKE_RERUN_GENERATIONS:
            raise ValueError("generation_invalid")
        if len(self.execution_trace) > MAX_FAKE_TRACE_ENTRIES:
            raise ValueError("trace_too_large")
        if len(self.consumed_request_ids) != len(set(self.consumed_request_ids)):
            raise ValueError("duplicate_consumed_id")
        if len(self.consumed_message_ids) != len(set(self.consumed_message_ids)):
            raise ValueError("duplicate_consumed_id")
        object.__setattr__(self, "status", LifecycleStatus(self.status))
        object.__setattr__(self, "phase", LogicalPhase(self.phase))
        if self.terminal_reason is not None:
            object.__setattr__(self, "terminal_reason", TerminalReason(self.terminal_reason))


class SkeletonState(TypedDict, total=False):
    schema_version: int
    research_id: str
    start_message_id: str
    request_digest: str
    request_text: str
    fixture_plan: dict[str, Any]
    status: str
    phase: str
    generation: int
    repair_counts: dict[str, int]
    wave0_results: Annotated[tuple[dict[str, str], ...], merge_branch_results]
    wave1_results: Annotated[tuple[dict[str, str], ...], merge_branch_results]
    consumed_request_ids: tuple[str, ...]
    consumed_message_ids: tuple[str, ...]
    terminal_reason: str | None
    route: str
    terminal_fixture_marker: str
    execution_trace: Annotated[tuple[str, ...], merge_trace]


def validate_skeleton_state(values: dict[str, Any]) -> SkeletonCheckpoint:
    return SkeletonCheckpoint(**values)


__all__ = [
    "BranchResult",
    "FakeFixturePlan",
    "MAX_CONTROL_RESULT_CHARS",
    "MAX_FAKE_REPAIR_ATTEMPTS",
    "MAX_FAKE_RERUN_GENERATIONS",
    "MAX_FAKE_TRACE_ENTRIES",
    "MAX_START_REQUEST_CHARS",
    "SKELETON_SCHEMA_VERSION",
    "SkeletonCheckpoint",
    "SkeletonState",
    "merge_branch_results",
    "merge_trace",
    "fixture_plan_to_checkpoint",
    "validate_skeleton_state",
]
