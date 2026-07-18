"""Agent PR workflow runs every focused deterministic lane.

@impl EVH-009
"""

from pathlib import Path


def test_agent_pr_workflow_runs_governance_and_three_focused_lanes() -> None:
    workflow = Path("../.github/workflows/agent-tests.yml").read_text(encoding="utf-8")

    assert "pull_request:" in workflow
    assert workflow.count("make test-assets") == 1
    assert workflow.count("make test-fast") == 1
    assert workflow.count("make test-integration") == 1
    assert workflow.count("make test-workflow") == 1
    assert "- run: make test\n" not in workflow
