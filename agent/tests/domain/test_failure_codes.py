"""@impl GAK-002 — FailureCode closed registry tests."""

from __future__ import annotations

import pytest

from deerflow_deep_research.domain.failure_codes import FailureCode, get_classification

VALID_CLASSIFICATIONS = frozenset({"hard", "semantic", "repairable", "degradable"})


def test_every_code_has_a_classification() -> None:
    for code in FailureCode:
        classification = get_classification(code)
        assert classification in VALID_CLASSIFICATIONS, (
            f"{code.value} → {classification!r} not in {VALID_CLASSIFICATIONS}"
        )


def test_no_duplicate_values() -> None:
    values = [code.value for code in FailureCode]
    assert len(values) == len(set(values)), f"duplicate values: {values}"


def test_all_required_codes_present() -> None:
    required = {
        FailureCode.MISSING_WORK_SPEC,
        FailureCode.WORK_TIMED_OUT,
        FailureCode.WORK_FAILED,
        FailureCode.WORK_CANCELLED,
        FailureCode.BUDGET_EXHAUSTED,
        FailureCode.INVALID_OUTPUT_SCHEMA,
        FailureCode.CONTENT_HASH_MISMATCH,
        FailureCode.MISSING_EVIDENCE,
        FailureCode.UNTRUSTED_SOURCE,
        FailureCode.IDENTITY_MISMATCH,
        FailureCode.SCHEMA_VERSION_UNSUPPORTED,
        FailureCode.REPAIR_BUDGET_EXHAUSTED,
        FailureCode.FATIGUE_ESCALATION,
        FailureCode.DEGRADED_EVIDENCE_QUALITY,
        FailureCode.INCOMPLETE_TOPIC_COVERAGE,
        FailureCode.REPAIR_TARGETED,
        FailureCode.REPAIR_SYNTHESIS,
        FailureCode.REPAIR_HITL2,
        FailureCode.EVIDENCE_INSUFFICIENT,
    }
    present = set(FailureCode)
    missing = required - present
    assert not missing, f"missing codes: {missing}"


def test_classification_consistency() -> None:
    """Hard codes cannot be repairable/degradable; system codes are hard."""
    hard = {
        FailureCode.MISSING_WORK_SPEC,
        FailureCode.WORK_CANCELLED,
        FailureCode.IDENTITY_MISMATCH,
        FailureCode.SCHEMA_VERSION_UNSUPPORTED,
        FailureCode.REPAIR_BUDGET_EXHAUSTED,
        FailureCode.FATIGUE_ESCALATION,
    }
    for code in hard:
        assert get_classification(code) == "hard", f"{code} should be hard"

    repairable = {
        FailureCode.WORK_TIMED_OUT,
        FailureCode.WORK_FAILED,
        FailureCode.INVALID_OUTPUT_SCHEMA,
        FailureCode.CONTENT_HASH_MISMATCH,
        FailureCode.REPAIR_TARGETED,
        FailureCode.REPAIR_SYNTHESIS,
        FailureCode.REPAIR_HITL2,
        FailureCode.BUDGET_EXHAUSTED,
    }
    for code in repairable:
        assert get_classification(code) == "repairable", f"{code} should be repairable"


def test_failure_code_is_closed() -> None:
    """New codes cannot be created outside the enum."""
    with pytest.raises((ValueError, TypeError)):
        FailureCode("nonexistent_code")  # type: ignore[arg-type]
