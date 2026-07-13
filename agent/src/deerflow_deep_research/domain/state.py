"""Canonical versioned typed ``ResearchState`` — the sole checkpointed control authority.

@impl REG-006
@impl REG-007
@impl REG-008
@impl REG-009
@impl REG-011

Change 02 replaces the change-01 ``graph/skeleton_state.py`` payload with this module.
Both schemas must never coexist as authorities: the graph builder binds ``ResearchState``
and ``graph/skeleton_state.py`` is removed.

The module freezes, for changes 03/04 and every real node:

- the typed ``ResearchState`` blocks (identity / request / control / planning / work /
  quality / delivery) and the writer/reader/reducer ownership of every field;
- the reducer invariants (terminal monotonicity, generation monotonicity, duplicate-hash
  idempotency, different-hash conflict, ref dedupe, sole-writer ownership);
- the content-ref rule (large content stays out of the checkpoint as path/hash/schema
  version/short-summary under a hard size bound);
- the three-authority boundary (checkpoint control state / validated submission ledger /
  sandbox artifact content) and the ``accepted_submission_refs`` slot that references the
  ledger;
- the versioned schema with fail-closed migration (no silent reset or auto-migration).
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from enum import StrEnum
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

RESEARCH_STATE_SCHEMA_VERSION = 2

# Hard bound on the serialized ResearchState checkpoint. Normal control state, artifact
# refs, branch summaries, HITL correlation, consumed ids, and the logical trace stay far
# under this bound; oversized updates indicate large content that must live as a sandbox
# ContentRef rather than inside the checkpoint.
MAX_CHECKPOINT_STATE_BYTES = 65_536

RESEARCH_ID_RE = re.compile(r"^r_[A-Za-z0-9_-]{43}$")
REQUEST_DIGEST_RE = re.compile(r"^d_[A-Za-z0-9_-]{43}$")
CONTENT_HASH_RE = re.compile(r"^h_[A-Za-z0-9_-]{43}$")
SANDBOX_PATH_RE = re.compile(r"^workspace/deep-research/r_[A-Za-z0-9_-]{43}/.+$")


class WorkStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUBMITTED = "submitted"
    FAILED = "failed"
    TIMED_OUT = "timed_out"
    CANCELLED = "cancelled"


TERMINAL_WORK_STATUSES = frozenset(
    {
        WorkStatus.SUBMITTED,
        WorkStatus.FAILED,
        WorkStatus.TIMED_OUT,
        WorkStatus.CANCELLED,
    }
)


class PhaseStatus(StrEnum):
    IN_PROGRESS = "in_progress"
    WAITING = "waiting"
    TERMINAL = "terminal"


class WriterRole(StrEnum):
    CONTROLLER = "controller"
    GATE = "gate"
    PLANNER = "planner"
    WORKER = "worker"
    REPAIR = "repair"


# Writers permitted to mutate gated authority fields (phase, control status, gate
# feedback, gate attempt/budget counters, accepted submission refs). Worker, planner, and
# repair agents are refused at the reducer.
AUTHORITY_WRITERS = frozenset({WriterRole.CONTROLLER, WriterRole.GATE})

# Fields that only authority writers (controller / gate) may mutate. Any other writer
# raising an update touching one of these is rejected by ``apply_research_update``.
GATED_FIELDS = frozenset(
    {
        "phase",
        "phase_status",
        "waiting_for",
        "terminal_status",
        "latest_gate_feedback",
        "gate_attempts_by_phase",
        "repair_budget_by_phase",
        "accepted_submission_refs",
        "generation",
        "schema_version",
        "research_id",
        "outer_thread_id",
        "route",  # @impl GAK-003 — gate writes route for gated phases
    }
)


@dataclass(frozen=True)
class ContentRef:
    """Bounded reference to large content that lives in the sandbox, not the checkpoint.

    Only the sandbox path, content hash, schema version, and a short summary enter
    ``ResearchState``; the artifact body (web page, PDF, full evidence, report,
    screenshot, large tool output) stays in the sandbox file system.
    """

    sandbox_path: str
    content_hash: str
    schema_version: int = 1
    short_summary: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.sandbox_path, str) or not SANDBOX_PATH_RE.fullmatch(self.sandbox_path):
            raise ValueError("content_ref_path_invalid")
        if not isinstance(self.content_hash, str) or not CONTENT_HASH_RE.fullmatch(self.content_hash):
            raise ValueError("content_ref_hash_invalid")
        if not isinstance(self.schema_version, int) or self.schema_version < 1:
            raise ValueError("content_ref_schema_version_invalid")
        if not isinstance(self.short_summary, str) or len(self.short_summary) > 512:
            raise ValueError("content_ref_summary_invalid")


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
    """Deterministic fake-graph fixture plan, preserved for change-01 resume behavior.

    This is a fake-control slot, explicitly not part of the real ``ResearchState``
    contract; it is removed when the fake graph is replaced by real nodes.
    """

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


# ---------------------------------------------------------------------------
# Reducers
# ---------------------------------------------------------------------------


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


def _coerce_work_status(value: Any) -> WorkStatus:
    return value if isinstance(value, WorkStatus) else WorkStatus(value)


def merge_work_status(
    current: Mapping[str, Any],
    incoming: Mapping[str, Any],
) -> dict[str, WorkStatus]:
    """Reduce ``work_status_by_id`` enforcing terminal monotonicity.

    A terminal status cannot be downgraded by a later ``running`` or stale value, and at
    most one terminal winner holds per work/attempt.
    """
    merged: dict[str, WorkStatus] = {key: _coerce_work_status(value) for key, value in current.items()}
    for work_id, value in incoming.items():
        candidate = _coerce_work_status(value)
        existing = merged.get(work_id)
        if existing in TERMINAL_WORK_STATUSES and candidate is not existing:
            raise ValueError(f"work_status_terminal_conflict:{work_id}")
        merged[work_id] = candidate
    return merged


def merge_accepted_refs(current: Iterable[str], incoming: Iterable[str]) -> tuple[str, ...]:
    """Dedupe-append references into the validated submission ledger."""
    seen: list[str] = [ref for ref in current if isinstance(ref, str)]
    existing = set(seen)
    for ref in incoming:
        if not isinstance(ref, str):
            raise ValueError("accepted_ref_invalid")
        if ref in existing:
            continue
        existing.add(ref)
        seen.append(ref)
    return tuple(seen)


def merge_content_refs(
    current: Iterable[ContentRef | dict[str, Any]],
    incoming: Iterable[ContentRef | dict[str, Any]],
) -> tuple[ContentRef, ...]:
    """Dedupe content refs by ``content_hash``; same hash re-idempotent, different hash
    with the same path is a conflict."""
    refs: list[ContentRef] = [
        item if isinstance(item, ContentRef) else ContentRef(**item) for item in (*current, *incoming)
    ]
    by_path: dict[str, ContentRef] = {}
    by_hash: dict[str, ContentRef] = {}
    deduped: list[ContentRef] = []
    for ref in refs:
        if ref.content_hash in by_hash:
            continue  # same-hash replay is idempotent
        prior_path = by_path.get(ref.sandbox_path)
        if prior_path is not None and prior_path.content_hash != ref.content_hash:
            raise ValueError(f"content_ref_conflict:{ref.sandbox_path}")
        deduped.append(ref)
        by_path[ref.sandbox_path] = ref
        by_hash[ref.content_hash] = ref
    return tuple(deduped)


# ---------------------------------------------------------------------------
# Control projection and ownership-enforcing update
# ---------------------------------------------------------------------------


def _control_field(checkpoint: Any, name: str) -> Any:
    if isinstance(checkpoint, Mapping):
        return checkpoint.get(name)
    return getattr(checkpoint, name, None)


def project_lifecycle_status(checkpoint: Any) -> LifecycleStatus:
    """Derive the wire ``LifecycleStatus`` (REG-004) from the three-field control model.

    ``terminal_status`` wins when set; otherwise a ``waiting`` phase status (or a set
    ``waiting_for``) projects to ``SUSPENDED``. The three-field split is internal to
    ``ResearchState``; the wire control-result envelope is unchanged. Accepts either a
    ``ResearchCheckpoint`` instance or a mapping of its fields.
    """
    terminal = _control_field(checkpoint, "terminal_status")
    if terminal is not None:
        return terminal if isinstance(terminal, LifecycleStatus) else LifecycleStatus(terminal)
    phase_status = _control_field(checkpoint, "phase_status")
    waiting_for = _control_field(checkpoint, "waiting_for")
    if waiting_for is not None or phase_status in (None, PhaseStatus.WAITING):
        return LifecycleStatus.SUSPENDED
    if phase_status == PhaseStatus.TERMINAL:
        # Terminal without a terminal_status is inconsistent; fail closed rather than
        # invent a status.
        raise ValueError("terminal_status_missing")
    return LifecycleStatus.SUSPENDED


def apply_research_update(
    current: Mapping[str, Any],
    incoming: Mapping[str, Any],
    *,
    writer: WriterRole,
) -> dict[str, Any]:
    """Ownership-enforcing reducer for ``ResearchState`` control updates.

    Rejects gated authority fields (phase, control status, gate feedback, gate attempt /
    repair budgets, accepted submission refs, identity) from non-authority writers
    (worker / planner / repair). Enforces ``generation`` monotonic non-decrease. Returns
    the validated partial update for the caller to merge.
    """
    if writer not in AUTHORITY_WRITERS:
        forbidden = sorted(name for name in incoming if name in GATED_FIELDS)
        if forbidden:
            raise ValueError(f"writer_not_authorized:{','.join(forbidden)}")
    if "generation" in incoming:
        prior = current.get("generation")
        if prior is not None and int(incoming["generation"]) < int(prior):
            raise ValueError("generation_decrease")
    return dict(incoming)


# ---------------------------------------------------------------------------
# Frozen validation authority
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ResearchCheckpoint:
    """Frozen validation authority for the typed ``ResearchState`` payload."""

    # identity
    research_id: str
    outer_thread_id: str
    generation: int = 0
    schema_version: int = RESEARCH_STATE_SCHEMA_VERSION
    # request
    start_message_id: str = ""
    request_digest: str = ""
    request_text: str = ""
    # control
    phase: LogicalPhase = LogicalPhase.BOOTSTRAP
    phase_status: PhaseStatus = PhaseStatus.WAITING
    waiting_for: str | None = None
    terminal_status: LifecycleStatus | None = None
    gate_attempts_by_phase: dict[str, int] = field(default_factory=dict)
    repair_budget_by_phase: dict[str, int] = field(default_factory=dict)
    terminal_reason: TerminalReason | None = None
    # planning
    topic_refs: tuple[str, ...] = ()
    active_wave: str | None = None
    pending_work_ids: tuple[str, ...] = ()
    batch_cursor: int = 0
    # work
    work_specs_by_id: dict[str, Any] = field(default_factory=dict)
    work_status_by_id: dict[str, WorkStatus] = field(default_factory=dict)
    accepted_submission_refs: tuple[str, ...] = ()
    wave0_results: tuple[dict[str, str], ...] = ()
    wave1_results: tuple[dict[str, str], ...] = ()
    # quality
    latest_gate_feedback: Any = None
    unresolved_gaps: tuple[str, ...] = ()
    degraded_decisions: tuple[str, ...] = ()
    # delivery
    synthesis_ref: ContentRef | None = None
    decision_brief_ref: ContentRef | None = None
    report_refs: tuple[ContentRef, ...] = ()
    # content refs (sandbox-backed large content)
    content_refs: tuple[ContentRef, ...] = ()
    # fake-control slot (change-01 deterministic resume; removed with the fake graph)
    fixture_plan: FakeFixturePlan = field(default_factory=FakeFixturePlan)
    route: str | None = None
    terminal_fixture_marker: str | None = None
    repair_counts: dict[str, int] = field(default_factory=dict)
    consumed_request_ids: tuple[str, ...] = ()
    consumed_message_ids: tuple[str, ...] = ()
    execution_trace: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.schema_version != RESEARCH_STATE_SCHEMA_VERSION:
            raise ValueError("schema_unsupported")
        if not isinstance(self.research_id, str) or not RESEARCH_ID_RE.fullmatch(self.research_id):
            raise ValueError("research_id_invalid")
        if not isinstance(self.outer_thread_id, str) or not self.outer_thread_id:
            raise ValueError("outer_thread_id_invalid")
        if not 0 <= self.generation <= MAX_FAKE_RERUN_GENERATIONS:
            raise ValueError("generation_invalid")
        if self.start_message_id and len(self.start_message_id) > 256:
            raise ValueError("start_message_id_invalid")
        if self.request_digest and not REQUEST_DIGEST_RE.fullmatch(self.request_digest):
            raise ValueError("request_digest_invalid")
        if self.request_text and len(self.request_text) > MAX_START_REQUEST_CHARS:
            raise ValueError("request_text_invalid")
        if isinstance(self.fixture_plan, dict):
            object.__setattr__(self, "fixture_plan", FakeFixturePlan(**self.fixture_plan))
        if not isinstance(self.fixture_plan, FakeFixturePlan):
            raise TypeError("fixture_plan_invalid")
        if len(self.execution_trace) > MAX_FAKE_TRACE_ENTRIES:
            raise ValueError("trace_too_large")
        if len(self.consumed_request_ids) != len(set(self.consumed_request_ids)):
            raise ValueError("duplicate_consumed_id")
        if len(self.consumed_message_ids) != len(set(self.consumed_message_ids)):
            raise ValueError("duplicate_consumed_id")
        # control-field consistency: terminal_status and terminal_reason require a terminal
        # phase_status; a waiting phase requires waiting_for or a HITL phase.
        object.__setattr__(self, "phase", LogicalPhase(self.phase))
        object.__setattr__(self, "phase_status", PhaseStatus(self.phase_status))
        if self.terminal_status is not None:
            object.__setattr__(self, "terminal_status", LifecycleStatus(self.terminal_status))
            if self.terminal_status not in {
                LifecycleStatus.COMPLETED,
                LifecycleStatus.STOPPED,
                LifecycleStatus.CANCELLED,
                LifecycleStatus.BLOCKED,
            }:
                raise ValueError("terminal_status_not_terminal")
        if self.terminal_reason is not None:
            object.__setattr__(self, "terminal_reason", TerminalReason(self.terminal_reason))
        # work status values must be valid WorkStatus
        coerced_status = {work_id: _coerce_work_status(value) for work_id, value in self.work_status_by_id.items()}
        object.__setattr__(self, "work_status_by_id", coerced_status)


class ResearchState(TypedDict, total=False):
    """LangGraph state schema bound to the research graph (REG-006)."""

    # identity
    research_id: str
    outer_thread_id: str
    generation: int
    schema_version: int
    # request
    start_message_id: str
    request_digest: str
    request_text: str
    # control
    phase: str
    phase_status: str
    waiting_for: str
    terminal_status: str
    gate_attempts_by_phase: dict[str, int]
    repair_budget_by_phase: dict[str, int]
    terminal_reason: str
    # planning
    topic_refs: tuple[str, ...]
    active_wave: str
    pending_work_ids: tuple[str, ...]
    batch_cursor: int
    # work
    work_specs_by_id: dict[str, Any]
    work_status_by_id: Annotated[dict[str, WorkStatus], merge_work_status]
    accepted_submission_refs: Annotated[tuple[str, ...], merge_accepted_refs]
    wave0_results: Annotated[tuple[dict[str, str], ...], merge_branch_results]
    wave1_results: Annotated[tuple[dict[str, str], ...], merge_branch_results]
    # quality
    latest_gate_feedback: Any
    unresolved_gaps: tuple[str, ...]
    degraded_decisions: tuple[str, ...]
    # delivery
    synthesis_ref: ContentRef
    decision_brief_ref: ContentRef
    report_refs: Annotated[tuple[ContentRef, ...], merge_content_refs]
    # content refs
    content_refs: Annotated[tuple[ContentRef, ...], merge_content_refs]
    # fake-control slot
    fixture_plan: dict[str, Any]
    route: str
    terminal_fixture_marker: str
    repair_counts: dict[str, int]
    consumed_request_ids: tuple[str, ...]
    consumed_message_ids: tuple[str, ...]
    execution_trace: Annotated[tuple[str, ...], merge_trace]


# ---------------------------------------------------------------------------
# Ownership table (REG-006): every field declares writer / reader / reducer
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FieldOwnership:
    field: str
    writer: WriterRole
    reader: tuple[WriterRole, ...]
    reducer: str


OWNERSHIP_TABLE: tuple[FieldOwnership, ...] = (
    FieldOwnership("research_id", WriterRole.CONTROLLER, (WriterRole.CONTROLLER, WriterRole.GATE), "controller_init"),
    FieldOwnership("outer_thread_id", WriterRole.CONTROLLER, (WriterRole.CONTROLLER,), "controller_init"),
    FieldOwnership(
        "generation", WriterRole.CONTROLLER, (WriterRole.CONTROLLER, WriterRole.GATE), "apply_research_update"
    ),
    FieldOwnership("schema_version", WriterRole.CONTROLLER, (WriterRole.CONTROLLER,), "controller_init"),
    FieldOwnership("start_message_id", WriterRole.CONTROLLER, (WriterRole.CONTROLLER,), "controller_init"),
    FieldOwnership("request_digest", WriterRole.CONTROLLER, (WriterRole.CONTROLLER,), "controller_init"),
    FieldOwnership("request_text", WriterRole.CONTROLLER, (WriterRole.CONTROLLER,), "controller_init"),
    FieldOwnership("phase", WriterRole.CONTROLLER, (WriterRole.CONTROLLER, WriterRole.GATE), "apply_research_update"),
    FieldOwnership(
        "phase_status", WriterRole.CONTROLLER, (WriterRole.CONTROLLER, WriterRole.GATE), "apply_research_update"
    ),
    FieldOwnership(
        "waiting_for", WriterRole.CONTROLLER, (WriterRole.CONTROLLER, WriterRole.GATE), "apply_research_update"
    ),
    FieldOwnership(
        "terminal_status", WriterRole.CONTROLLER, (WriterRole.CONTROLLER, WriterRole.GATE), "apply_research_update"
    ),
    FieldOwnership("gate_attempts_by_phase", WriterRole.GATE, (WriterRole.GATE,), "apply_research_update"),
    FieldOwnership("repair_budget_by_phase", WriterRole.GATE, (WriterRole.GATE,), "apply_research_update"),
    FieldOwnership(
        "terminal_reason", WriterRole.CONTROLLER, (WriterRole.CONTROLLER, WriterRole.GATE), "apply_research_update"
    ),
    FieldOwnership("topic_refs", WriterRole.PLANNER, (WriterRole.CONTROLLER, WriterRole.WORKER), "last_write_wins"),
    FieldOwnership(
        "active_wave", WriterRole.CONTROLLER, (WriterRole.CONTROLLER, WriterRole.WORKER), "apply_research_update"
    ),
    FieldOwnership(
        "pending_work_ids", WriterRole.PLANNER, (WriterRole.CONTROLLER, WriterRole.WORKER), "last_write_wins"
    ),
    FieldOwnership(
        "batch_cursor", WriterRole.CONTROLLER, (WriterRole.CONTROLLER, WriterRole.WORKER), "apply_research_update"
    ),
    FieldOwnership(
        "work_specs_by_id", WriterRole.CONTROLLER, (WriterRole.CONTROLLER, WriterRole.WORKER), "controller_assign"
    ),
    FieldOwnership(
        "work_status_by_id", WriterRole.CONTROLLER, (WriterRole.CONTROLLER, WriterRole.GATE), "merge_work_status"
    ),
    FieldOwnership(
        "accepted_submission_refs",
        WriterRole.CONTROLLER,
        (WriterRole.CONTROLLER, WriterRole.GATE),
        "merge_accepted_refs",
    ),
    FieldOwnership(
        "wave0_results", WriterRole.WORKER, (WriterRole.CONTROLLER, WriterRole.GATE), "merge_branch_results"
    ),
    FieldOwnership(
        "wave1_results", WriterRole.WORKER, (WriterRole.CONTROLLER, WriterRole.GATE), "merge_branch_results"
    ),
    FieldOwnership(
        "latest_gate_feedback",
        WriterRole.GATE,
        (WriterRole.CONTROLLER, WriterRole.GATE, WriterRole.REPAIR),
        "last_write_wins",
    ),
    FieldOwnership("unresolved_gaps", WriterRole.GATE, (WriterRole.CONTROLLER, WriterRole.GATE), "last_write_wins"),
    FieldOwnership("degraded_decisions", WriterRole.GATE, (WriterRole.CONTROLLER, WriterRole.GATE), "last_write_wins"),
    FieldOwnership("synthesis_ref", WriterRole.CONTROLLER, (WriterRole.CONTROLLER, WriterRole.GATE), "last_write_wins"),
    FieldOwnership("decision_brief_ref", WriterRole.CONTROLLER, (WriterRole.CONTROLLER,), "last_write_wins"),
    FieldOwnership("report_refs", WriterRole.CONTROLLER, (WriterRole.CONTROLLER,), "merge_content_refs"),
    FieldOwnership("content_refs", WriterRole.WORKER, (WriterRole.CONTROLLER, WriterRole.GATE), "merge_content_refs"),
    FieldOwnership("fixture_plan", WriterRole.CONTROLLER, (WriterRole.CONTROLLER,), "controller_init"),
    # @impl GAK-003 — gate writes route for gated phases
    FieldOwnership("route", WriterRole.GATE, (WriterRole.CONTROLLER, WriterRole.GATE), "last_write_wins"),
    FieldOwnership("terminal_fixture_marker", WriterRole.CONTROLLER, (WriterRole.CONTROLLER,), "last_write_wins"),
    # frozen — superseded by gate_attempts_by_phase + repair_budget_by_phase (change 03)  @impl GAK-003
    FieldOwnership("repair_counts", WriterRole.GATE, (WriterRole.CONTROLLER,), "last_write_wins"),
    FieldOwnership("consumed_request_ids", WriterRole.CONTROLLER, (WriterRole.CONTROLLER,), "last_write_wins"),
    FieldOwnership("consumed_message_ids", WriterRole.CONTROLLER, (WriterRole.CONTROLLER,), "last_write_wins"),
    FieldOwnership("execution_trace", WriterRole.CONTROLLER, (WriterRole.CONTROLLER,), "merge_trace"),
)


def ownership_fields() -> frozenset[str]:
    return frozenset(entry.field for entry in OWNERSHIP_TABLE)


def research_state_fields() -> frozenset[str]:
    return frozenset(ResearchState.__annotations__)


# ---------------------------------------------------------------------------
# Serialization and validation
# ---------------------------------------------------------------------------


def serialize_research_state(values: Mapping[str, Any]) -> str:
    payload = json.dumps(values, sort_keys=True, separators=(",", ":"), default=_json_default)
    if len(payload) > MAX_CHECKPOINT_STATE_BYTES:
        raise ValueError("state_too_large")
    return payload


def _json_default(value: Any) -> Any:
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, ContentRef):
        return {
            "sandbox_path": value.sandbox_path,
            "content_hash": value.content_hash,
            "schema_version": value.schema_version,
            "short_summary": value.short_summary,
        }
    raise TypeError(f"not serializable: {type(value).__name__}")


def validate_research_state(values: Mapping[str, Any]) -> ResearchCheckpoint:
    """Validate a serialized ``ResearchState`` payload.

    Enforces the hard checkpoint-size bound first, then constructs the frozen
    ``ResearchCheckpoint`` (which fail-closes on an unsupported ``schema_version``).
    """
    serialize_research_state(values)
    return ResearchCheckpoint(**dict(values))


__all__ = [
    "AUTHORITY_WRITERS",
    "ContentRef",
    "FakeFixturePlan",
    "FieldOwnership",
    "GATED_FIELDS",
    "MAX_CHECKPOINT_STATE_BYTES",
    "MAX_CONTROL_RESULT_CHARS",
    "MAX_FAKE_REPAIR_ATTEMPTS",
    "MAX_FAKE_RERUN_GENERATIONS",
    "MAX_FAKE_TRACE_ENTRIES",
    "MAX_START_REQUEST_CHARS",
    "OWNERSHIP_TABLE",
    "PhaseStatus",
    "RESEARCH_STATE_SCHEMA_VERSION",
    "ResearchCheckpoint",
    "ResearchState",
    "TERMINAL_WORK_STATUSES",
    "WriterRole",
    "WorkStatus",
    "apply_research_update",
    "fixture_plan_to_checkpoint",
    "merge_accepted_refs",
    "merge_branch_results",
    "merge_content_refs",
    "merge_trace",
    "merge_work_status",
    "ownership_fields",
    "project_lifecycle_status",
    "research_state_fields",
    "serialize_research_state",
    "validate_research_state",
]
