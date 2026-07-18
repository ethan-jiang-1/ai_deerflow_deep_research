"""Bounded typed inputs and narrow call observations for scenario cases.

@impl EVH-001
@impl EVH-007
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING
from urllib.parse import urlsplit

if TYPE_CHECKING:
    from tests.scenarios.contracts import ScenarioBounds

MAX_MODEL_TURNS = 64
MAX_TOOL_STEPS = 128
MAX_LIFECYCLE_ACTIONS = 64
MAX_FAULT_POINTS = 16
MAX_MODEL_CONTENT_BYTES = 16_384
MAX_TOOL_RESULT_BYTES = 32_768
MAX_ARGUMENT_VALUE_BYTES = 4_096
SENSITIVE_RE = re.compile(r"(?i)(?:api[_-]?key|token|secret|password)\s*[:=]\s*\S+")
HOST_PATH_RE = re.compile(r"(?:/Users/[^/\s]+/|/home/[^/\s]+/|[A-Za-z]:\\Users\\)")


class LifecycleActionKind(StrEnum):
    START = "start"
    RESUME = "resume"
    CANCEL = "cancel"
    STATUS = "status"


class ToolOutcome(StrEnum):
    RESULT = "result"
    TIMEOUT = "timeout"
    UNAVAILABLE = "unavailable"
    ERROR = "error"


class FaultPoint(StrEnum):
    BEFORE_STAGING_WRITE = "before_staging_write"
    AFTER_STAGING_FSYNC = "after_staging_fsync"
    AFTER_PROFILE_REPLACE = "after_profile_replace"
    AFTER_MARKER_REPLACE = "after_marker_replace"
    AFTER_LEDGER_REPLACE = "after_ledger_replace"
    AFTER_DIRECTORY_FSYNC = "after_directory_fsync"
    BEFORE_SUBMIT_NODE_RETURN = "before_submit_node_return"
    AFTER_RETURNED_STATE_UPDATE = "after_returned_state_update"


@dataclass(frozen=True)
class ModelTurn:
    content: str
    tool_names: tuple[str, ...] = ()
    input_tokens: int = 10
    output_tokens: int = 5

    def __post_init__(self) -> None:
        _validate_text(self.content, max_bytes=MAX_MODEL_CONTENT_BYTES, oversize="model_turn_content_oversize")
        if not isinstance(self.tool_names, tuple) or any(not _valid_name(value) for value in self.tool_names):
            raise ValueError("model_turn_tool_names_invalid")
        if len(set(self.tool_names)) != len(self.tool_names):
            raise ValueError("model_turn_tool_names_duplicate")
        if not isinstance(self.input_tokens, int) or not 0 <= self.input_tokens <= 1_000_000:
            raise ValueError("model_turn_input_tokens_invalid")
        if not isinstance(self.output_tokens, int) or not 0 <= self.output_tokens <= 1_000_000:
            raise ValueError("model_turn_output_tokens_invalid")


@dataclass(frozen=True)
class ToolStep:
    tool_name: str
    arguments: tuple[tuple[str, str], ...]
    outcome: ToolOutcome
    result: str | None = None

    def __post_init__(self) -> None:
        if not _valid_name(self.tool_name):
            raise ValueError("tool_name_invalid")
        if not isinstance(self.arguments, tuple) or any(
            not isinstance(item, tuple) or len(item) != 2 or not _valid_name(item[0]) or not isinstance(item[1], str)
            for item in self.arguments
        ):
            raise ValueError("tool_arguments_invalid")
        if len({name for name, _value in self.arguments}) != len(self.arguments):
            raise ValueError("tool_arguments_duplicate")
        for name, value in self.arguments:
            _validate_text(value, max_bytes=MAX_ARGUMENT_VALUE_BYTES, oversize="tool_argument_oversize")
            if name == "url" and not _synthetic_url(value):
                raise ValueError("external_url_forbidden")
        if not isinstance(self.outcome, ToolOutcome):
            raise ValueError("tool_outcome_invalid")
        if self.outcome is ToolOutcome.RESULT:
            if self.result is None:
                raise ValueError("tool_result_required")
            _validate_text(self.result, max_bytes=MAX_TOOL_RESULT_BYTES, oversize="tool_result_oversize")
        elif self.result is not None:
            raise ValueError("tool_failure_result_forbidden")


@dataclass(frozen=True)
class LifecycleAction:
    kind: LifecycleActionKind
    value: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.kind, LifecycleActionKind):
            raise ValueError("lifecycle_action_invalid")
        if self.value is not None:
            _validate_text(self.value, max_bytes=4_096, oversize="lifecycle_action_value_oversize")


@dataclass(frozen=True)
class ScenarioInputs:
    model_turns: tuple[ModelTurn, ...] = ()
    tool_steps: tuple[ToolStep, ...] = ()
    lifecycle_actions: tuple[LifecycleAction, ...] = ()
    fault_points: tuple[FaultPoint, ...] = ()

    def __post_init__(self) -> None:
        _validate_typed_tuple(self.model_turns, ModelTurn, MAX_MODEL_TURNS, "scenario_model_turns_invalid")
        _validate_typed_tuple(self.tool_steps, ToolStep, MAX_TOOL_STEPS, "scenario_tool_steps_invalid")
        _validate_typed_tuple(
            self.lifecycle_actions,
            LifecycleAction,
            MAX_LIFECYCLE_ACTIONS,
            "scenario_lifecycle_actions_invalid",
        )
        _validate_typed_tuple(self.fault_points, FaultPoint, MAX_FAULT_POINTS, "scenario_fault_points_invalid")


@dataclass(frozen=True)
class LiveRequirements:
    dependency_names: tuple[str, ...]

    def __post_init__(self) -> None:
        if (
            not isinstance(self.dependency_names, tuple)
            or not self.dependency_names
            or any(not _valid_name(value) for value in self.dependency_names)
        ):
            raise ValueError("live_requirements_invalid")


@dataclass(frozen=True)
class ObservedToolCall:
    tool_name: str
    arguments: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class ScriptExecutionObservation:
    model_calls: int
    tool_calls: tuple[ObservedToolCall, ...]
    bound_tool_names: tuple[str, ...]


class ScriptInputError(ValueError):
    pass


def validate_script_observation(
    inputs: ScenarioInputs,
    bounds: ScenarioBounds,
    observation: ScriptExecutionObservation,
) -> None:
    errors: list[str] = []
    if len(inputs.model_turns) > bounds.max_model_calls or observation.model_calls > bounds.max_model_calls:
        errors.append("model call bound exceeded")
    if observation.model_calls != len(inputs.model_turns):
        errors.append(
            f"model call order/count mismatch: expected={len(inputs.model_turns)} actual={observation.model_calls}"
        )
    if len(inputs.tool_steps) > bounds.max_tool_calls or len(observation.tool_calls) > bounds.max_tool_calls:
        errors.append("tool call bound exceeded")
    expected_calls = tuple((step.tool_name, step.arguments) for step in inputs.tool_steps)
    actual_calls = tuple((call.tool_name, call.arguments) for call in observation.tool_calls)
    if actual_calls != expected_calls:
        errors.append(f"tool call order mismatch: expected={expected_calls!r} actual={actual_calls!r}")
    unbound = sorted({call.tool_name for call in observation.tool_calls} - set(observation.bound_tool_names))
    if unbound:
        errors.append(f"unbound tool calls: {unbound}")
    if errors:
        raise ScriptInputError("\n".join(errors))


def _validate_typed_tuple(values: object, item_type: type, maximum: int, code: str) -> None:
    if (
        not isinstance(values, tuple)
        or len(values) > maximum
        or any(not isinstance(item, item_type) for item in values)
    ):
        raise ValueError(code)


def _validate_text(value: object, *, max_bytes: int, oversize: str) -> None:
    if not isinstance(value, str):
        raise ValueError("input_text_invalid")
    if len(value.encode("utf-8")) > max_bytes:
        raise ValueError(oversize)
    if SENSITIVE_RE.search(value):
        raise ValueError("sensitive_input_forbidden")
    if HOST_PATH_RE.search(value):
        raise ValueError("raw_host_path_forbidden")


def _valid_name(value: object) -> bool:
    return isinstance(value, str) and bool(re.fullmatch(r"[a-z][a-z0-9_-]{1,63}", value))


def _synthetic_url(value: str) -> bool:
    parsed = urlsplit(value)
    return parsed.scheme in {"http", "https"} and parsed.hostname in {"example.com", "example.invalid", "localhost"}


__all__ = [
    "FaultPoint",
    "LifecycleAction",
    "LifecycleActionKind",
    "LiveRequirements",
    "ModelTurn",
    "ObservedToolCall",
    "ScenarioInputs",
    "ScriptExecutionObservation",
    "ScriptInputError",
    "ToolOutcome",
    "ToolStep",
    "validate_script_observation",
]
