"""Pure reducer adapters for work-unit kernel values.

@impl WOU-002
@impl WOU-007
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping

from deerflow_deep_research.domain.state import merge_accepted_refs
from deerflow_deep_research.domain.work_units import CandidateResult, merge_candidates


def reduce_candidates(
    current: Mapping[str, CandidateResult],
    incoming: Mapping[str, CandidateResult],
) -> dict[str, CandidateResult]:
    return merge_candidates(current, incoming)


def reduce_accepted_refs(current: Iterable[str], incoming: Iterable[str]) -> tuple[str, ...]:
    return merge_accepted_refs(current, incoming)


__all__ = ["reduce_accepted_refs", "reduce_candidates"]
