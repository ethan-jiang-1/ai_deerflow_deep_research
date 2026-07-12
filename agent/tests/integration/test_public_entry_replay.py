"""Zero-API replay contract for the public Deep Research entry surfaces."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from langchain.agents import create_agent
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.runnables import Runnable
from langchain_core.tools import tool

REPO_ROOT = Path(__file__).resolve().parents[3]
SKILL_PATH = REPO_ROOT / "agent/config/public-skill/deep-research-controller/SKILL.md"
SOUL_PATH = REPO_ROOT / "agent/config/agent-template/SOUL.md"


class ReplayToolCallingModel(FakeMessagesListChatModel):
    """Replay two committed assistant turns while accepting bound tools."""

    def bind_tools(  # type: ignore[override]
        self,
        tools: Any,
        *,
        tool_choice: Any = None,
        **kwargs: Any,
    ) -> Runnable:
        return self


@pytest.mark.parametrize("surface_path", [SKILL_PATH, SOUL_PATH], ids=["public-skill", "agent-soul"])
def test_entry_surface_routes_to_control_tool_and_surfaces_typed_unavailability(surface_path: Path) -> None:
    calls: list[str] = []

    @tool
    def deep_research(request: str) -> str:
        """Fake global Deep Research control tool."""
        calls.append(request)
        return json.dumps(
            {
                "ok": False,
                "code": "action_unavailable",
                "available_actions": ["infra_probe"],
            },
            sort_keys=True,
        )

    final_text = "The requested Deep Research capability is unavailable in the current runtime."
    model = ReplayToolCallingModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "deep_research",
                        "args": {"request": "Research the evidence for the user's question."},
                        "id": "deep-research-entry-call",
                        "type": "tool_call",
                    }
                ],
            ),
            AIMessage(content=final_text),
        ]
    )
    surface = surface_path.read_text(encoding="utf-8")
    graph = create_agent(model=model, tools=[deep_research], system_prompt=surface)

    result = graph.invoke(
        {
            "messages": [
                {
                    "role": "user",
                    "content": "Please conduct multi-source research and give me a supported answer.",
                }
            ]
        }
    )

    tool_messages = [message for message in result["messages"] if isinstance(message, ToolMessage)]
    assert calls == ["Research the evidence for the user's question."]
    assert len(tool_messages) == 1
    assert json.loads(tool_messages[0].content)["code"] == "action_unavailable"
    assert result["messages"][-1].content == final_text
    assert "deep_research" in surface
    forbidden_claims = (
        "research started",
        "resume is available",
        "human review is available",
        "only tool",
        "phase prompt",
    )
    combined = f"{surface}\n{final_text}".casefold()
    assert all(claim not in combined for claim in forbidden_claims)
