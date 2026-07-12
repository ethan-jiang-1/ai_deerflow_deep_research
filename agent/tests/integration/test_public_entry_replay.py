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
RESEARCH_ID = "r_" + "A" * 43
REQUEST_ID = "drh_fixture_request"


class ReplayToolCallingModel(FakeMessagesListChatModel):
    """Replay committed assistant turns while accepting bound tools."""

    def bind_tools(  # type: ignore[override]
        self,
        tools: Any,
        *,
        tool_choice: Any = None,
        **kwargs: Any,
    ) -> Runnable:
        return self


@pytest.mark.parametrize("surface_path", [SKILL_PATH, SOUL_PATH], ids=["public-skill", "agent-soul"])
def test_entry_surface_replays_start_resume_and_fake_terminal_disclaimer(surface_path: Path) -> None:
    calls: list[dict[str, str]] = []

    @tool
    def deep_research(action: str, research_id: str | None = None) -> str:
        """Fake global Deep Research lifecycle control tool."""
        call = {"action": action}
        if research_id is not None:
            call["research_id"] = research_id
        calls.append(call)
        if action == "start":
            return json.dumps(
                {
                    "action": "start",
                    "code": "suspended",
                    "implementation_mode": "full_fake",
                    "research_id": RESEARCH_ID,
                    "request_id": REQUEST_ID,
                },
                sort_keys=True,
            )
        return json.dumps(
            {
                "action": "resume",
                "code": "completed",
                "implementation_mode": "full_fake",
                "research_id": RESEARCH_ID,
                "terminal_fixture_marker": "full_fake_terminal_fixture",
            },
            sort_keys=True,
        )

    surface = surface_path.read_text(encoding="utf-8")
    start_text = f"Development lifecycle suspended. Keep {RESEARCH_ID} for the matching reply. full_fake."
    start_model = ReplayToolCallingModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "deep_research",
                        "args": {"action": "start"},
                        "id": "start-call",
                        "type": "tool_call",
                    }
                ],
            ),
            AIMessage(content=start_text),
        ]
    )
    started = create_agent(model=start_model, tools=[deep_research], system_prompt=surface).invoke(
        {"messages": [{"role": "user", "content": "Research the question using multiple sources."}]}
    )

    terminal_text = "The full_fake lifecycle fixture reached a terminal state; no research output was produced."
    resume_model = ReplayToolCallingModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "deep_research",
                        "args": {"action": "resume", "research_id": RESEARCH_ID},
                        "id": "resume-call",
                        "type": "tool_call",
                    }
                ],
            ),
            AIMessage(content=terminal_text),
        ]
    )
    resumed = create_agent(model=resume_model, tools=[deep_research], system_prompt=surface).invoke(
        {"messages": [{"role": "user", "content": "proceed"}]}
    )

    assert calls == [{"action": "start"}, {"action": "resume", "research_id": RESEARCH_ID}]
    start_tool = next(message for message in started["messages"] if isinstance(message, ToolMessage))
    resume_tool = next(message for message in resumed["messages"] if isinstance(message, ToolMessage))
    assert json.loads(start_tool.content)["implementation_mode"] == "full_fake"
    assert json.loads(resume_tool.content)["implementation_mode"] == "full_fake"
    assert RESEARCH_ID in started["messages"][-1].content
    assert resumed["messages"][-1].content == terminal_text
    assert all(term not in terminal_text.casefold() for term in ("findings", "report", "completed research"))


@pytest.mark.parametrize("surface_path", [SKILL_PATH, SOUL_PATH], ids=["public-skill", "agent-soul"])
def test_entry_surface_keeps_control_guidance_bounded(surface_path: Path) -> None:
    surface = surface_path.read_text(encoding="utf-8").casefold()
    for required in (
        "implementation_mode=full_fake",
        'action="start"',
        'action="resume"',
        "research_id",
        "sole tool call",
        "status",
        "cancel",
        "non-interactive",
        "known im",
    ):
        assert required in surface
    for forbidden in (
        "stategraph",
        "fixture controls",
        "phase prompt",
        "security isolation",
        "authorization boundary",
        "answer=",
    ):
        assert forbidden not in surface
