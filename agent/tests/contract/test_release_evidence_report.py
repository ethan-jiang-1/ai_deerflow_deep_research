"""DPT invariant parity and release-evidence report contract.

@impl EVH-002
@impl EVH-003
@impl EVH-004
@impl EVH-005
"""

from __future__ import annotations

from pathlib import Path


def test_release_evidence_report_keeps_achieved_and_outstanding_proof_explicit() -> None:
    path = Path("docs/dpt-invariant-parity-release-report-2026-07-17.md")
    text = path.read_text(encoding="utf-8")

    assert "Release verdict: NOT READY" in text
    assert "2 of 3" in text
    assert "Full-real acceptance: not executed" in text
    assert "final artifact materialization: achieved deterministically" in text
    assert "full-real unproved" in text
    for evidence_axis in ("Quality", "Resilience", "Cost", "Security"):
        assert f"## {evidence_axis} Evidence" in text
    for authority in ("checkpointed ResearchState", "accepted-submission ledger", "sandbox filesystem"):
        assert authority in text
    assert "A single successful demo is not release proof." in text
