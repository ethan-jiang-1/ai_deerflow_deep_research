"""Hard viability gate for cancellation across a reflected nested graph."""

from __future__ import annotations

import asyncio
import importlib
from pathlib import Path

import pytest
from deerflow.config.app_config import AppConfig
from deerflow.config.tool_config import ToolConfig
from deerflow.tools.tools import get_available_tools
from langchain_core.messages import AIMessage
from langgraph.prebuilt import ToolNode
from langgraph.runtime import Runtime

TOOL_NAME = "deep_research_cancellation_viability_probe"
TOOL_PATH = "tests.fixtures.reflected_runtime_tool:cancellation_viability_probe"


def _config_with_reflected_probe() -> AppConfig:
    return AppConfig(
        sandbox={"use": "deerflow.sandbox.local:LocalSandboxProvider"},
        tools=[ToolConfig(name=TOOL_NAME, group="deep-research-viability", use=TOOL_PATH)],
    )


@pytest.mark.asyncio
async def test_outer_tool_cancellation_terminates_nested_graph() -> None:
    loaded = get_available_tools(
        groups=["deep-research-viability"],
        include_mcp=False,
        app_config=_config_with_reflected_probe(),
    )
    probe = next(tool for tool in loaded if tool.name == TOOL_NAME)
    fixture_module = importlib.import_module("tests.fixtures.reflected_runtime_tool")
    control = fixture_module.reset_cancellation_control()

    outer_runtime = Runtime(context={"user_id": "viability-user"})
    config = {"configurable": {"__pregel_runtime": outer_runtime}}
    state = {
        "messages": [
            AIMessage(
                content="",
                tool_calls=[{"name": TOOL_NAME, "args": {"payload": "wait"}, "id": "cancel-call"}],
            )
        ]
    }

    outer_task = asyncio.create_task(ToolNode([probe]).ainvoke(state, config=config))
    await asyncio.wait_for(control.started.wait(), timeout=2)
    outer_task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await outer_task
    await asyncio.wait_for(control.terminated.wait(), timeout=2)

    assert not control.release.is_set()
    assert control.active_nodes == 0


def test_downstream_source_does_not_use_private_gateway_cancellation_state() -> None:
    source_root = Path(__file__).resolve().parents[2] / "src" / "deerflow_deep_research"
    source = "\n".join(path.read_text(encoding="utf-8") for path in source_root.rglob("*.py"))

    assert "abort_event" not in source
    assert "__run_journal" not in source
