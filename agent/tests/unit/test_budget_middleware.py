"""BudgetMiddleware admission-control and tool-budget contract (NOA-002)."""

from __future__ import annotations

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from deerflow_deep_research.agents.middleware import AgentBudgetError, BudgetMiddleware
from deerflow_deep_research.agents.policies import ExecutionBudget
from deerflow_deep_research.domain.enums import NodeFinishReason


def _budget(**overrides) -> ExecutionBudget:
    base = {
        "max_model_calls": 2,
        "max_total_tool_calls": 2,
        "max_tool_calls_per_response": 2,
        "max_parallel_tool_calls": 1,
        "total_token_budget": 1_000,
        "per_call_output_token_cap": 200,
        "per_tool_result_bytes": 64,
        "structured_result_bytes": 512,
        "wall_time_seconds": 5.0,
    }
    base.update(overrides)
    return ExecutionBudget(**base)


class FakeRequest:
    def __init__(self, messages=None, tools=(), system=None) -> None:
        self.messages = messages or [HumanMessage("hello")]
        self.tools = list(tools)
        self.system_message = system


class FakeResponse:
    def __init__(self, message: AIMessage) -> None:
        self.result = [message]


def _ai(content="ok", *, tool_calls=None, input_tokens=10, output_tokens=5) -> AIMessage:
    usage = None
    if input_tokens is not None and output_tokens is not None:
        usage = {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": input_tokens + output_tokens,
        }
    return AIMessage(content=content, tool_calls=tool_calls or [], usage_metadata=usage)


def _handler_for(message: AIMessage):
    async def handler(_request):
        return FakeResponse(message)

    return handler


async def test_normal_call_updates_counters() -> None:
    mw = BudgetMiddleware(_budget())
    await mw.awrap_model_call(FakeRequest(), _handler_for(_ai(output_tokens=5)))
    assert mw.model_calls == 1
    assert mw.tokens_used == 15


async def test_max_model_calls_refused_before_handler() -> None:
    mw = BudgetMiddleware(_budget(max_model_calls=1))
    mw.model_calls = 1
    called = False

    async def handler(_request):
        nonlocal called
        called = True
        return FakeResponse(_ai())

    with pytest.raises(AgentBudgetError) as excinfo:
        await mw.awrap_model_call(FakeRequest(), handler)
    assert excinfo.value.finish_reason == NodeFinishReason.BUDGET_EXHAUSTED
    assert called is False


async def test_non_text_content_fails_admission() -> None:
    mw = BudgetMiddleware(_budget())
    non_text = HumanMessage(content=[{"type": "image_url", "image_url": {"url": "x"}}])
    with pytest.raises(AgentBudgetError):
        await mw.awrap_model_call(FakeRequest(messages=[non_text]), _handler_for(_ai()))


async def test_token_admission_upper_bound_refused_before_handler() -> None:
    mw = BudgetMiddleware(_budget(total_token_budget=50, per_call_output_token_cap=40))
    called = False

    async def handler(_request):
        nonlocal called
        called = True
        return FakeResponse(_ai())

    big = HumanMessage("x" * 200)
    with pytest.raises(AgentBudgetError):
        await mw.awrap_model_call(FakeRequest(messages=[big]), handler)
    assert called is False


async def test_missing_usage_is_terminal_usage_unavailable() -> None:
    mw = BudgetMiddleware(_budget())
    with pytest.raises(AgentBudgetError) as excinfo:
        await mw.awrap_model_call(FakeRequest(), _handler_for(_ai(input_tokens=None, output_tokens=None)))
    assert excinfo.value.finish_reason == NodeFinishReason.USAGE_UNAVAILABLE


async def test_per_call_output_cap_exceeded() -> None:
    mw = BudgetMiddleware(_budget(per_call_output_token_cap=100, total_token_budget=1_000))
    with pytest.raises(AgentBudgetError) as excinfo:
        await mw.awrap_model_call(FakeRequest(), _handler_for(_ai(output_tokens=500)))
    assert excinfo.value.finish_reason == NodeFinishReason.BUDGET_EXHAUSTED


async def test_total_token_budget_exhausted_after_reconcile() -> None:
    mw = BudgetMiddleware(_budget(total_token_budget=120, per_call_output_token_cap=100))
    mw.tokens_used = 100
    with pytest.raises(AgentBudgetError):
        await mw.awrap_model_call(FakeRequest(), _handler_for(_ai(input_tokens=5, output_tokens=90)))


async def test_too_many_tool_calls_per_response() -> None:
    mw = BudgetMiddleware(_budget(max_tool_calls_per_response=2, max_parallel_tool_calls=2))
    three = [
        {"name": "t", "args": {}, "id": "1"},
        {"name": "t", "args": {}, "id": "2"},
        {"name": "t", "args": {}, "id": "3"},
    ]
    with pytest.raises(AgentBudgetError):
        await mw.awrap_model_call(FakeRequest(), _handler_for(_ai(tool_calls=three)))


async def test_parallel_tool_call_limit() -> None:
    mw = BudgetMiddleware(_budget(max_tool_calls_per_response=2, max_parallel_tool_calls=1))
    two = [{"name": "t", "args": {}, "id": "1"}, {"name": "t", "args": {}, "id": "2"}]
    with pytest.raises(AgentBudgetError):
        await mw.awrap_model_call(FakeRequest(), _handler_for(_ai(tool_calls=two)))


async def test_max_total_tool_calls_refused() -> None:
    mw = BudgetMiddleware(_budget(max_total_tool_calls=1, max_tool_calls_per_response=1, max_parallel_tool_calls=1))
    mw.tool_calls = 1

    async def handler(_request):
        return ToolMessage(content="x", tool_call_id="c1")

    with pytest.raises(AgentBudgetError):
        await mw.awrap_tool_call(object(), handler)


async def test_tool_result_is_size_bounded() -> None:
    mw = BudgetMiddleware(_budget(per_tool_result_bytes=16))
    big = "A" * 200

    async def handler(_request):
        return ToolMessage(content=big, tool_call_id="c1")

    result = await mw.awrap_tool_call(object(), handler)
    assert len(result.content.encode("utf-8")) < len(big.encode("utf-8"))
    assert "[truncated" in result.content
