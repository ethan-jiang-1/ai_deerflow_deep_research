"""Reusable bounded work-unit Send/fan-in/submit/drain component.

@impl WOU-002
@impl WOU-005
@impl WOU-008
"""

from __future__ import annotations

import base64
import hashlib
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from langgraph.graph import END, START, StateGraph
from langgraph.types import Overwrite, Send

from deerflow_deep_research.domain.bundle import first_work_spec_path, output_path, result_path, work_spec_path
from deerflow_deep_research.domain.invocation import WorkUnitControllerDependencies
from deerflow_deep_research.domain.lifecycle import WorkUnitStorageReason
from deerflow_deep_research.domain.node_spec import PolicyRef
from deerflow_deep_research.domain.state import WORK_UNIT_GATE_PREVIEW_FIELDS, preview_work_unit_update
from deerflow_deep_research.domain.work_units import (
    ATTEMPT_ID_RE,
    VALIDATOR_V1_PASSED_CHECKS,
    Attempt,
    AttemptRef,
    AttemptStatus,
    AttemptTerminalUpdate,
    CandidateResult,
    FixtureResultDocument,
    OutputRef,
    SubmissionRecord,
    WorkSpec,
    WorkSpecRef,
    WorkUnitComponentState,
    WorkUnitGateView,
    canonical_json_bytes,
    compute_candidate_hash,
    validate_component_gate_view,
)
from deerflow_deep_research.engine.work_units.kernel import (
    ConcurrencyPolicy,
    WorkIntent,
    allocate_attempt,
    materialize_work_spec,
    require_attempt_submittable,
    retry_allowed,
    select_batch,
)
from deerflow_deep_research.engine.work_units.validation import (
    build_validation_plan,
    validate_submission_candidate,
)

Worker = Callable[[WorkSpec, Attempt], Awaitable[CandidateResult]]
Submit = Callable[[WorkSpec, Attempt, CandidateResult], Awaitable[SubmissionRecord]]
Reconcile = Callable[[WorkSpec, Attempt], Awaitable[SubmissionRecord | None]]


@dataclass(frozen=True)
class WorkUnitComponentConfig:
    research_id: str
    generation: int
    phase: str
    intents: tuple[WorkIntent, ...]
    max_concurrency: int
    clock: Callable[[], datetime]
    start_work_ordinal: int = 0
    fault_hook: Callable[[str], None] | None = None
    materialized_specs: tuple[WorkSpec, ...] = ()
    replay_attempts_by_work_id: Mapping[str, Attempt] = field(default_factory=dict)

    def __post_init__(self) -> None:
        ConcurrencyPolicy(self.max_concurrency)
        if self.intents and self.materialized_specs:
            raise ValueError("work_source_conflict")
        count = len(self.intents) or len(self.materialized_specs)
        if not 1 <= count <= 32:
            raise ValueError("work_intents_bound_invalid")
        if self.intents and not 0 <= self.start_work_ordinal <= 9999 - len(self.intents) + 1:
            raise ValueError("start_work_ordinal_invalid")
        spec_work_ids = {spec.work_id for spec in self.materialized_specs}
        if set(self.replay_attempts_by_work_id) - spec_work_ids:
            raise ValueError("replay_attempt_spec_missing")


@dataclass(frozen=True)
class WorkUnitComponentResult:
    parent_update: dict[str, Any]
    gate_view: WorkUnitGateView


def _content_hash(data: bytes) -> str:
    digest = hashlib.sha256(data).digest()
    return "h_" + base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def _candidate_from_record(record: SubmissionRecord) -> CandidateResult:
    return CandidateResult.model_validate(
        {field_name: getattr(record, field_name) for field_name in CandidateResult.model_fields}
    )


async def _validate_accepted_record_artifacts(
    controller: WorkUnitControllerDependencies,
    record: SubmissionRecord,
    accepted_records: tuple[SubmissionRecord, ...],
) -> WorkSpec:
    store = controller.store
    spec_ref = work_spec_path(record.research_id, record.work_id, record.attempt_id)
    try:
        spec_bytes = await store.read_canonical_bytes(spec_ref, max_bytes=16 * 1024)
        spec = WorkSpec.model_validate_json(spec_bytes)
    except (FileNotFoundError, ValueError) as exc:
        raise store.infrastructure_error(WorkUnitStorageReason.ACCEPTED_ARTIFACT_DIVERGED) from exc
    if canonical_json_bytes(spec) != spec_bytes or spec.scope != record.scope:
        raise store.infrastructure_error(WorkUnitStorageReason.ACCEPTED_ARTIFACT_DIVERGED)
    candidate = _candidate_from_record(record)
    attempt = Attempt(
        schema_version=1,
        research_id=record.research_id,
        generation=record.generation,
        phase=record.phase,
        work_id=record.work_id,
        attempt_id=record.attempt_id,
        attempt_ordinal=int(record.attempt_id.rsplit("_a", 1)[1]),
        spec_hash=record.spec_hash,
        status="pending",
        created_at=record.submitted_at,
        started_at=None,
        expires_at=None,
        terminal_at=None,
        terminal_code=None,
    )
    plan = build_validation_plan(spec, attempt, candidate)
    artifacts = await store.read_validation_plan(plan)
    codes = validate_submission_candidate(
        spec,
        attempt,
        candidate,
        artifacts,
        accepted_records=accepted_records,
    )
    if codes:
        raise store.infrastructure_error(WorkUnitStorageReason.ACCEPTED_ARTIFACT_DIVERGED)
    return spec


async def reconcile_parent_ledger_authority(
    parent_state: Mapping[str, Any],
    controller: WorkUnitControllerDependencies,
) -> tuple[SubmissionRecord, ...]:
    """Validate checkpoint-to-ledger authority before any worker dispatch."""

    store = controller.store
    records = await store.load_records()
    by_hash = {record.record_hash: record for record in records}
    by_attempt = {record.attempt_id: record for record in records}
    accepted_refs = tuple(parent_state.get("accepted_submission_refs", ()))
    if any(record_hash not in by_hash for record_hash in accepted_refs):
        raise store.infrastructure_error(WorkUnitStorageReason.LEDGER_CORRUPT)
    statuses = parent_state.get("work_status_by_id", {})
    for attempt_id, raw_status in statuses.items():
        status = raw_status.value if hasattr(raw_status, "value") else str(raw_status)
        if status != "submitted":
            continue
        record = by_attempt.get(attempt_id)
        if record is None:
            raise store.infrastructure_error(WorkUnitStorageReason.LEDGER_CORRUPT)
    for record_hash in accepted_refs:
        await _validate_accepted_record_artifacts(controller, by_hash[record_hash], records)
    return records


async def submit_candidate_if_active(
    controller: WorkUnitControllerDependencies,
    *,
    spec: WorkSpec,
    attempt: Attempt,
    candidate: CandidateResult,
    active_attempt_id: str | None,
    now: datetime,
) -> SubmissionRecord:
    """Validate lifecycle before any ledger or artifact-store access."""

    require_attempt_submittable(
        attempt,
        active_attempt_id=active_attempt_id,
        now=now,
    )
    store = controller.store
    accepted_records = await store.load_records()
    plan = build_validation_plan(spec, attempt, candidate)
    artifacts = await store.read_validation_plan(plan)
    codes = validate_submission_candidate(
        spec,
        attempt,
        candidate,
        artifacts,
        accepted_records=accepted_records,
    )
    if codes:
        raise ValueError("submission_validation_failed:" + ",".join(code.value for code in codes))
    receipt = await store.commit_candidate(
        candidate,
        scope=spec.scope,
        validator_version=1,
        passed_checks=VALIDATOR_V1_PASSED_CHECKS,
    )
    if not isinstance(receipt.record, SubmissionRecord):
        raise TypeError("submission_record_required")
    return receipt.record


async def _rehydrate_active_replay(
    parent_state: Mapping[str, Any],
    controller: WorkUnitControllerDependencies,
    *,
    logical_name: str,
    generation: int,
) -> tuple[tuple[WorkSpec, ...], dict[str, Attempt]]:
    active = parent_state.get("active_attempt_by_work_id", {})
    current_prefix = f"g{generation}_{logical_name}_w"
    work_ids = tuple(sorted(work_id for work_id in active if work_id.startswith(current_prefix)))
    if not work_ids:
        return (), {}

    specs_by_id: dict[str, WorkSpec] = {}
    attempts_by_work_id: dict[str, Attempt] = {}
    compact_specs = parent_state.get("work_specs_by_id", {})
    compact_attempts = parent_state.get("attempts_by_id", {})
    statuses = parent_state.get("work_status_by_id", {})
    for work_id in work_ids:
        spec = await _rehydrate_canonical_spec(
            parent_state,
            controller,
            work_id=work_id,
            logical_name=logical_name,
            generation=generation,
            compact_specs=compact_specs,
        )

        attempt_id = active[work_id]
        match = ATTEMPT_ID_RE.fullmatch(attempt_id)
        if match is None or match.group("work_id") != work_id:
            raise ValueError("active_attempt_replay_invalid")
        try:
            compact_attempt = AttemptRef.model_validate(compact_attempts[attempt_id])
            status = AttemptStatus(statuses[attempt_id])
        except (KeyError, ValueError) as exc:
            raise ValueError("active_attempt_replay_invalid") from exc
        if status not in {AttemptStatus.PENDING, AttemptStatus.RUNNING}:
            raise ValueError("active_attempt_replay_invalid")
        attempt = Attempt(
            schema_version=1,
            research_id=spec.research_id,
            generation=spec.generation,
            phase=spec.phase,
            work_id=work_id,
            attempt_id=attempt_id,
            attempt_ordinal=int(match.group("attempt_ordinal")),
            spec_hash=spec.spec_hash,
            status=status,
            created_at=compact_attempt.created_at,
            started_at=compact_attempt.started_at,
            expires_at=compact_attempt.expires_at,
            terminal_at=compact_attempt.terminal_at,
            terminal_code=compact_attempt.terminal_code,
        )
        specs_by_id[work_id] = spec
        attempts_by_work_id[work_id] = attempt
    return tuple(specs_by_id.values()), attempts_by_work_id


async def _rehydrate_canonical_spec(
    parent_state: Mapping[str, Any],
    controller: WorkUnitControllerDependencies,
    *,
    work_id: str,
    logical_name: str,
    generation: int,
    compact_specs: Mapping[str, Any],
) -> WorkSpec:
    try:
        compact_spec = WorkSpecRef.model_validate(compact_specs[work_id])
        spec_bytes = await controller.store.read_canonical_bytes(
            first_work_spec_path(str(parent_state.get("research_id", "")), work_id),
            max_bytes=16 * 1024,
        )
        spec = WorkSpec.model_validate_json(spec_bytes)
    except (KeyError, FileNotFoundError, ValueError) as exc:
        raise ValueError("work_spec_replay_invalid") from exc
    if (
        canonical_json_bytes(spec) != spec_bytes
        or spec.work_id != work_id
        or spec.generation != generation
        or spec.phase.value != logical_name
        or spec.worker_role != compact_spec.worker_role
        or spec.spec_hash != compact_spec.spec_hash
    ):
        raise ValueError("work_spec_replay_invalid")
    return spec


async def _allocate_terminal_retries(
    parent_state: Mapping[str, Any],
    controller: WorkUnitControllerDependencies,
    *,
    logical_name: str,
    generation: int,
    accepted_work_ids: set[str],
    clock: Callable[[], datetime],
) -> tuple[tuple[WorkSpec, ...], dict[str, Attempt]]:
    active_work_ids = set(parent_state.get("active_attempt_by_work_id", {}))
    compact_specs = parent_state.get("work_specs_by_id", {})
    compact_attempts = parent_state.get("attempts_by_id", {})
    statuses = parent_state.get("work_status_by_id", {})
    next_ordinals = parent_state.get("next_attempt_ordinal_by_work_id", {})
    current_prefix = f"g{generation}_{logical_name}_w"
    retry_specs: dict[str, WorkSpec] = {}
    retry_attempts: dict[str, Attempt] = {}

    for work_id in sorted(compact_specs):
        if not work_id.startswith(current_prefix) or work_id in active_work_ids or work_id in accepted_work_ids:
            continue
        terminal_attempts: list[tuple[int, str, AttemptStatus]] = []
        for attempt_id, raw_status in statuses.items():
            match = ATTEMPT_ID_RE.fullmatch(attempt_id)
            if match is None or match.group("work_id") != work_id:
                continue
            status = AttemptStatus(raw_status)
            if status in {
                AttemptStatus.SUBMITTED,
                AttemptStatus.FAILED,
                AttemptStatus.TIMED_OUT,
                AttemptStatus.CANCELLED,
            }:
                terminal_attempts.append((int(match.group("attempt_ordinal")), attempt_id, status))
        if not terminal_attempts:
            continue
        latest_ordinal, latest_attempt_id, latest_status = max(terminal_attempts)
        compact_attempt = AttemptRef.model_validate(compact_attempts[latest_attempt_id])
        spec = await _rehydrate_canonical_spec(
            parent_state,
            controller,
            work_id=work_id,
            logical_name=logical_name,
            generation=generation,
            compact_specs=compact_specs,
        )
        terminal = Attempt(
            schema_version=1,
            research_id=spec.research_id,
            generation=spec.generation,
            phase=spec.phase,
            work_id=work_id,
            attempt_id=latest_attempt_id,
            attempt_ordinal=latest_ordinal,
            spec_hash=spec.spec_hash,
            status=latest_status,
            created_at=compact_attempt.created_at,
            started_at=compact_attempt.started_at,
            expires_at=compact_attempt.expires_at,
            terminal_at=compact_attempt.terminal_at,
            terminal_code=compact_attempt.terminal_code,
        )
        if not retry_allowed(terminal, accepted=False):
            continue
        next_ordinal = next_ordinals.get(work_id)
        if not isinstance(next_ordinal, int) or next_ordinal != latest_ordinal + 1:
            raise ValueError("next_attempt_ordinal_invalid")
        retry = allocate_attempt(spec, attempt_ordinal=next_ordinal, created_at=clock())
        retry_specs[work_id] = spec
        retry_attempts[work_id] = retry

    return tuple(retry_specs.values()), retry_attempts


def _materialized(config: WorkUnitComponentConfig) -> dict[str, WorkSpec]:
    if config.materialized_specs:
        specs = {spec.work_id: spec for spec in config.materialized_specs}
        if len(specs) != len(config.materialized_specs) or tuple(specs) != tuple(sorted(specs)):
            raise ValueError("materialized_specs_not_canonical")
        if any(
            spec.research_id != config.research_id
            or spec.generation != config.generation
            or spec.phase.value != config.phase
            for spec in specs.values()
        ):
            raise ValueError("materialized_spec_scope_mismatch")
        return specs
    return {
        spec.work_id: spec
        for ordinal, intent in enumerate(config.intents, start=config.start_work_ordinal)
        for spec in (
            materialize_work_spec(
                research_id=config.research_id,
                generation=config.generation,
                phase=config.phase,
                work_ordinal=ordinal,
                intent=intent,
            ),
        )
    }


async def run_work_unit_component(
    parent_state: Mapping[str, Any],
    *,
    config: WorkUnitComponentConfig,
    worker: Worker,
    submit: Submit,
    reconcile: Reconcile | None = None,
) -> WorkUnitComponentResult:
    specs = _materialized(config)
    planned = tuple(sorted(specs))
    attempts: dict[str, Attempt] = {}
    records: dict[str, SubmissionRecord] = {}

    async def initialize(_state: WorkUnitComponentState) -> dict[str, Any]:
        return {
            "planned_work_ids": planned,
            "pending_work_ids": planned,
            "batch_cursor": 0,
            "in_flight_by_attempt_id": Overwrite({}),
            "candidates_by_attempt_id": Overwrite({}),
            "terminal_updates_by_attempt_id": {},
        }

    async def allocate(state: WorkUnitComponentState) -> dict[str, Any]:
        selected, cursor = select_batch(
            planned,
            cursor=state["batch_cursor"],
            max_concurrency=config.max_concurrency,
        )
        in_flight: dict[str, str] = {}
        for work_id in selected:
            attempt = config.replay_attempts_by_work_id.get(work_id)
            if attempt is None:
                attempt = allocate_attempt(specs[work_id], attempt_ordinal=0, created_at=config.clock())
            attempts[attempt.attempt_id] = attempt
            existing = await reconcile(specs[work_id], attempt) if reconcile is not None else None
            if existing is None:
                in_flight[attempt.attempt_id] = work_id
            else:
                records[work_id] = existing
        return {
            "batch_cursor": cursor,
            "pending_work_ids": planned[cursor:],
            "in_flight_by_attempt_id": Overwrite(in_flight),
        }

    def dispatch(state: WorkUnitComponentState) -> list[Send] | str:
        sends: list[Send] = []
        for attempt_id, work_id in sorted(state["in_flight_by_attempt_id"].items()):
            sends.append(
                Send(
                    "worker",
                    {
                        "planned_work_ids": state["planned_work_ids"],
                        "pending_work_ids": state["pending_work_ids"],
                        "batch_cursor": state["batch_cursor"],
                        "in_flight_by_attempt_id": {attempt_id: work_id},
                        "candidates_by_attempt_id": {},
                        "terminal_updates_by_attempt_id": state.get("terminal_updates_by_attempt_id", {}),
                    },
                )
            )
        return sends or "submit"

    async def run_worker(state: WorkUnitComponentState) -> dict[str, Any]:
        attempt_id, work_id = next(iter(state["in_flight_by_attempt_id"].items()))
        candidate = await worker(specs[work_id], attempts[attempt_id])
        return {"candidates_by_attempt_id": {attempt_id: candidate}}

    async def submit_batch(state: WorkUnitComponentState) -> dict[str, Any]:
        terminal: dict[str, AttemptTerminalUpdate] = {}
        for attempt_id, candidate in sorted(state["candidates_by_attempt_id"].items()):
            work_id = state["in_flight_by_attempt_id"][attempt_id]
            record = await submit(specs[work_id], attempts[attempt_id], candidate)
            records[work_id] = record
            terminal[attempt_id] = AttemptTerminalUpdate(
                attempt_id=attempt_id,
                status="submitted",
                terminal_at=record.submitted_at,
                terminal_code="accepted",
            )
        if config.fault_hook is not None:
            config.fault_hook("before_submit_node_return")
        return {
            "in_flight_by_attempt_id": Overwrite({}),
            "candidates_by_attempt_id": Overwrite({}),
            "terminal_updates_by_attempt_id": terminal,
        }

    def refill_or_drain(state: WorkUnitComponentState) -> str:
        return "allocate" if state["pending_work_ids"] else "drain"

    async def drain(_state: WorkUnitComponentState) -> dict[str, Any]:
        return {}

    builder = StateGraph(WorkUnitComponentState)
    builder.add_node("initialize", initialize)
    builder.add_node("allocate", allocate)
    builder.add_node("worker", run_worker)
    builder.add_node("submit", submit_batch, defer=True)
    builder.add_node("drain", drain)
    builder.add_edge(START, "initialize")
    builder.add_edge("initialize", "allocate")
    builder.add_conditional_edges("allocate", dispatch, {"submit": "submit"})
    builder.add_edge("worker", "submit")
    builder.add_conditional_edges("submit", refill_or_drain, {"allocate": "allocate", "drain": "drain"})
    builder.add_edge("drain", END)
    graph = builder.compile(checkpointer=False)
    child = await graph.ainvoke({}, {"recursion_limit": 128})

    attempt_refs: dict[str, dict[str, Any]] = {}
    statuses: dict[str, str] = {}
    for attempt_id, attempt in attempts.items():
        record = records[attempt.work_id]
        sibling_won = record.attempt_id != attempt_id
        attempt_refs[attempt_id] = {
            "created_at": attempt.created_at,
            "started_at": attempt.started_at if sibling_won else (attempt.started_at or attempt.created_at),
            "expires_at": attempt.expires_at,
            "terminal_at": record.submitted_at,
            "terminal_code": "superseded" if sibling_won else "accepted",
        }
        statuses[attempt_id] = "cancelled" if sibling_won else "submitted"
    next_attempt_ordinals = dict(parent_state.get("next_attempt_ordinal_by_work_id", {}))
    for attempt in attempts.values():
        next_attempt_ordinals[attempt.work_id] = max(
            int(next_attempt_ordinals.get(attempt.work_id, 0)),
            attempt.attempt_ordinal + 1,
        )
    parent_update = {
        "work_specs_by_id": {
            work_id: WorkSpecRef(worker_role=spec.worker_role, spec_hash=spec.spec_hash).model_dump(mode="json")
            for work_id, spec in specs.items()
        },
        "attempts_by_id": attempt_refs,
        "work_status_by_id": statuses,
        "active_attempt_by_work_id": {},
        "terminal_failures_by_attempt_id": {},
        "accepted_submission_refs": tuple(record.record_hash for _, record in sorted(records.items())),
        "pending_work_ids": tuple(child["pending_work_ids"]),
        "batch_cursor": child["batch_cursor"],
        "next_work_ordinal": config.start_work_ordinal + len(config.intents),
        "next_attempt_ordinal_by_work_id": next_attempt_ordinals,
    }
    gate_view = WorkUnitGateView(
        drained=not child["pending_work_ids"] and not child["in_flight_by_attempt_id"],
        planned_work_ids=planned,
        terminal_attempt_by_work_id={work_id: record.attempt_id for work_id, record in sorted(records.items())},
        accepted_record_by_work_id={work_id: record.record_hash for work_id, record in sorted(records.items())},
        failure_summaries=(),
    )
    preview_delta = {key: value for key, value in parent_update.items() if key in WORK_UNIT_GATE_PREVIEW_FIELDS}
    parent_projection = preview_work_unit_update(parent_state, preview_delta)
    parent_projection.update(
        {key: value for key, value in parent_update.items() if key not in WORK_UNIT_GATE_PREVIEW_FIELDS}
    )
    validate_component_gate_view(
        gate_view,
        planned_work_ids=planned,
        records_by_work_id=records,
        parent_projection=parent_projection,
    )
    return WorkUnitComponentResult(parent_update=parent_update, gate_view=gate_view)


async def run_fixture_work_unit_component(
    parent_state: Mapping[str, Any],
    *,
    logical_name: str,
    policy: PolicyRef,
    controller: WorkUnitControllerDependencies,
    intents: tuple[WorkIntent, ...],
    clock: Callable[[], datetime],
    fault_hook: Callable[[str], None] | None = None,
    worker: Worker | None = None,
) -> WorkUnitComponentResult:
    """Run a controlled work-unit phase through the production submit path.

    By default the fixture artifact-writing worker is used. Real phases (e.g.
    Wave0 source intake) pass their own ``worker`` callable that calls the
    runtime node-agent bridge; the shared reconcile/replay/retry/submit
    scaffolding is reused unchanged.
    """

    initial_records = await reconcile_parent_ledger_authority(parent_state, controller)
    records_by_work_id = {record.work_id: record for record in initial_records}

    async def fixture_worker(spec: WorkSpec, attempt: Attempt) -> CandidateResult:
        resolved = await controller.resolver.resolve_worker(
            logical_name=logical_name,
            work_spec=spec,
            attempt=attempt,
            policy=policy,
        )
        writer = resolved.artifact_writer
        if writer is None:
            raise ValueError("fixture_artifact_writer_missing")

        output_refs: list[OutputRef] = []
        for relative_path in spec.required_outputs:
            content = canonical_json_bytes(
                {
                    "fixture_marker": "non_research_fixture",
                    "phase": spec.phase.value,
                    "scope": list(spec.scope),
                    "work_id": spec.work_id,
                }
            )
            await writer.write_output(relative_path, content)
            output_refs.append(
                OutputRef(
                    path=output_path(spec.research_id, spec.work_id, attempt.attempt_id, relative_path),
                    content_hash=_content_hash(content),
                    schema_version=1,
                    byte_count=len(content),
                )
            )

        document = FixtureResultDocument(
            schema_version=1,
            research_id=spec.research_id,
            generation=spec.generation,
            phase=spec.phase,
            work_id=spec.work_id,
            attempt_id=attempt.attempt_id,
            worker_role=spec.worker_role,
            spec_hash=spec.spec_hash,
            result_contract="fixture.work-unit",
            fixture_marker="non_research_fixture",
            output_paths=spec.required_outputs,
            source_ids=(),
        )
        result_bytes = canonical_json_bytes(document)
        await writer.write_result(document)
        payload: dict[str, Any] = {
            "schema_version": 1,
            "research_id": spec.research_id,
            "generation": spec.generation,
            "phase": spec.phase,
            "work_id": spec.work_id,
            "attempt_id": attempt.attempt_id,
            "worker_role": spec.worker_role,
            "spec_hash": spec.spec_hash,
            "result_contract": spec.result_contract,
            "result_ref": result_path(spec.research_id, spec.work_id, attempt.attempt_id),
            "result_hash": _content_hash(result_bytes),
            "result_schema_version": spec.result_schema_version,
            "result_byte_count": len(result_bytes),
            "output_refs": tuple(output_refs),
            "source_refs": (),
        }
        payload["candidate_hash"] = compute_candidate_hash(payload)
        return CandidateResult.model_validate(payload)

    async def validate_and_submit(
        spec: WorkSpec,
        attempt: Attempt,
        candidate: CandidateResult,
    ) -> SubmissionRecord:
        return await submit_candidate_if_active(
            controller,
            spec=spec,
            attempt=attempt,
            candidate=candidate,
            active_attempt_id=attempt.attempt_id,
            now=clock(),
        )

    async def reconcile(spec: WorkSpec, attempt: Attempt) -> SubmissionRecord | None:
        record = records_by_work_id.get(spec.work_id)
        if record is None:
            return None
        accepted_spec = await _validate_accepted_record_artifacts(controller, record, initial_records)
        if accepted_spec != spec:
            raise ValueError("candidate_conflict")
        return record

    generation = int(parent_state.get("generation", 0))
    current_epoch_prefix = f"g{generation}_{logical_name}_w"
    has_current_epoch = any(
        isinstance(work_id, str) and work_id.startswith(current_epoch_prefix)
        for work_id in parent_state.get("work_specs_by_id", {})
    )
    start_work_ordinal = parent_state.get("next_work_ordinal", 0) if has_current_epoch else 0
    if not isinstance(start_work_ordinal, int):
        raise ValueError("next_work_ordinal_invalid")
    replay_specs, replay_attempts = await _rehydrate_active_replay(
        parent_state,
        controller,
        logical_name=logical_name,
        generation=generation,
    )
    retry_specs: tuple[WorkSpec, ...] = ()
    retry_attempts: dict[str, Attempt] = {}
    if not replay_specs:
        retry_specs, retry_attempts = await _allocate_terminal_retries(
            parent_state,
            controller,
            logical_name=logical_name,
            generation=generation,
            accepted_work_ids=set(records_by_work_id),
            clock=clock,
        )
    materialized_specs = replay_specs or retry_specs
    selected_attempts = replay_attempts or retry_attempts
    selected_intents = () if materialized_specs else intents
    effective_worker = worker if worker is not None else fixture_worker
    return await run_work_unit_component(
        parent_state,
        config=WorkUnitComponentConfig(
            research_id=str(parent_state.get("research_id", "")),
            generation=generation,
            phase=logical_name,
            intents=selected_intents,
            max_concurrency=3,
            clock=clock,
            start_work_ordinal=start_work_ordinal,
            fault_hook=fault_hook,
            materialized_specs=materialized_specs,
            replay_attempts_by_work_id=selected_attempts,
        ),
        worker=effective_worker,
        submit=validate_and_submit,
        reconcile=reconcile,
    )


__all__ = [
    "WorkUnitComponentConfig",
    "WorkUnitComponentResult",
    "reconcile_parent_ledger_authority",
    "run_fixture_work_unit_component",
    "run_work_unit_component",
    "submit_candidate_if_active",
]
