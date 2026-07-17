"""Critical faults map to collected tests at their authoritative seams.

@impl EVH-003
@impl EVH-010
"""

from __future__ import annotations

import pytest

from tests.assets.fault_matrix import (
    CRITICAL_FAULTS,
    CriticalFault,
    FaultMatrixError,
    validate_fault_matrix,
)


def test_fault_matrix_covers_every_required_fault_once() -> None:
    expected = {
        CriticalFault.DUPLICATE_RESUME,
        CriticalFault.CANCEL,
        CriticalFault.TIMEOUT,
        CriticalFault.PARTIAL_PUBLICATION,
        CriticalFault.STALE_CHECKPOINT,
        CriticalFault.CONFLICTING_WORKER_RESULT,
        CriticalFault.RESTART_RECOVERY,
    }
    assert {entry.fault for entry in CRITICAL_FAULTS} == expected
    assert len(CRITICAL_FAULTS) == len(expected)
    for entry in CRITICAL_FAULTS:
        assert "::test_" in entry.selector
        assert entry.seam
        assert entry.expected_outcome


def test_stale_fault_selector_reports_fault_identity() -> None:
    collected = {entry.selector for entry in CRITICAL_FAULTS}
    stale = CRITICAL_FAULTS[0]
    collected.remove(stale.selector)

    with pytest.raises(FaultMatrixError) as exc_info:
        validate_fault_matrix(CRITICAL_FAULTS, collected)

    detail = str(exc_info.value)
    assert stale.fault.value in detail
    assert stale.selector in detail
