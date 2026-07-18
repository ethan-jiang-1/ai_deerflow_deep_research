"""Scheduled/manual live workflow contracts.

@impl EVH-005
@impl EVH-009
"""

from __future__ import annotations

from pathlib import Path


def test_live_workflow_has_strict_preflight_secrets_and_report_upload() -> None:
    workflow = Path("../.github/workflows/agent-live-evaluation.yml").read_text(encoding="utf-8")

    assert "schedule:" not in workflow
    assert "workflow_dispatch:" in workflow
    assert "secrets.ANTHROPIC_API_KEY" in workflow
    assert "secrets.TAVILY_API_KEY" in workflow
    assert "scripts/live_preflight.py --require-web" in workflow
    assert "make test-live" in workflow
    assert "actions/upload-artifact@v4" in workflow
    assert "agent/.reports/live" in workflow


def test_six_case_live_workflow_remains_manual_until_measured_lane_passes() -> None:
    workflow = Path("../.github/workflows/agent-live-evaluation.yml").read_text(encoding="utf-8")

    assert "workflow_dispatch:" in workflow
    assert "cron:" not in workflow
    assert "make test-live" in workflow
