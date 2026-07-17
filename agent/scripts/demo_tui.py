#!/usr/bin/env python3
"""Standalone Textual visualization of the Deep Research real-mode lifecycle.

@impl RED-001
@impl RED-002

Set DEEPSEEK_API_KEY, ANTHROPIC_API_KEY, or OPENAI_API_KEY in the environment
(or in agent/.env — the Makefile passes --env-file .env to uv run).
"""

from __future__ import annotations

import json
import sys
from typing import Any, Literal

from _demo_core import (
    PHASE_META,
    DemoAdapter,
    _runtime,
    _suspension,
    _tool_call,
    build_demo_host,
    build_demo_recipe,
    check_credentials_available,
    create_hitl_response,
)
from langchain_core.messages import HumanMessage
from langgraph.types import Command
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text
from textual.app import App, ComposeResult
from textual.containers import Horizontal
from textual.widgets import Button, Footer, Input, RichLog, Static

from deerflow_deep_research.tool import run_deep_research

# ── pipeline order for visual tracker ──────────────────────────────────

PIPELINE_ORDER: tuple[str, ...] = (
    "bootstrap",
    "hitl1",
    "topic_planning",
    "wave0",
    "wave1",
    "wave2_synthesis",
    "targeted_evidence",
    "hitl2",
    "rerun",
    "readiness",
    "final_delivery",
)

Stage = Literal["question", "hitl1", "hitl2", "terminal"]


# ── rich helpers ────────────────────────────────────────────────────────


def _pipeline_tracker(completed: tuple[str, ...], active: str | None, suspended: bool) -> Table:
    """Render an 11-phase pipeline progress table."""
    table = Table(show_header=False, expand=True, padding=(0, 1))
    table.add_column("marker", width=2)
    table.add_column("phase", width=14)
    table.add_column("desc", width=22)
    for name in PIPELINE_ORDER:
        label, desc = PHASE_META.get(name, (name, ""))
        if name in completed:
            marker = "[green]✓[/]"
            style = "dim green"
        elif name == active and suspended:
            marker = "[bold yellow]⏸[/]"
            style = "bold yellow"
        elif name == active:
            marker = "[bold cyan]●[/]"
            style = "bold cyan"
        else:
            marker = " ·"
            style = "dim"
        table.add_row(marker, f"[{style}]{label}[/]", f"[{style}]{desc}[/]")
    return table


def _welcome_text() -> Panel:
    """Render the welcome / onboarding guide."""
    guide = Text()
    guide.append("Deep Research — 11-Phase Pipeline\n\n", style="bold cyan")
    guide.append(
        "You enter a research question. The graph drives the full lifecycle:\n"
        "bootstrap → HITL-1 (scope) → topic planning → "
        "Wave 0/1/2 → HITL-2 (decide) → report.\n\n",
        style="white",
    )
    guide.append("How to use:\n", style="bold yellow")
    guide.append("  1. Type a research question and press Enter.\n")
    guide.append("  2. When HITL-1 (研究配置) asks for scope, describe what to cover.\n")
    guide.append("  3. When HITL-2 (决策) offers options, type one to choose.\n")
    guide.append("  4. Watch each phase tick by; Ctrl+C to quit.\n\n")
    guide.append("Each [bold]LLM call[/] and [bold]tool use[/] runs against the real API.\n", style="italic")
    return Panel(guide, title="Welcome", border_style="cyan")


# ── TUI app ─────────────────────────────────────────────────────────────


class DeepResearchDemoTUI(App[None]):
    """A thin presentation shell; lifecycle authority stays in the real graph."""

    CSS = """
    Screen { layout: vertical; background: #0b1020; color: #e5e7eb; }
    #banner { height: 3; padding: 1 2; background: #16213e; color: #7dd3fc; text-style: bold; }
    #pipeline { height: auto; margin: 1 2 1 2; min-height: 13; }
    #log { height: 1fr; border: round #334155; margin: 0 2; padding: 0 1; }
    #prompt { height: auto; margin: 0 2; color: #fbbf24; text-style: bold; }
    #controls { height: 3; margin: 0 2 1 2; }
    #composer { width: 1fr; }
    #cancel { width: 14; margin-left: 1; }
    """

    BINDINGS = [("ctrl+c", "quit", "Quit")]

    def __init__(self, *, _recipe: Any = None) -> None:
        super().__init__()
        self.stage: Stage = "question"
        self.adapter = DemoAdapter()
        if _recipe is not None:
            recipe = _recipe
        else:
            recipe = build_demo_recipe(
                mode="real",
                work_unit_store_factory=self.adapter.create_work_unit_store,
            )
        self.host = build_demo_host(recipe=recipe)
        self.messages: list[Any] = []
        self.research_id: str | None = None
        self.pending: dict[str, Any] | None = None
        self.request_ids: list[str] = []
        self.last_result: dict[str, Any] = {}
        self.completed_phases: tuple[str, ...] = ()
        self.active_phase: str | None = None
        self.suspended: bool = False
        self.resume_invocations = 0

    def compose(self) -> ComposeResult:
        yield Static(
            Text("Deep Research · all-real pipeline demo", style="bold cyan"),
            id="banner",
        )
        yield Static(_welcome_text(), id="pipeline")
        yield RichLog(id="log", wrap=True, markup=True, max_lines=500)
        yield Static("Enter a research question ↓", id="prompt")
        with Horizontal(id="controls"):
            yield Input(
                value="Compare renewable-energy storage approaches",
                placeholder="Research question",
                id="composer",
            )
            yield Button("Cancel", id="cancel", variant="error", disabled=True)
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#composer", Input).focus()
        self._write("[bold cyan]Ready.[/] Type a question and press Enter.", "")

    def on_unmount(self) -> None:
        self.adapter.close()

    # ── display helpers ──────────────────────────────────────────────

    def _write(self, message: str, style: str = "") -> None:
        self.query_one("#log", RichLog).write(Text.from_markup(message) if style else message)

    def _write_payload(self, label: str, payload: dict[str, Any]) -> None:
        self._write(f"\n[bold green]{label}[/]", "")
        self.query_one("#log", RichLog).write(
            Syntax(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), "json", word_wrap=True)
        )

    def _refresh_pipeline(self, result_dict: dict[str, Any]) -> None:
        trace = tuple(result_dict.get("execution_trace", ()))
        phase = result_dict.get("phase")
        self.completed_phases = trace
        self.active_phase = phase
        table = _pipeline_tracker(trace, phase, self.suspended)
        self.query_one("#pipeline", Static).update(table)

    def _set_prompt(self, text: str, placeholder: str = "") -> None:
        self.query_one("#prompt", Static).update(Text(text, style="bold yellow"))
        composer = self.query_one("#composer", Input)
        composer.value = ""
        composer.placeholder = placeholder
        composer.disabled = self.stage == "terminal"
        if not composer.disabled:
            composer.focus()

    # ── input routing ────────────────────────────────────────────────

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        value = event.value.strip()
        if not value:
            self._write("[bold red]Input cannot be empty.[/]", "")
            return
        if self.stage == "question":
            await self._start(value)
        elif self.stage == "hitl1":
            await self._resume_hitl1(value)
        elif self.stage == "hitl2":
            await self._resume_hitl2(value.lower())

    # ── start ────────────────────────────────────────────────────────

    async def _start(self, question: str) -> None:
        self._write(f"\n[bold]Research question:[/] {question}", "")
        self._write("[dim]Starting graph — bootstrap → HITL-1 …[/]", "")

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
        self.suspended = True
        self.query_one("#cancel", Button).disabled = False
        self._refresh_pipeline(control)

        # HITL-1: describe what the research should cover
        self._write_payload("HITL-1 REQUEST — 研究配置", request)
        self._write(
            "\n[yellow]The graph needs you to describe the research scope & profile.[/]",
            "",
        )
        self._write(
            "[dim]Examples: 'Use broad public sources', 'Focus on academic papers', "
            "'Cover only US market', 'Include Chinese sources'[/]",
            "",
        )
        self._set_prompt(
            "HITL-1 · Describe research scope / profile",
            "Use broad public sources",
        )

    # ── HITL-1 resume ────────────────────────────────────────────────

    async def _resume_hitl1(self, value: str) -> None:
        assert self.pending is not None and self.research_id is not None
        self._write(f"\n[dim]Scope response: {value}[/]", "")
        self._write("[dim]Resuming → topic_planning → wave0/1/2 …[/]", "")

        response = create_hitl_response(
            value=value,
            request_id=self.pending["request_id"],
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
            self._fail("HITL-1 resume failed", result)
            return
        control, request = _suspension(result)
        self.pending = request
        self.request_ids.append(request["request_id"])
        self.last_result = control
        self.stage = "hitl2"
        self._refresh_pipeline(control)
        options = ", ".join(option["value"] for option in request.get("options", []))
        self._write_payload("HITL-2 REQUEST — 决策", request)
        self._write(
            f"\n[yellow]Choose one of the advertised options: [bold]{options}[/][/]",
            "",
        )
        self._set_prompt(f"HITL-2 · choose: {options}", "proceed")

    # ── HITL-2 resume ────────────────────────────────────────────────

    async def _resume_hitl2(self, value: str) -> None:
        assert self.pending is not None and self.research_id is not None
        advertised = {option["value"] for option in self.pending.get("options", [])}
        if value not in advertised:
            self._write(
                f"[bold red]Invalid: {value}. Choose: {', '.join(sorted(advertised))}[/]",
                "",
            )
            return

        self._write(f"\n[dim]Decision: {value}[/]", "")
        self._write("[dim]Resuming → remaining phases …[/]", "")

        response = create_hitl_response(
            value=value,
            request_id=self.pending["request_id"],
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
            self._refresh_pipeline(control)
            self._write_payload("SUSPENDED", control)
            self._write_payload("NEXT HITL REQUEST", request)
            self._set_prompt("Another decision is required", "proceed")
            return
        self._finish(result)

    # ── cancel ──────────────────────────────────────────────────────

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id != "cancel" or self.stage not in {"hitl1", "hitl2"} or self.research_id is None:
            return
        self._write("\n[bold red]Cancelling lifecycle…[/]", "")
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

    # ── terminal states ──────────────────────────────────────────────

    def _finish(self, result: dict[str, Any]) -> None:
        self.last_result = result
        self.stage = "terminal"
        self.pending = None
        self.suspended = False
        self._refresh_pipeline(result)
        self._write_payload("TERMINAL RESULT", result)
        self._write("\n[bold yellow]✓ Lifecycle finished.[/]", "")
        self.query_one("#cancel", Button).disabled = True
        self._set_prompt("Demo complete · Ctrl+C to exit")

    def _fail(self, label: str, result: Any) -> None:
        self.last_result = result if isinstance(result, dict) else {"detail": str(result)}
        self.stage = "terminal"
        self.suspended = False
        self._write_payload(f"[bold red]{label}[/]", self.last_result)
        self._set_prompt("Demo stopped · Ctrl+C to exit")


def main() -> None:
    if not check_credentials_available():
        print(
            "❌ No API key found in environment.\n"
            "   Real-mode TUI requires model credentials.\n"
            "   Export one of: DEEPSEEK_API_KEY, ANTHROPIC_API_KEY, OPENAI_API_KEY and retry.",
            file=sys.stderr,
        )
        sys.exit(1)
    DeepResearchDemoTUI().run()


if __name__ == "__main__":
    main()
