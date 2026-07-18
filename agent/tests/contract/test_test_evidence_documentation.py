"""Human test-evidence guidance stays aligned without copying catalogs.

@impl EVH-001
@impl EVH-002
@impl EVH-005
@impl EVH-009
@impl EVH-010
"""

from __future__ import annotations

import re
from pathlib import Path


def test_readme_and_agent_guide_share_stable_test_evidence_vocabulary() -> None:
    readme = Path("README.md").read_text(encoding="utf-8")
    guide = Path("AGENTS.md").read_text(encoding="utf-8")

    for text in (readme, guide):
        assert "TestEvidenceClaim" in text
        assert "scripted case" in text
        assert re.search(r"provider-shape\s+fixture", text)
        assert re.search(r"persisted\s+trace replay", text, flags=re.IGNORECASE)
        assert "evidence-v1" in text
        assert "release-attestation-2026-07-17.json" in text
        assert "sole `FULL_REAL_PIPELINE`" in text or "single full-pipeline" in text


def test_live_baseline_and_workflow_disclose_current_partial_lane() -> None:
    baseline = Path("docs/live-evaluation-baseline-2026-07-17.md").read_text(encoding="utf-8")
    workflow = Path("../.github/workflows/agent-live-evaluation.yml").read_text(encoding="utf-8")

    assert "Four cases passed" in baseline
    assert "Wave2 synthesis failed closed" in baseline
    assert "targeted evidence failed closed" in baseline
    assert "workflow_dispatch:" in workflow
    assert "schedule:" not in workflow


def test_governance_bootstrap_pointers_remain_concise_and_aligned() -> None:
    config = Path("../openspec/config.yaml").read_text(encoding="utf-8")
    governance = Path("../openspec/governance/README.md").read_text(encoding="utf-8")

    assert "openspec/governance/test-evidence-policy.md" in config
    assert "test-evidence-policy.md" in governance
    assert "evaluation-hardening" in config
    assert "evaluation-hardening" in governance
