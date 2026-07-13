"""Closed failure-code registry for the deterministic gate kernel.

@impl GAK-002
"""

from __future__ import annotations

from enum import StrEnum


class FailureCode(StrEnum):
    """Stable failure codes with fixed classifications.

    Models, workers, and repair agents SHALL NOT emit new or free-form codes.
    Phase gate definitions SHALL register only codes from this closed enum.
    """

    # Hard — cannot be repaired; blocks the phase immediately
    MISSING_WORK_SPEC = "missing_work_spec"
    WORK_CANCELLED = "work_cancelled"
    IDENTITY_MISMATCH = "identity_mismatch"
    SCHEMA_VERSION_UNSUPPORTED = "schema_version_unsupported"

    # Semantic — output is technically valid but semantically wrong
    INCOMPLETE_TOPIC_COVERAGE = "incomplete_topic_coverage"
    MISSING_EVIDENCE = "missing_evidence"
    DEGRADED_EVIDENCE_QUALITY = "degraded_evidence_quality"
    EVIDENCE_INSUFFICIENT = "evidence_insufficient"

    # Degradable — non-critical, phase can pass with degraded flag
    UNTRUSTED_SOURCE = "untrusted_source"

    # Repairable — worker or phase can fix and retry
    WORK_TIMED_OUT = "work_timed_out"
    WORK_FAILED = "work_failed"
    BUDGET_EXHAUSTED = "budget_exhausted"
    INVALID_OUTPUT_SCHEMA = "invalid_output_schema"
    CONTENT_HASH_MISMATCH = "content_hash_mismatch"
    REPAIR_TARGETED = "repair_targeted"
    REPAIR_SYNTHESIS = "repair_synthesis"
    REPAIR_HITL2 = "repair_hitl2"

    # System — gate-internal, produced by the kernel itself
    REPAIR_BUDGET_EXHAUSTED = "repair_budget_exhausted"
    FATIGUE_ESCALATION = "fatigue_escalation"


def get_classification(code: FailureCode) -> str:
    """Return the stable classification for *code*."""
    return _CLASSIFICATION_MAP[code]


# ---------------------------------------------------------------------------
# Classification map
# ---------------------------------------------------------------------------

_CLASSIFICATION_MAP: dict[FailureCode, str] = {
    # Hard
    FailureCode.MISSING_WORK_SPEC: "hard",
    FailureCode.WORK_CANCELLED: "hard",
    FailureCode.IDENTITY_MISMATCH: "hard",
    FailureCode.SCHEMA_VERSION_UNSUPPORTED: "hard",
    # Semantic
    FailureCode.INCOMPLETE_TOPIC_COVERAGE: "semantic",
    FailureCode.MISSING_EVIDENCE: "semantic",
    FailureCode.DEGRADED_EVIDENCE_QUALITY: "semantic",
    FailureCode.EVIDENCE_INSUFFICIENT: "semantic",
    # Degradable
    FailureCode.UNTRUSTED_SOURCE: "degradable",
    # Repairable
    FailureCode.WORK_TIMED_OUT: "repairable",
    FailureCode.WORK_FAILED: "repairable",
    FailureCode.BUDGET_EXHAUSTED: "repairable",
    FailureCode.INVALID_OUTPUT_SCHEMA: "repairable",
    FailureCode.CONTENT_HASH_MISMATCH: "repairable",
    FailureCode.REPAIR_TARGETED: "repairable",
    FailureCode.REPAIR_SYNTHESIS: "repairable",
    FailureCode.REPAIR_HITL2: "repairable",
    # System
    FailureCode.REPAIR_BUDGET_EXHAUSTED: "hard",
    FailureCode.FATIGUE_ESCALATION: "hard",
}


__all__ = [
    "FailureCode",
    "get_classification",
]
