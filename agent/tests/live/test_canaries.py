"""Shortest credentialed real-prefix canaries through the public entry.

@impl EVH-005
@impl EVH-009
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from tests.scenarios.canaries import LIVE_CANARIES, run_live_canary
from tests.scenarios.live import LiveScenarioFailure, write_live_report

pytestmark = pytest.mark.requires_llm


@pytest.mark.parametrize("scenario", LIVE_CANARIES, ids=lambda scenario: scenario.scenario_id)
async def test_live_prefix_canary(tmp_path, scenario) -> None:
    report_dir = os.environ.get("LIVE_REPORT_DIR")
    try:
        report = await run_live_canary(scenario, environ=os.environ, workspace=tmp_path)
    except LiveScenarioFailure as exc:
        if report_dir:
            write_live_report(exc.report, Path(report_dir))
        raise

    assert report.scenario_id == scenario.scenario_id
    assert report.attempt_count == 1
    assert report.retry_count == 0
    assert all(report.hard_invariants.values())
    if report_dir:
        write_live_report(report, Path(report_dir))
