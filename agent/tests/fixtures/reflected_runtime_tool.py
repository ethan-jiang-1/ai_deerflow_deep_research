"""Async BaseTool fixture resolved by DeerFlow's configured-tool loader."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from typing import TypedDict

from deerflow.tools.types import Runtime
from langchain_core.tools import tool
from langgraph.graph import END, START, StateGraph


class CancellationProbeState(TypedDict):
    payload: str


@dataclass
class CancellationControl:
    started: asyncio.Event = field(default_factory=asyncio.Event)
    release: asyncio.Event = field(default_factory=asyncio.Event)
    terminated: asyncio.Event = field(default_factory=asyncio.Event)
    active_nodes: int = 0


_cancellation_control = CancellationControl()


def reset_cancellation_control() -> CancellationControl:
    global _cancellation_control
    _cancellation_control = CancellationControl()
    return _cancellation_control


async def _blocking_probe_node(state: CancellationProbeState) -> CancellationProbeState:
    control = _cancellation_control
    control.active_nodes += 1
    control.started.set()
    try:
        await control.release.wait()
        return state
    finally:
        control.active_nodes -= 1
        control.terminated.set()


def _make_cancellation_graph():
    builder = StateGraph(CancellationProbeState)
    builder.add_node("blocking_probe", _blocking_probe_node)
    builder.add_edge(START, "blocking_probe")
    builder.add_edge("blocking_probe", END)
    return builder.compile(checkpointer=None)


_cancellation_graph = _make_cancellation_graph()


@tool("deep_research_runtime_viability_probe", parse_docstring=True)
async def runtime_viability_probe(payload: str, runtime: Runtime) -> str:
    """Return selected runtime channels for the viability contract.

    Args:
        payload: Opaque test payload.
        runtime: Runtime injected by LangGraph's ToolNode.
    """
    return json.dumps(
        {
            "context_sentinel": runtime.context.get("user_id"),
            "payload": payload,
            "state_sentinel": runtime.state.get("state_sentinel"),
            "tool_call_id": runtime.tool_call_id,
        },
        sort_keys=True,
    )


@tool("deep_research_cancellation_viability_probe", parse_docstring=True)
async def cancellation_viability_probe(payload: str) -> str:
    """Run a blocking nested graph until its outer task is cancelled.

    Args:
        payload: Opaque test payload passed through nested state.
    """
    result = await _cancellation_graph.ainvoke({"payload": payload})
    return result["payload"]
