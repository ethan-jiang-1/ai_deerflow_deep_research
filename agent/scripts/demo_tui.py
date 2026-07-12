#!/usr/bin/env python3
"""Standalone Textual visualization of the Change 01 full-fake lifecycle.

@impl RED-001
@impl RED-002
"""

from __future__ import annotations

import json
from typing import Any, Literal

from demo import DemoAdapter, _runtime, _suspension, _tool_call
from langchain_core.messages import HumanMessage
from langgraph.types import Command
from rich.syntax import Syntax
from rich.text import Text
from textual.app import App, ComposeResult
from textual.containers import Horizontal
from textual.widgets import Button, Footer, Input, RichLog, Static

from deerflow_deep_research.runtime.control import build_control_graph_host
from deerflow_deep_research.tool import run_deep_research

Stage = Literal["question", "hitl1", "hitl2", "terminal"]


class DeepResearchDemoTUI(App[None]):
    """A thin presentation shell; lifecycle authority stays in the real graph."""

    CSS = """
    Screen { layout: vertical; background: #0b1020; color: #e5e7eb; }
    #banner { height: 4; padding: 1 2; background: #16213e; color: #7dd3fc; text-style: bold; }
    #log { height: 1fr; border: round #334155; margin: 1 2; padding: 0 1; }
    #prompt { height: auto; margin: 0 2; color: #fbbf24; text-style: bold; }
    #controls { height: 3; margin: 0 2 1 2; }
    #composer { width: 1fr; }
    #cancel { width: 14; margin-left: 1; }
    """

    BINDINGS = [("ctrl+c", "quit", "Quit")]

    def __init__(self) -> None:
        super().__init__()
        self.stage: Stage = "question"
        self.host = build_control_graph_host(fingerprint_verifier=lambda _app_config: None)
        self.adapter = DemoAdapter()
        self.messages: list[Any] = []
        self.research_id: str | None = None
        self.pending: dict[str, Any] | None = None
        self.request_ids: list[str] = []
        self.last_result: dict[str, Any] = {}
        self.resume_invocations = 0

    def compose(self) -> ComposeResult:
        yield Static(
            Text(
                "Deep Research lifecycle demo · ZERO API · implementation_mode=full_fake\n"
                "Standalone visualization only — no findings or report are produced",
                style="bold cyan",
            ),
            id="banner",
        )
        yield RichLog(id="log", wrap=True, markup=True)
        yield Static("Enter a demo research request", id="prompt")
        with Horizontal(id="controls"):
            yield Input(
                value="Compare renewable-energy storage approaches",
                placeholder="Research request",
                id="composer",
            )
            yield Button("Cancel lifecycle", id="cancel", variant="error", disabled=True)
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#composer", Input).focus()
        self._write("Ready. Press Enter to start the real full-fake lifecycle.", "cyan")

    def _write(self, message: str, style: str = "") -> None:
        self.query_one("#log", RichLog).write(Text(message, style=style))

    def _write_payload(self, label: str, payload: dict[str, Any]) -> None:
        self._write(f"\n{label}", "bold green")
        self.query_one("#log", RichLog).write(
            Syntax(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), "json", word_wrap=True)
        )

    def _set_prompt(self, text: str, placeholder: str = "") -> None:
        self.query_one("#prompt", Static).update(text)
        composer = self.query_one("#composer", Input)
        composer.value = ""
        composer.placeholder = placeholder
        composer.disabled = self.stage == "terminal"
        if not composer.disabled:
            composer.focus()

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        value = event.value.strip()
        if not value:
            self._write("Input cannot be empty.", "bold red")
            return
        if self.stage == "question":
            await self._start(value)
        elif self.stage == "hitl1":
            await self._resume_hitl1(value)
        elif self.stage == "hitl2":
            await self._resume_hitl2(value.lower())

    async def _start(self, question: str) -> None:
        start_user = HumanMessage(content=question, id="demo-tui-human-start")
        start_call = _tool_call("start", "demo-tui-call-start")
        result = await run_deep_research(
            action="start",
            probe_id=None,
            runtime=_runtime([start_user, start_call], "demo-tui-call-start"),
            adapter=self.adapter,
            host_factory=lambda: self.host,
        )
        if not isinstance(result, Command):
            self._fail("Start failed", result)
            return
        control, request = _suspension(result)
        self.messages = [start_user]
        self.research_id = control["research_id"]
        self.pending = request
        self.request_ids.append(request["request_id"])
        self.last_result = control
        self.stage = "hitl1"
        self.query_one("#cancel", Button).disabled = False
        self._write_payload("START / SUSPENDED", control)
        self._write_payload("HITL1 REQUEST", request)
        self._set_prompt("HITL1 · enter a profile/scope response", "Use broad public sources")

    async def _resume_hitl1(self, value: str) -> None:
        assert self.pending is not None and self.research_id is not None
        response = self._response_message(
            value=value,
            message_id="demo-tui-human-hitl1",
            response_kind="text",
        )
        self.messages.append(response)
        call = _tool_call("resume", "demo-tui-call-resume-1", self.research_id)
        self.resume_invocations += 1
        result = await run_deep_research(
            action="resume",
            probe_id=None,
            research_id=self.research_id,
            runtime=_runtime([*self.messages, call], "demo-tui-call-resume-1"),
            adapter=self.adapter,
            host_factory=lambda: self.host,
        )
        if not isinstance(result, Command):
            self._fail("HITL1 resume failed", result)
            return
        control, request = _suspension(result)
        self.pending = request
        self.request_ids.append(request["request_id"])
        self.last_result = control
        self.stage = "hitl2"
        options = ", ".join(option["value"] for option in request["options"])
        self._write_payload("RESUME / SUSPENDED", control)
        self._write_payload("HITL2 REQUEST", request)
        self._set_prompt(f"HITL2 · choose: {options}", "proceed")

    async def _resume_hitl2(self, value: str) -> None:
        assert self.pending is not None and self.research_id is not None
        advertised = {option["value"] for option in self.pending.get("options", [])}
        if value not in advertised:
            self._write(f"Invalid decision: {value}. Choose one of: {', '.join(sorted(advertised))}", "bold red")
            return
        response = self._response_message(
            value=value,
            message_id="demo-tui-human-hitl2",
            response_kind="option",
        )
        self.messages.append(response)
        call = _tool_call("resume", "demo-tui-call-resume-2", self.research_id)
        self.resume_invocations += 1
        result = await run_deep_research(
            action="resume",
            probe_id=None,
            research_id=self.research_id,
            runtime=_runtime([*self.messages, call], "demo-tui-call-resume-2"),
            adapter=self.adapter,
            host_factory=lambda: self.host,
        )
        if isinstance(result, Command):
            control, request = _suspension(result)
            self.pending = request
            self.request_ids.append(request["request_id"])
            self.last_result = control
            self._write_payload("ROUTE / SUSPENDED", control)
            self._write_payload("NEXT HITL REQUEST", request)
            self._set_prompt("Another decision is required", "proceed")
            return
        self._finish(result)

    def _response_message(self, *, value: str, message_id: str, response_kind: str) -> HumanMessage:
        assert self.pending is not None
        payload: dict[str, Any] = {
            "version": 1,
            "kind": "human_input_response",
            "source": "deep_research",
            "request_id": self.pending["request_id"],
            "response_kind": response_kind,
            "value": value,
        }
        if response_kind == "option":
            payload["option_id"] = value
        return HumanMessage(
            content=value,
            id=message_id,
            additional_kwargs={"human_input_response": payload},
        )

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id != "cancel" or self.stage not in {"hitl1", "hitl2"} or self.research_id is None:
            return
        call = _tool_call("cancel", "demo-tui-call-cancel", self.research_id)
        result = await run_deep_research(
            action="cancel",
            probe_id=None,
            research_id=self.research_id,
            runtime=_runtime([*self.messages, call], "demo-tui-call-cancel"),
            adapter=self.adapter,
            host_factory=lambda: self.host,
        )
        if isinstance(result, Command):
            self._fail("Cancel unexpectedly suspended", {})
            return
        self._finish(result)

    def _finish(self, result: dict[str, Any]) -> None:
        self.last_result = result
        self.stage = "terminal"
        self.pending = None
        self._write_payload("TERMINAL RESULT", result)
        self._write("Lifecycle finished. This fixture is not completed research.", "bold yellow")
        self.query_one("#cancel", Button).disabled = True
        self._set_prompt("Demo complete · Ctrl+C to exit")

    def _fail(self, label: str, result: Any) -> None:
        self.last_result = result if isinstance(result, dict) else {"detail": str(result)}
        self.stage = "terminal"
        self._write_payload(label, self.last_result)
        self._set_prompt("Demo stopped · Ctrl+C to exit")


def main() -> None:
    DeepResearchDemoTUI().run()


if __name__ == "__main__":
    main()
