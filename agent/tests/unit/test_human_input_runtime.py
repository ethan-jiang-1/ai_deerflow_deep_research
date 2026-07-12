"""Outer HumanMessage selection and suspension projection (REG-003/004)."""

from __future__ import annotations

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from deerflow_deep_research.domain.lifecycle import (
    DeepResearchControlResult,
    HumanInputMode,
    HumanInputRequest,
    PendingResearchInterrupt,
)
from deerflow_deep_research.runtime.human_input import (
    ConsumedResponseRetry,
    HumanInputError,
    extract_resume_response,
    project_suspension,
    select_start_message,
)


def _pending(mode: HumanInputMode = HumanInputMode.TEXT) -> PendingResearchInterrupt:
    return PendingResearchInterrupt(
        request=HumanInputRequest(
            request_id="drh_test",
            mode=mode,
            title="implementation_mode=full_fake",
            context="implementation_mode=full_fake fixture",
        ),
        suspension_cursor="cursor",
        phase="hitl1",
        generation=0,
    )


def test_start_selects_newest_visible_genuine_message_and_exact_text_blocks() -> None:
    messages = [
        HumanMessage(content="older", id="old"),
        HumanMessage(content="hidden", id="hidden", additional_kwargs={"hide_from_ui": True}),
        HumanMessage(content=[{"type": "text", "text": "new"}, {"type": "text", "text": " request"}], id="new"),
        AIMessage(content="calling tool"),
    ]
    selected = select_start_message(messages)
    assert selected.message_id == "new"
    assert selected.text == "new request"


def test_start_does_not_fall_back_past_invalid_newest_candidate() -> None:
    messages = [HumanMessage(content="older", id="old"), HumanMessage(content="", id="new")]
    with pytest.raises(HumanInputError, match="start_message_invalid"):
        select_start_message(messages)


@pytest.mark.parametrize(
    "content",
    [
        [{"type": "image_url", "image_url": {"url": "x"}}],
        [{"type": "text", "text": "ok", "extra": "no"}],
    ],
)
def test_start_rejects_non_text_or_malformed_blocks(content) -> None:
    with pytest.raises(HumanInputError, match="start_message_invalid"):
        select_start_message([HumanMessage(content=content, id="new")])


def test_structured_hidden_response_is_genuine_and_correlated() -> None:
    payload = {
        "version": 1,
        "kind": "human_input_response",
        "source": "deep_research",
        "request_id": "drh_test",
        "response_kind": "text",
        "value": "answer",
    }
    messages = [
        HumanMessage(content="start", id="cursor"),
        HumanMessage(
            content="formatted",
            id="reply",
            additional_kwargs={"hide_from_ui": True, "human_input_response": payload},
        ),
    ]
    response = extract_resume_response(messages, _pending(), consumed_request_ids=(), consumed_message_ids=())
    assert response.message_id == "reply"
    assert response.value == "answer"


def test_forged_non_human_and_stale_message_do_not_resume() -> None:
    messages = [
        HumanMessage(content="start", id="cursor"),
        ToolMessage(content="answer", tool_call_id="x"),
        AIMessage(content="answer"),
    ]
    with pytest.raises(HumanInputError, match="response_mismatch"):
        extract_resume_response(messages, _pending(), consumed_request_ids=(), consumed_message_ids=())


def test_consumed_exact_pair_is_classified_for_reprojection() -> None:
    payload = {
        "version": 1,
        "kind": "human_input_response",
        "source": "deep_research",
        "request_id": "drh_old",
        "response_kind": "text",
        "value": "answer",
    }
    messages = [HumanMessage(content="formatted", id="reply", additional_kwargs={"human_input_response": payload})]
    result = extract_resume_response(
        messages,
        _pending(),
        consumed_request_ids=("drh_old",),
        consumed_message_ids=("reply",),
    )
    assert isinstance(result, ConsumedResponseRetry)


def test_suspension_projection_uses_same_control_envelope_and_omits_internal_cursor() -> None:
    pending = _pending()
    result = DeepResearchControlResult(
        action="start",
        code="suspended",
        durability="same_process",
        research_id="r_" + "A" * 43,
        status="suspended",
        phase="hitl1",
        generation=0,
        request_id="drh_test",
    )
    command = project_suspension(pending=pending, result=result, tool_call_id="tool-call")
    message = command.update["messages"][0]
    assert message.tool_call_id == "tool-call"
    assert message.id == "drh_test"
    assert message.name == "deep_research"
    assert "full_fake" in message.content
    assert message.artifact["human_input"]["request_id"] == "drh_test"
    assert "suspension_cursor" not in str(message.artifact)
