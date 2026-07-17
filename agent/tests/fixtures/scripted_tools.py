"""Typed scripted external-tool adapters for deterministic workflows.

@impl EVH-007
@impl EVH-008
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Any

from langchain_core.tools import StructuredTool


@dataclass
class ScriptedTool:
    name: str
    responses: deque[str | BaseException]
    calls: list[dict[str, Any]] = field(default_factory=list)

    @classmethod
    def create(cls, name: str, *responses: str | BaseException) -> ScriptedTool:
        return cls(name=name, responses=deque(responses))

    def as_langchain_tool(self) -> StructuredTool:
        async def invoke(query: str = "", url: str = "") -> str:
            self.calls.append({"query": query, "url": url})
            if not self.responses:
                raise AssertionError(f"scripted tool exhausted: {self.name}")
            response = self.responses.popleft()
            if isinstance(response, BaseException):
                raise response
            return response

        return StructuredTool.from_function(
            coroutine=invoke,
            name=self.name,
            description=f"Deterministic scripted {self.name} adapter.",
        )


@dataclass
class ScriptedPathTool:
    name: str
    responses: deque[str | BaseException]
    calls: list[dict[str, Any]] = field(default_factory=list)

    @classmethod
    def create(cls, name: str, *responses: str | BaseException) -> ScriptedPathTool:
        return cls(name=name, responses=deque(responses))

    def as_langchain_tool(self) -> StructuredTool:
        async def invoke(path: str, content: str = "") -> str:
            self.calls.append({"path": path, "content": content})
            if not self.responses:
                raise AssertionError(f"scripted tool exhausted: {self.name}")
            response = self.responses.popleft()
            if isinstance(response, BaseException):
                raise response
            return response

        return StructuredTool.from_function(
            coroutine=invoke,
            name=self.name,
            description=f"Deterministic scripted path-aware {self.name} adapter.",
        )


def scripted_web_tools(
    *,
    search: tuple[str | BaseException, ...] = ("search result",),
    fetch: tuple[str | BaseException, ...] = ("fetched page",),
) -> tuple[ScriptedTool, ScriptedTool]:
    return ScriptedTool.create("web_search", *search), ScriptedTool.create("web_fetch", *fetch)


__all__ = ["ScriptedPathTool", "ScriptedTool", "scripted_web_tools"]
