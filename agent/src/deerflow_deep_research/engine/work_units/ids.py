"""Deterministic controller-owned work and attempt identifiers.

@impl WOU-001
"""

from __future__ import annotations

from deerflow_deep_research.domain.lifecycle import LogicalPhase
from deerflow_deep_research.domain.work_units import WORK_ID_RE


def allocate_work_id(generation: int, phase: LogicalPhase | str, work_ordinal: int) -> str:
    try:
        normalized_phase = phase if isinstance(phase, LogicalPhase) else LogicalPhase(phase)
    except ValueError as exc:
        raise ValueError("phase_invalid") from exc
    if not isinstance(generation, int) or not 0 <= generation <= 2:
        raise ValueError("generation_invalid")
    if not isinstance(work_ordinal, int) or not 0 <= work_ordinal <= 9999:
        raise ValueError("work_ordinal_invalid")
    return f"g{generation}_{normalized_phase.value}_w{work_ordinal:04d}"


def allocate_attempt_id(work_id: str, attempt_ordinal: int) -> str:
    if not isinstance(work_id, str) or not WORK_ID_RE.fullmatch(work_id):
        raise ValueError("work_id_invalid")
    if not isinstance(attempt_ordinal, int) or not 0 <= attempt_ordinal <= 99:
        raise ValueError("attempt_ordinal_invalid")
    return f"{work_id}_a{attempt_ordinal:02d}"


__all__ = ["allocate_attempt_id", "allocate_work_id"]
