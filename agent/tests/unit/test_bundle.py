"""Pure change-02 bundle layout, path containment, and authority boundary (REG-009, REG-010)."""

from __future__ import annotations

import pytest

from deerflow_deep_research.domain.bundle import (
    BUNDLE_ROOT,
    BUNDLE_SUBTREES,
    DIAGNOSTICS_GATE_ATTEMPTS,
    attempt_dir,
    bundle_root,
    canonicalize_source_url,
    dedupe_source_urls,
    diagnostics_path,
    is_audit_only,
    resolve_contained_path,
)
from deerflow_deep_research.domain.state import ResearchState

RESEARCH_ID = "r_" + "A" * 43
WORK_ID = "w1"
ATTEMPT_ID = "g0-wave0-a1"


def test_bundle_root_is_research_id_scoped() -> None:
    assert bundle_root(RESEARCH_ID) == f"{BUNDLE_ROOT}/{RESEARCH_ID}"


def test_bundle_declares_minimal_subtrees() -> None:
    assert set(BUNDLE_SUBTREES) == {
        "request",
        "work",
        "evidence",
        "synthesis",
        "review",
        "final",
        "diagnostics",
    }


def test_attempt_dir_scopes_a_worker_write_root() -> None:
    assert attempt_dir(RESEARCH_ID, WORK_ID, ATTEMPT_ID) == f"{BUNDLE_ROOT}/{RESEARCH_ID}/work/{WORK_ID}/{ATTEMPT_ID}"


def test_in_containment_write_is_accepted() -> None:
    path = f"{BUNDLE_ROOT}/{RESEARCH_ID}/work/{WORK_ID}/{ATTEMPT_ID}/outputs/page.html"
    assert resolve_contained_path(path, research_id=RESEARCH_ID, work_id=WORK_ID, attempt_id=ATTEMPT_ID) == path


def test_out_of_attempt_write_is_rejected() -> None:
    # A worker cannot write into another work/attempt directory.
    path = f"{BUNDLE_ROOT}/{RESEARCH_ID}/work/w2/g0-w2-a1/outputs/page.html"
    with pytest.raises(ValueError, match="path_not_contained"):
        resolve_contained_path(path, research_id=RESEARCH_ID, work_id=WORK_ID, attempt_id=ATTEMPT_ID)


def test_parent_traversal_escape_is_rejected() -> None:
    path = f"{BUNDLE_ROOT}/{RESEARCH_ID}/work/{WORK_ID}/{ATTEMPT_ID}/../../w2/g0-w2-a1/x"
    with pytest.raises(ValueError, match="path_not_contained"):
        resolve_contained_path(path, research_id=RESEARCH_ID, work_id=WORK_ID, attempt_id=ATTEMPT_ID)


def test_absolute_path_is_rejected() -> None:
    with pytest.raises(ValueError, match="path_not_contained"):
        resolve_contained_path("/etc/passwd", research_id=RESEARCH_ID, work_id=WORK_ID, attempt_id=ATTEMPT_ID)


def test_diagnostics_path_is_audit_only() -> None:
    path = diagnostics_path(RESEARCH_ID)
    assert path.endswith(f"diagnostics/{DIAGNOSTICS_GATE_ATTEMPTS}")
    assert is_audit_only(path)


def test_unknown_diagnostic_is_rejected() -> None:
    with pytest.raises(ValueError, match="diagnostic_unknown"):
        diagnostics_path(RESEARCH_ID, "phase_cursor.json")


def test_canonical_source_url_dedupes_trivial_variants() -> None:
    assert canonicalize_source_url("HTTPS://Example.com/a/") == "https://example.com/a"
    assert canonicalize_source_url("https://example.com/a#frag") == "https://example.com/a"


def test_dedupe_source_urls_collapses_duplicates() -> None:
    deduped = dedupe_source_urls(["https://example.com/a/", "https://example.com/a#x", "https://example.com/b"])
    assert deduped == ("https://example.com/a", "https://example.com/b")


def test_accepted_submission_refs_is_a_ledger_ref_slot() -> None:
    # REG-009: accepted_submission_refs holds references into the validated submission
    # ledger (strings), not ledger records, file paths, or worker text. It is the only
    # slot that marks accepted submissions.
    hints = ResearchState.__annotations__
    assert "accepted_submission_refs" in hints
    # No field treats file existence or worker text as accepted coverage.
    assert "accepted_files" not in hints
    assert "worker_text_accepted" not in hints


def test_no_second_phase_cursor_field_exists() -> None:
    hints = ResearchState.__annotations__
    assert "phase_cursor" not in hints
    assert "rb_status" not in hints
    # diagnostics is not a state field; it lives only in the sandbox bundle as audit-only.
    assert "diagnostics" not in hints
