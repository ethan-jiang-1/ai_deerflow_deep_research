"""Hard viability gate for reflected async ToolRuntime injection.

@impl RUI-001
"""

from __future__ import annotations

import json

import pytest
from deerflow.config.app_config import AppConfig
from deerflow.config.tool_config import ToolConfig
from deerflow.tools.tools import get_available_tools
from langchain_core.messages import AIMessage
from langchain_core.tools import BaseTool
from langgraph.graph import END
from langgraph.prebuilt import ToolNode
from langgraph.runtime import Runtime
from langgraph.types import Command

TOOL_NAME = "deep_research_runtime_viability_probe"
TOOL_PATH = "tests.fixtures.reflected_runtime_tool:runtime_viability_probe"
COMMAND_TOOL_NAME = "deep_research_command_viability_probe"
COMMAND_TOOL_PATH = "tests.fixtures.reflected_runtime_tool:command_viability_probe"
CONTROL_TOOL_NAME = "deep_research"
CONTROL_TOOL_PATH = "deerflow_deep_research.tool:deep_research_tool"


def _config_with_reflected_probe() -> AppConfig:
    return AppConfig(
        sandbox={"use": "deerflow.sandbox.local:LocalSandboxProvider"},
        tools=[ToolConfig(name=TOOL_NAME, group="deep-research-viability", use=TOOL_PATH)],
    )


def _config_with_reflected_command_probe() -> AppConfig:
    return AppConfig(
        sandbox={"use": "deerflow.sandbox.local:LocalSandboxProvider"},
        tools=[ToolConfig(name=COMMAND_TOOL_NAME, group="deep-research-viability", use=COMMAND_TOOL_PATH)],
    )


def _config_with_reflected_control_tool() -> AppConfig:
    return AppConfig(
        sandbox={"use": "deerflow.sandbox.local:LocalSandboxProvider"},
        tools=[ToolConfig(name=CONTROL_TOOL_NAME, group="deep-research-control", use=CONTROL_TOOL_PATH)],
    )


def test_reflected_control_tool_exposes_expanded_lifecycle_schema_without_new_config() -> None:
    loaded = get_available_tools(
        groups=["deep-research-control"],
        include_mcp=False,
        app_config=_config_with_reflected_control_tool(),
    )
    control = next(tool for tool in loaded if tool.name == CONTROL_TOOL_NAME)
    schema = control.get_input_schema().model_json_schema()

    assert control.coroutine is not None
    assert set(schema["properties"]) == {"action", "probe_id", "research_id"}
    assert "infra_probe|start|resume|status|cancel" in control.description
    assert CONTROL_TOOL_PATH == "deerflow_deep_research.tool:deep_research_tool"


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


@pytest.mark.asyncio
async def test_reflected_async_tool_preserves_outer_command_and_human_input_artifact() -> None:
    loaded = get_available_tools(
        groups=["deep-research-viability"],
        include_mcp=False,
        app_config=_config_with_reflected_command_probe(),
    )
    probe = next(tool for tool in loaded if tool.name == COMMAND_TOOL_NAME)
    state = {
        "messages": [
            AIMessage(
                content="",
                tool_calls=[{"name": COMMAND_TOOL_NAME, "args": {"payload": "ping"}, "id": "command-call"}],
            )
        ]
    }
    runtime = Runtime(context={"user_id": "viability-user", "thread_id": "viability-thread"})
    result = await ToolNode([probe]).ainvoke(state, config={"configurable": {"__pregel_runtime": runtime}})

    assert isinstance(result, list)
    assert len(result) == 1
    command = result[0]
    assert isinstance(command, Command)
    assert command.goto == END
    message = command.update["messages"][0]
    assert message.tool_call_id == "command-call"
    assert message.name == COMMAND_TOOL_NAME
    assert message.id == "viability-human-input"
    assert message.artifact["human_input"] == {
        "version": 1,
        "kind": "human_input_request",
        "source": "deep_research",
        "request_id": "viability-human-input",
        "mode": "text",
        "title": "implementation_mode=full_fake viability",
        "context": "implementation_mode=full_fake viability fixture",
    }
