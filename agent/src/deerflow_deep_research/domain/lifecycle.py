"""Pure lifecycle and wire contracts for the change-01 fake graph.

@impl REG-003
@impl REG-004
"""

from __future__ import annotations

import base64
import hashlib
import json
from collections.abc import Mapping, Sequence
from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

MAX_START_REQUEST_CHARS = 16_384
MAX_CONTROL_RESULT_CHARS = 4_096
MAX_FAKE_TRACE_ENTRIES = 256
MAX_FAKE_REPAIR_ATTEMPTS = 3
MAX_FAKE_RERUN_GENERATIONS = 2
RESEARCH_ID_PATTERN = r"^r_[A-Za-z0-9_-]{43}$"


class LifecycleAction(StrEnum):
    START = "start"
    RESUME = "resume"
    STATUS = "status"
    CANCEL = "cancel"


class LifecycleStatus(StrEnum):
    SUSPENDED = "suspended"
    COMPLETED = "completed"
    STOPPED = "stopped"
    CANCELLED = "cancelled"
    BLOCKED = "blocked"


class LogicalPhase(StrEnum):
    BOOTSTRAP = "bootstrap"
    HITL1 = "hitl1"
    TOPIC_PLANNING = "topic_planning"
    WAVE0 = "wave0"
    WAVE1 = "wave1"
    WAVE2_SYNTHESIS = "wave2_synthesis"
    TARGETED_EVIDENCE = "targeted_evidence"
    HITL2 = "hitl2"
    RERUN = "rerun"
    READINESS = "readiness"
    FINAL_DELIVERY = "final_delivery"


class TerminalReason(StrEnum):
    COMPLETED = "completed"
    USER_STOPPED = "user_stopped"
    USER_CANCELLED = "user_cancelled"
    REPAIR_EXHAUSTED = "repair_exhausted"  # retained for compat, no longer produced by gate
    RERUN_EXHAUSTED = "rerun_exhausted"
    GATE_BLOCKED = "gate_blocked"  # @impl REG-004 — gate fatigue/budget exhaustion


class ResultCode(StrEnum):
    SUSPENDED = "suspended"
    COMPLETED = "completed"
    STOPPED = "stopped"
    CANCELLED = "cancelled"
    BLOCKED = "blocked"
    STATUS_OK = "status_ok"
    START_MESSAGE_INVALID = "start_message_invalid"
    THREAD_RESEARCH_EXISTS = "thread_research_exists"
    RESPONSE_MISMATCH = "response_mismatch"
    RESPONSE_INVALID = "response_invalid"
    INVALID_TRANSITION = "invalid_transition"
    RESEARCH_NOT_FOUND = "research_not_found"
    SCHEMA_UNSUPPORTED = "schema_unsupported"
    CHECKPOINT_INCONSISTENT = "checkpoint_inconsistent"
    INTERACTIVE_REQUIRED = "interactive_required"
    HUMAN_INPUT_TRANSPORT_UNAVAILABLE = "human_input_transport_unavailable"
    EXCLUSIVE_CONTROL_CALL_REQUIRED = "exclusive_control_call_required"
    IMPLEMENTATION_UNAVAILABLE = "implementation_unavailable"


class InfrastructureResultCode(StrEnum):
    RESTART_REQUIRED = "restart_required"
    IDENTITY_MISSING = "identity_missing"
    RUNTIME_CONTEXT_REQUIRED = "runtime_context_required"
    SANDBOX_UNAVAILABLE = "sandbox_unavailable"
    THREAD_PATH_INVALID = "thread_path_invalid"
    THREAD_PATH_ESCAPE = "thread_path_escape"
    THREAD_DATA_MISMATCH = "thread_data_mismatch"
    THREAD_MISSING = "thread_missing"
    RUN_MISSING = "run_missing"
    APP_CONFIG_MISSING = "app_config_missing"
    WORK_UNIT_STORAGE_UNAVAILABLE = "work_unit_storage_unavailable"
    WORK_UNIT_STORE_BUSY = "work_unit_store_busy"


class WorkUnitStorageReason(StrEnum):
    AIO_PROVISIONER_UNMOUNTED = "aio_provisioner_unmounted"
    E2B_UNMOUNTED = "e2b_unmounted"
    BOXLITE_UNMOUNTED = "boxlite_unmounted"
    PROVIDER_UNRECOGNIZED = "provider_unrecognized"
    THREAD_MOUNT_UNAVAILABLE = "thread_mount_unavailable"
    WORKSPACE_ALIAS_MISMATCH = "workspace_alias_mismatch"
    POSIX_PRIMITIVES_UNAVAILABLE = "posix_primitives_unavailable"
    PROBE_CLEANUP_FAILED = "probe_cleanup_failed"
    LEDGER_CORRUPT = "ledger_corrupt"
    ACCEPTED_ARTIFACT_DIVERGED = "accepted_artifact_diverged"
    LOCK_TIMEOUT = "lock_timeout"


class Durability(StrEnum):
    SAME_PROCESS = "same_process"
    RESTART_DURABLE = "restart_durable"
    UNAVAILABLE = "unavailable"


class ResponseKind(StrEnum):
    TEXT = "text"
    OPTION = "option"


class HumanInputMode(StrEnum):
    TEXT = "text"
    CHOICE = "choice"


class BootstrapRoute(StrEnum):
    NEEDS_INPUT = "needs_input"
    PROFILE_COMPLETE = "profile_complete"


class GateVerdict(StrEnum):
    PASS = "pass"
    REPAIR = "repair"


class SynthesisVerdict(StrEnum):
    PASS = "pass"
    EVIDENCE_NEEDED = "evidence_needed"


class Hitl2Decision(StrEnum):
    PROCEED = "proceed"
    REVISE_VIEW = "revise_view"
    REPAIR = "repair"
    RERUN = "rerun"
    STOP = "stop"


class ReadinessVerdict(StrEnum):
    PASS = "pass"
    REPAIR_TARGETED = "repair_targeted"
    REPAIR_SYNTHESIS = "repair_synthesis"
    REPAIR_HITL2 = "repair_hitl2"


class FinalVerdict(StrEnum):
    PASS = "pass"
    REPAIR = "repair"
    EVIDENCE_BLOCKED = "evidence_blocked"


class FrozenContract(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class BranchResult(FrozenContract):
    branch_id: str = Field(min_length=1, max_length=64, pattern=r"^[a-z][a-z0-9_-]*$")
    verdict: GateVerdict


class AcceptedHumanResponse(FrozenContract):
    request_id: str = Field(min_length=1, max_length=128)
    message_id: str = Field(min_length=1, max_length=256)
    value: str = Field(min_length=1, max_length=MAX_START_REQUEST_CHARS)
    response_kind: ResponseKind
    option_id: str | None = Field(default=None, min_length=1, max_length=64)

    @model_validator(mode="after")
    def validate_option_shape(self) -> AcceptedHumanResponse:
        if self.response_kind is ResponseKind.OPTION and self.option_id is None:
            raise ValueError("option response requires option_id")
        if self.response_kind is ResponseKind.TEXT and self.option_id is not None:
            raise ValueError("text response cannot include option_id")
        return self


class InternalCancelDecision(FrozenContract):
    kind: Literal["internal_cancel"] = "internal_cancel"


ResumeDecision = Annotated[AcceptedHumanResponse | InternalCancelDecision, Field(discriminator=None)]


class HumanInputOption(FrozenContract):
    id: Hitl2Decision
    label: str = Field(min_length=1, max_length=128)
    value: Hitl2Decision

    @model_validator(mode="after")
    def id_matches_value(self) -> HumanInputOption:
        if self.id is not self.value:
            raise ValueError("option id and value must match")
        return self


class HumanInputRequest(FrozenContract):
    version: Literal[1] = 1
    kind: Literal["human_input_request"] = "human_input_request"
    source: Literal["deep_research"] = "deep_research"
    request_id: str = Field(min_length=1, max_length=128)
    mode: HumanInputMode
    title: str = Field(min_length=1, max_length=256)
    context: str = Field(min_length=1, max_length=2_048)
    options: tuple[HumanInputOption, ...] = ()

    @model_validator(mode="after")
    def validate_mode(self) -> HumanInputRequest:
        if self.mode is HumanInputMode.TEXT and self.options:
            raise ValueError("text input cannot define options")
        if self.mode is HumanInputMode.CHOICE:
            expected = tuple(Hitl2Decision)
            if tuple(option.id for option in self.options) != expected:
                raise ValueError("choice input must advertise the stable HITL2 options")
        return self


class PendingResearchInterrupt(FrozenContract):
    request: HumanInputRequest
    suspension_cursor: str = Field(min_length=1, max_length=256)
    phase: Literal["hitl1", "hitl2"]
    generation: int = Field(ge=0, le=MAX_FAKE_RERUN_GENERATIONS)


def make_hitl_request_id(*, research_id: str, phase: str, generation: int, ordinal: int) -> str:
    encoded = json.dumps(
        ["deep-research/hitl/v1", research_id, phase, generation, ordinal],
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode()
    digest = base64.urlsafe_b64encode(hashlib.sha256(encoded).digest()).decode().rstrip("=")
    return f"drh_{digest}"


def completed_visits(state: Mapping[str, Any], logical_name: str) -> int:
    return sum(1 for item in state.get("execution_trace", ()) if item == logical_name)


def make_attempt_id(state: Mapping[str, Any], logical_name: str) -> str:
    generation = int(state.get("generation", 0))
    return f"g{generation}-{logical_name}-a{completed_visits(state, logical_name) + 1}"


def text_only_content(content: Any, *, max_chars: int = MAX_START_REQUEST_CHARS) -> str:
    if isinstance(content, str):
        text = content
    elif isinstance(content, Sequence) and not isinstance(content, (bytes, bytearray, str)):
        pieces: list[str] = []
        for block in content:
            if not isinstance(block, Mapping) or set(block) != {"type", "text"} or block.get("type") != "text":
                raise ValueError("content_blocks_invalid")
            value = block.get("text")
            if not isinstance(value, str):
                raise ValueError("content_blocks_invalid")
            pieces.append(value)
        text = "".join(pieces)
    else:
        raise ValueError("content_invalid")
    if not text or len(text) > max_chars:
        raise ValueError("content_invalid")
    return text


class DeepResearchControlResult(FrozenContract):
    schema_version: Literal[1] = 1
    implementation_mode: Literal["full_fake"] = "full_fake"
    action: LifecycleAction
    code: ResultCode | InfrastructureResultCode
    durability: Durability
    research_id: str | None = Field(default=None, pattern=RESEARCH_ID_PATTERN)
    status: LifecycleStatus | None = None
    phase: LogicalPhase | None = None
    generation: int | None = Field(default=None, ge=0, le=2)
    request_id: str | None = Field(default=None, min_length=1, max_length=128)
    terminal_reason: TerminalReason | None = None
    infrastructure_reason: WorkUnitStorageReason | None = None

    @model_validator(mode="after")
    def validate_lifecycle_shape(self) -> DeepResearchControlResult:
        storage_codes = {
            InfrastructureResultCode.WORK_UNIT_STORAGE_UNAVAILABLE,
            InfrastructureResultCode.WORK_UNIT_STORE_BUSY,
        }
        if self.code in storage_codes and self.infrastructure_reason is None:
            raise ValueError("work-unit infrastructure code requires infrastructure_reason")
        if self.code not in storage_codes and self.infrastructure_reason is not None:
            raise ValueError("infrastructure_reason is forbidden for this code")
        if self.code is InfrastructureResultCode.WORK_UNIT_STORE_BUSY:
            if self.infrastructure_reason is not WorkUnitStorageReason.LOCK_TIMEOUT:
                raise ValueError("work_unit_store_busy requires lock_timeout")
        elif self.infrastructure_reason is WorkUnitStorageReason.LOCK_TIMEOUT:
            raise ValueError("lock_timeout requires work_unit_store_busy")
        lifecycle_fields = (self.status, self.phase, self.generation)
        if any(value is not None for value in lifecycle_fields) and not all(
            value is not None for value in lifecycle_fields
        ):
            raise ValueError("status, phase, and generation must appear together")
        if self.status is LifecycleStatus.SUSPENDED and self.request_id is None:
            raise ValueError("suspended result requires request_id")
        if self.request_id is not None and self.status is not LifecycleStatus.SUSPENDED:
            raise ValueError("request_id is only valid for suspended results")
        if self.terminal_reason is not None and self.status not in {
            LifecycleStatus.COMPLETED,
            LifecycleStatus.STOPPED,
            LifecycleStatus.CANCELLED,
            LifecycleStatus.BLOCKED,
        }:
            raise ValueError("terminal_reason requires a terminal status")
        return self


def serialize_control_result(result: DeepResearchControlResult) -> str:
    payload = json.dumps(result.model_dump(mode="json", exclude_none=True), sort_keys=True, separators=(",", ":"))
    if len(payload) > MAX_CONTROL_RESULT_CHARS:
        raise ValueError("control_result_too_large")
    return payload


__all__ = [
    "AcceptedHumanResponse",
    "BranchResult",
    "BootstrapRoute",
    "DeepResearchControlResult",
    "Durability",
    "FinalVerdict",
    "GateVerdict",
    "Hitl2Decision",
    "HumanInputMode",
    "HumanInputOption",
    "HumanInputRequest",
    "InfrastructureResultCode",
    "InternalCancelDecision",
    "LifecycleAction",
    "LifecycleStatus",
    "LogicalPhase",
    "MAX_CONTROL_RESULT_CHARS",
    "MAX_FAKE_REPAIR_ATTEMPTS",
    "MAX_FAKE_RERUN_GENERATIONS",
    "MAX_FAKE_TRACE_ENTRIES",
    "MAX_START_REQUEST_CHARS",
    "ReadinessVerdict",
    "RESEARCH_ID_PATTERN",
    "ResponseKind",
    "ResultCode",
    "ResumeDecision",
    "SynthesisVerdict",
    "TerminalReason",
    "WorkUnitStorageReason",
    "PendingResearchInterrupt",
    "make_hitl_request_id",
    "completed_visits",
    "make_attempt_id",
    "text_only_content",
    "serialize_control_result",
]
