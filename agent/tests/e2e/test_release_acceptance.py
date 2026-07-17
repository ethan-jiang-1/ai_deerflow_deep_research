"""Manual full-real acceptance from the public entry.

@impl EVH-004
@impl EVH-005
@impl EVH-009
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from tests.scenarios.release import (
    RELEASE_SCENARIO,
    ReleaseAcceptanceFailure,
    ReleaseRunner,
    execute_full_real_release,
    new_release_invocation,
    preflight_release_environment,
)

pytestmark = [pytest.mark.requires_llm, pytest.mark.release_e2e]


async def test_full_real_release_acceptance(tmp_path) -> None:
    preflight_release_environment(environ=os.environ)
    invocation = new_release_invocation()

    async def execute(scenario, selected_invocation):
        return await execute_full_real_release(
            scenario,
            selected_invocation,
            environ=os.environ,
            workspace=tmp_path,
        )

    try:
        report = await ReleaseRunner(executor=execute, max_attempts=1).run(RELEASE_SCENARIO, invocation)
    except ReleaseAcceptanceFailure as exc:
        report = exc.report
        _write_report(report)
        raise
    _write_report(report)


def _write_report(report) -> None:
    report_dir = os.environ.get("RELEASE_REPORT_DIR")
    if not report_dir:
        return
    directory = Path(report_dir)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{report.scenario_id}.json"
    path.write_text(json.dumps(report.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
