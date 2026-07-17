"""Manual/reusable release workflow contracts.

@impl EVH-005
@impl EVH-009
"""

from __future__ import annotations

from pathlib import Path


def test_release_workflow_depends_on_deterministic_gate_and_uploads_report() -> None:
    workflow = Path("../.github/workflows/agent-release-e2e.yml").read_text(encoding="utf-8")

    assert "workflow_dispatch:" in workflow
    assert "workflow_call:" in workflow
    assert "needs: deterministic" in workflow
    assert "make test-assets" in workflow
    assert "make test-req-coverage" in workflow
    assert "make test" in workflow
    assert 'RELEASE_E2E_CONFIRM: "1"' in workflow
    assert "scripts/release_preflight.py" in workflow
    assert "make test-release-e2e" in workflow
    assert "actions/upload-artifact@v4" in workflow
    assert "agent/.reports/release" in workflow
