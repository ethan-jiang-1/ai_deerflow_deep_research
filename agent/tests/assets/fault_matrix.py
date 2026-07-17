"""Collected real-seam selectors for critical recovery faults.

@impl EVH-003
@impl EVH-010
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum

from tests.assets.inventory import StableSeam


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
    seam: StableSeam
    selector: str
    expected_outcome: str


class FaultMatrixError(ValueError):
    pass


CRITICAL_FAULTS = (
    FaultCoverage(
        CriticalFault.DUPLICATE_RESUME,
        StableSeam.PUBLIC_ENTRY,
        "tests/integration/test_research_lifecycle_tool.py::test_consumed_resume_reprojects_next_interrupt_and_cancel_is_idempotent",
        "replay reprojects the existing next interrupt without advancing the graph",
    ),
    FaultCoverage(
        CriticalFault.CANCEL,
        StableSeam.PUBLIC_ENTRY,
        "tests/integration/test_research_lifecycle_tool.py::test_consumed_resume_reprojects_next_interrupt_and_cancel_is_idempotent",
        "repeated cancellation returns the same explicit cancelled terminal outcome",
    ),
    FaultCoverage(
        CriticalFault.TIMEOUT,
        StableSeam.NODE_CAPABILITY,
        "tests/eval/test_fault_injection.py::test_wall_time_timeout_returns_typed_budget_exhausted_outcome",
        "bridge wall-time exhaustion returns BUDGET_EXHAUSTED with wall_time error code",
    ),
    FaultCoverage(
        CriticalFault.PARTIAL_PUBLICATION,
        StableSeam.RUNTIME_STORE,
        "tests/unit/test_work_unit_store.py::test_atomic_publication_fault_boundaries_replay_from_last_parent_checkpoint[after_staging_fsync-False]",
        "restart exposes no partial authority and replay commits exactly one record",
    ),
    FaultCoverage(
        CriticalFault.STALE_CHECKPOINT,
        StableSeam.NODE_CAPABILITY,
        "tests/unit/test_hitl2_real.py::TestRealHitl2Factory::test_stale_request_id_rejected",
        "a stale request id is rejected before it can control graph routing",
    ),
    FaultCoverage(
        CriticalFault.CONFLICTING_WORKER_RESULT,
        StableSeam.RUNTIME_STORE,
        "tests/integration/test_work_unit_submit_boundary.py::test_same_hash_replays_and_different_hash_conflicts_at_real_store_boundary",
        "same-hash replay is idempotent and divergent content is an explicit conflict",
    ),
    FaultCoverage(
        CriticalFault.RESTART_RECOVERY,
        StableSeam.LIFECYCLE_GRAPH,
        "tests/integration/test_provider_durability.py::test_file_sqlite_research_resumes_after_real_subprocess_restart",
        "a new process resumes the durable research checkpoint with a new interrupt",
    ),
)


def validate_fault_matrix(entries: Iterable[FaultCoverage], collected_selectors: set[str]) -> None:
    seen: set[CriticalFault] = set()
    errors: list[str] = []
    for entry in entries:
        if entry.fault in seen:
            errors.append(f"{entry.fault.value}: duplicate fault")
        seen.add(entry.fault)
        if entry.selector not in collected_selectors:
            errors.append(f"{entry.fault.value}: stale selector {entry.selector}")
    if errors:
        raise FaultMatrixError("\n".join(errors))


__all__ = [
    "CRITICAL_FAULTS",
    "CriticalFault",
    "FaultCoverage",
    "FaultMatrixError",
    "validate_fault_matrix",
]
