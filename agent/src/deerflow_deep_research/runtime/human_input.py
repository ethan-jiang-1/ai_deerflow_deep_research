"""Trusted outer-message selection and HITL projection.

@impl REG-003
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from langchain_core.messages import HumanMessage, ToolMessage
from langgraph.graph import END
from langgraph.types import Command

from deerflow_deep_research.domain.lifecycle import (
    AcceptedHumanResponse,
    DeepResearchControlResult,
    HumanInputMode,
    PendingResearchInterrupt,
    ResponseKind,
    serialize_control_result,
    text_only_content,
)


class HumanInputError(ValueError):
    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"[{code}] {detail}")
        self.code = code
        self.detail = detail


@dataclass(frozen=True)
class SelectedStartMessage:
    message_id: str
    text: str


@dataclass(frozen=True)
class ConsumedResponseRetry:
    request_id: str
    message_id: str


def _response_payload(message: HumanMessage) -> dict[str, Any] | None:
    payload = message.additional_kwargs.get("human_input_response")
    return payload if isinstance(payload, dict) else None


def _is_synthetic(message: HumanMessage) -> bool:
    if _response_payload(message) is not None:
        return False
    if message.additional_kwargs.get("hide_from_ui"):
        return True
    return message.name in {"summary", "dynamic_context", "system_reminder"}


def select_start_message(messages: list[Any] | tuple[Any, ...]) -> SelectedStartMessage:
    candidate: HumanMessage | None = None
    for message in reversed(messages):
        if not isinstance(message, HumanMessage) or _is_synthetic(message):
            continue
        candidate = message
        break
    if candidate is None or _response_payload(candidate) is not None or not candidate.id:
        raise HumanInputError("start_message_invalid", "newest visible user message is not a research request")
    try:
        text = text_only_content(candidate.content)
    except ValueError as exc:
        raise HumanInputError("start_message_invalid", "research request content is invalid") from exc
    return SelectedStartMessage(message_id=str(candidate.id), text=text)


def _latest_actual_human(messages: list[Any] | tuple[Any, ...]) -> HumanMessage | None:
    for message in reversed(messages):
        if isinstance(message, HumanMessage) and not _is_synthetic(message):
            return message
    return None


def _consumed_retry(
    message: HumanMessage | None,
    consumed_request_ids: tuple[str, ...],
    consumed_message_ids: tuple[str, ...],
) -> ConsumedResponseRetry | None:
    if message is None or not message.id:
        return None
    pairs = dict(zip(consumed_message_ids, consumed_request_ids, strict=True))
    request_id = pairs.get(str(message.id))
    if request_id is None:
        return None
    payload = _response_payload(message)
    if payload is not None and payload.get("request_id") != request_id:
        return None
    return ConsumedResponseRetry(request_id=request_id, message_id=str(message.id))


def find_consumed_retry(
    messages: list[Any] | tuple[Any, ...],
    *,
    consumed_request_ids: tuple[str, ...],
    consumed_message_ids: tuple[str, ...],
) -> ConsumedResponseRetry | None:
    if len(consumed_request_ids) != len(consumed_message_ids):
        raise HumanInputError("checkpoint_inconsistent", "consumed response ids are not paired")
    return _consumed_retry(_latest_actual_human(messages), consumed_request_ids, consumed_message_ids)


def extract_resume_response(
    messages: list[Any] | tuple[Any, ...],
    pending: PendingResearchInterrupt,
    *,
    consumed_request_ids: tuple[str, ...],
    consumed_message_ids: tuple[str, ...],
) -> AcceptedHumanResponse | ConsumedResponseRetry:
    replay = find_consumed_retry(
        messages,
        consumed_request_ids=consumed_request_ids,
        consumed_message_ids=consumed_message_ids,
    )
    if replay is not None:
        return replay

    cursor_index = next(
        (
            index
            for index, message in enumerate(messages)
            if isinstance(message, HumanMessage) and message.id == pending.suspension_cursor
        ),
        None,
    )
    if cursor_index is None:
        raise HumanInputError("response_mismatch", "suspension cursor is absent")
    candidate: HumanMessage | None = None
    for message in reversed(messages[cursor_index + 1 :]):
        if not isinstance(message, HumanMessage) or _is_synthetic(message):
            continue
        candidate = message
        break
    if candidate is None or not candidate.id:
        raise HumanInputError("response_mismatch", "no eligible response after suspension")

    payload = _response_payload(candidate)
    if payload is not None:
        if (
            payload.get("version") != 1
            or payload.get("kind") != "human_input_response"
            or payload.get("source") != "deep_research"
            or payload.get("request_id") != pending.request.request_id
        ):
            raise HumanInputError("response_mismatch", "structured response correlation does not match")
        try:
            response = AcceptedHumanResponse(
                request_id=pending.request.request_id,
                message_id=str(candidate.id),
                value=payload.get("value"),
                response_kind=payload.get("response_kind"),
                option_id=payload.get("option_id"),
            )
        except (TypeError, ValueError) as exc:
            raise HumanInputError("response_invalid", "structured response value is invalid") from exc
        return _validate_response_mode(response, pending)

    try:
        value = text_only_content(candidate.content)
    except ValueError as exc:
        raise HumanInputError("response_invalid", "plain response content is invalid") from exc
    response = AcceptedHumanResponse(
        request_id=pending.request.request_id,
        message_id=str(candidate.id),
        value=value,
        response_kind=ResponseKind.TEXT,
    )
    return _validate_response_mode(response, pending)


def _validate_response_mode(
    response: AcceptedHumanResponse,
    pending: PendingResearchInterrupt,
) -> AcceptedHumanResponse:
    if pending.request.mode is HumanInputMode.TEXT:
        if response.response_kind is not ResponseKind.TEXT:
            raise HumanInputError("response_invalid", "text request requires a text response")
        return response
    advertised = {option.id.value for option in pending.request.options}
    if response.response_kind is ResponseKind.OPTION:
        if response.option_id != response.value or response.value not in advertised:
            raise HumanInputError("response_invalid", "choice option id/value is invalid")
        return response
    normalized = response.value.strip().lower()
    if normalized not in advertised:
        raise HumanInputError("response_invalid", "plain choice does not match an advertised value")
    return response.model_copy(update={"value": normalized})


def pending_from_snapshot(snapshot: Any) -> PendingResearchInterrupt | None:
    interrupts = [interrupt for task in snapshot.tasks for interrupt in task.interrupts]
    if not interrupts:
        return None
    if len(interrupts) != 1:
        raise HumanInputError("checkpoint_inconsistent", "research lifecycle must have one pending interrupt")
    try:
        return PendingResearchInterrupt.model_validate(interrupts[0].value)
    except (TypeError, ValueError) as exc:
        raise HumanInputError("checkpoint_inconsistent", "pending interrupt descriptor is invalid") from exc


def project_suspension(
    *,
    pending: PendingResearchInterrupt,
    result: DeepResearchControlResult,
    tool_call_id: str,
) -> Command:
    if result.request_id != pending.request.request_id:
        raise HumanInputError("checkpoint_inconsistent", "result and interrupt request ids differ")
    artifact_request = pending.request.model_dump(mode="json")
    if pending.request.mode is HumanInputMode.TEXT:
        artifact_request.pop("options", None)
    message = ToolMessage(
        content=serialize_control_result(result),
        tool_call_id=tool_call_id,
        id=pending.request.request_id,
        name="deep_research",
        artifact={"human_input": artifact_request},
    )
    return Command(update={"messages": [message]}, goto=END)


__all__ = [
    "ConsumedResponseRetry",
    "HumanInputError",
    "SelectedStartMessage",
    "extract_resume_response",
    "find_consumed_retry",
    "pending_from_snapshot",
    "project_suspension",
    "select_start_message",
]
