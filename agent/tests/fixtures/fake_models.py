"""Zero-API scripted chat models for bounded phase-agent contract tests.

These fakes return pre-scripted ``AIMessage`` responses (optionally with tool
calls and ``usage_metadata``) so budget, tool, and cancellation behaviour can be
exercised deterministically without any external model API.
"""

from __future__ import annotations

import asyncio
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult


class ScriptedChatModel(BaseChatModel):
    """Return successive scripted AIMessages; full-takeover friendly."""

    responses: list[AIMessage]
    calls: int = 0

    def _generate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:
        if not self.responses:
            raise AssertionError("ScriptedChatModel exhausted its scripted responses")
        message = self.responses.pop(0)
        object.__setattr__(self, "calls", self.calls + 1)
        return ChatResult(generations=[ChatGeneration(message=message)])

    def bind_tools(self, tools: Any, **kwargs: Any) -> BaseChatModel:  # noqa: ARG002
        # Scripted responses drive tool calls; ignore the actual binding.
        return self

    @property
    def _llm_type(self) -> str:
        return "scripted"


class BlockingChatModel(BaseChatModel):
    """Await forever on the async path so outer cancellation can be exercised."""

    started: Any = None  # asyncio.Event, set when the model call begins

    async def _agenerate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:
        if self.started is not None:
            self.started.set()
        await asyncio.Event().wait()  # never resolves; only cancellation ends it
        raise AssertionError("unreachable")

    def _generate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:
        raise AssertionError("BlockingChatModel is async-only")

    def bind_tools(self, tools: Any, **kwargs: Any) -> BaseChatModel:  # noqa: ARG002
        return self

    @property
    def _llm_type(self) -> str:
        return "blocking"


class CapturingChatModel(BaseChatModel):
    """Record the messages the agent sends so leakage can be asserted."""

    reply: AIMessage
    seen: list = []

    def _generate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:
        self.seen.append([getattr(m, "content", "") for m in messages])
        return ChatResult(generations=[ChatGeneration(message=self.reply)])

    def bind_tools(self, tools: Any, **kwargs: Any) -> BaseChatModel:  # noqa: ARG002
        return self

    @property
    def _llm_type(self) -> str:
        return "capturing"


class RaisingChatModel(BaseChatModel):
    """Raise a scripted provider exception from sync and async model paths."""

    error: Exception

    def _generate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:
        raise self.error

    async def _agenerate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:
        raise self.error

    def bind_tools(self, tools: Any, **kwargs: Any) -> BaseChatModel:
        return self

    @property
    def _llm_type(self) -> str:
        return "raising"


def ai_message(
    content: str = "done",
    *,
    tool_calls: list[dict] | None = None,
    input_tokens: int | None = 10,
    output_tokens: int | None = 5,
) -> AIMessage:
    usage = None
    if input_tokens is not None and output_tokens is not None:
        usage = {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": input_tokens + output_tokens,
        }
    return AIMessage(
        content=content,
        tool_calls=tool_calls or [],
        usage_metadata=usage,
    )
