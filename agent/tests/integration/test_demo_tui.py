"""Pilot coverage for the standalone Deep Research lifecycle demo TUI."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from demo_tui import DeepResearchDemoTUI  # noqa: E402


async def _wait_for(app: DeepResearchDemoTUI, pilot, stage: str, max_wait: float = 3.0) -> None:
    elapsed = 0.0
    while elapsed < max_wait and app.stage != stage:
        await pilot.pause()
        await asyncio.sleep(0.02)
        elapsed += 0.02
    assert app.stage == stage


async def _reach_hitl2(app: DeepResearchDemoTUI, pilot) -> None:
    await pilot.press("enter")
    await _wait_for(app, pilot, "hitl1")
    await pilot.press(*"profile")
    await pilot.press("enter")
    await _wait_for(app, pilot, "hitl2")


@pytest.mark.asyncio
async def test_demo_tui_happy_path_shows_both_interrupts_and_terminal() -> None:
    app = DeepResearchDemoTUI()
    async with app.run_test() as pilot:
        await pilot.pause()
        assert "full_fake" in app.query_one("#banner").render().plain
        await _reach_hitl2(app, pilot)
        assert len(app.request_ids) == 2
        await pilot.press(*"proceed")
        await pilot.press("enter")
        await _wait_for(app, pilot, "terminal")

    assert app.last_result["code"] == "completed"
    assert app.last_result["implementation_mode"] == "full_fake"


@pytest.mark.asyncio
async def test_demo_tui_invalid_decision_does_not_resume() -> None:
    app = DeepResearchDemoTUI()
    async with app.run_test() as pilot:
        await _reach_hitl2(app, pilot)
        before = app.resume_invocations
        await pilot.press(*"not-an-option")
        await pilot.press("enter")
        await pilot.pause()
        assert app.stage == "hitl2"
        assert app.resume_invocations == before
        assert "not-an-option" not in app.last_result


@pytest.mark.asyncio
async def test_demo_tui_explicit_cancel_uses_lifecycle_action() -> None:
    app = DeepResearchDemoTUI()
    async with app.run_test() as pilot:
        await pilot.press("enter")
        await _wait_for(app, pilot, "hitl1")
        await pilot.click("#cancel")
        await _wait_for(app, pilot, "terminal")

    assert app.last_result["code"] == "cancelled"
    assert app.last_result["status"] == "cancelled"
