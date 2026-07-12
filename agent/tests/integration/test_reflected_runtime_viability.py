"""Hard viability gate for reflected async ToolRuntime injection."""

from __future__ import annotations

import json

import pytest
from deerflow.config.app_config import AppConfig
from deerflow.config.tool_config import ToolConfig
from deerflow.tools.tools import get_available_tools
from langchain_core.messages import AIMessage
from langchain_core.tools import BaseTool
from langgraph.prebuilt import ToolNode
from langgraph.runtime import Runtime

TOOL_NAME = "deep_research_runtime_viability_probe"
TOOL_PATH = "tests.fixtures.reflected_runtime_tool:runtime_viability_probe"


def _config_with_reflected_probe() -> AppConfig:
    return AppConfig(
        sandbox={"use": "deerflow.sandbox.local:LocalSandboxProvider"},
        tools=[ToolConfig(name=TOOL_NAME, group="deep-research-viability", use=TOOL_PATH)],
    )


@pytest.mark.asyncio
async def test_reflected_async_tool_receives_runtime_context_and_state() -> None:
    """DeerFlow reflection plus ToolNode must preserve both authority channels."""
    loaded = get_available_tools(
        groups=["deep-research-viability"],
        include_mcp=False,
        app_config=_config_with_reflected_probe(),
    )
    probe = next(tool for tool in loaded if tool.name == TOOL_NAME)
    assert isinstance(probe, BaseTool)
    assert probe.coroutine is not None

    outer_runtime = Runtime(
        context={
            "user_id": "viability-user",
            "thread_id": "viability-thread",
            "run_id": "viability-run",
        }
    )
    config = {"configurable": {"__pregel_runtime": outer_runtime}}
    state = {
        "messages": [
            AIMessage(
                content="",
                tool_calls=[{"name": TOOL_NAME, "args": {"payload": "ping"}, "id": "probe-call"}],
            )
        ],
        "state_sentinel": "state-reached-tool",
    }

    result = await ToolNode([probe]).ainvoke(state, config=config)
    payload = json.loads(result["messages"][0].content)

    assert payload == {
        "context_sentinel": "viability-user",
        "payload": "ping",
        "state_sentinel": "state-reached-tool",
        "tool_call_id": "probe-call",
    }
