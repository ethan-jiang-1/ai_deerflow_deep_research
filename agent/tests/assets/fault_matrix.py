"""Collected real-seam selectors for critical recovery faults.

@impl EVH-003
@impl EVH-010
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum

from tests.assets.evidence import TestEvidenceClaim


class CriticalFault(StrEnum):
    DUPLICATE_RESUME = "duplicate-resume"
    CANCEL = "cancel"
    TIMEOUT = "timeout"
    PARTIAL_PUBLICATION = "partial-publication"
    STALE_CHECKPOINT = "stale-checkpoint"
    CONFLICTING_WORKER_RESULT = "conflicting-worker-result"
    RESTART_RECOVERY = "restart-recovery"


@dataclass(frozen=True)
class FaultCoverage:
    fault: CriticalFault
    claim_id: str
    expected_outcome: str


class FaultMatrixError(ValueError):
    pass


CRITICAL_FAULTS = (
    FaultCoverage(
        CriticalFault.DUPLICATE_RESUME,
        "lifecycle-consumed-resume-cancel",
        "replay reprojects the existing next interrupt without advancing the graph",
    ),
    FaultCoverage(
        CriticalFault.CANCEL,
        "lifecycle-consumed-resume-cancel",
        "repeated cancellation returns the same explicit cancelled terminal outcome",
    ),
    FaultCoverage(
        CriticalFault.TIMEOUT,
        "bridge-wall-time-timeout",
        "bridge wall-time exhaustion returns BUDGET_EXHAUSTED with wall_time error code",
    ),
    FaultCoverage(
        CriticalFault.PARTIAL_PUBLICATION,
        "store-atomic-publication-replay",
        "restart exposes no partial authority and replay commits exactly one record",
    ),
    FaultCoverage(
        CriticalFault.STALE_CHECKPOINT,
        "hitl2-stale-request-rejected",
        "a stale request id is rejected before it can control graph routing",
    ),
    FaultCoverage(
        CriticalFault.CONFLICTING_WORKER_RESULT,
        "store-conflicting-worker-result",
        "same-hash replay is idempotent and divergent content is an explicit conflict",
    ),
    FaultCoverage(
        CriticalFault.RESTART_RECOVERY,
        "provider-subprocess-restart",
        "a new process resumes the durable research checkpoint with a new interrupt",
    ),
)


def validate_fault_matrix(
    entries: Iterable[FaultCoverage],
    claims: dict[str, TestEvidenceClaim],
    collected_selectors: set[str],
) -> None:
    seen: set[CriticalFault] = set()
    errors: list[str] = []
    for entry in entries:
        if entry.fault in seen:
            errors.append(f"{entry.fault.value}: duplicate fault")
        seen.add(entry.fault)
        claim = claims.get(entry.claim_id)
        if claim is None:
            errors.append(f"{entry.fault.value}: unknown claim {entry.claim_id}")
            continue
        if claim.selector not in collected_selectors:
            errors.append(f"{entry.fault.value}: {entry.claim_id}: stale selector {claim.selector}")
    if errors:
        raise FaultMatrixError("\n".join(errors))


__all__ = [
    "CRITICAL_FAULTS",
    "CriticalFault",
    "FaultCoverage",
    "FaultMatrixError",
    "validate_fault_matrix",
]
