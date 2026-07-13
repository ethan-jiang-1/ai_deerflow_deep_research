"""Deterministic Send fan-out/fan-in contracts (REG-002)."""

from __future__ import annotations

import pytest

from deerflow_deep_research.domain.state import BranchResult
from deerflow_deep_research.graph.nodes.wave0.subgraph import build_wave0_subgraph, normalize_results
from deerflow_deep_research.graph.nodes.wave1.subgraph import build_wave1_subgraph


@pytest.mark.asyncio
@pytest.mark.parametrize("builder", [build_wave0_subgraph, build_wave1_subgraph])
async def test_wave_subgraph_dispatches_three_and_joins_in_stable_order(builder) -> None:
    result = await builder().ainvoke({"branch_prefix": "g0-wave-a1", "branch_results": ()})
    assert [item.branch_id for item in result["normalized_results"]] == [
        "g0-wave-a1-b0",
        "g0-wave-a1-b1",
        "g0-wave-a1-b2",
    ]


def test_wave_join_normalizes_scheduler_order_and_rejects_duplicates() -> None:
    values = (
        BranchResult(branch_id="x-b2", verdict="pass"),
        BranchResult(branch_id="x-b0", verdict="pass"),
        BranchResult(branch_id="x-b1", verdict="pass"),
    )
    assert [item.branch_id for item in normalize_results(values)] == ["x-b0", "x-b1", "x-b2"]
    with pytest.raises(ValueError, match="duplicate_branch"):
        normalize_results((values[0], values[0], values[1]))


@pytest.mark.asyncio
async def test_repair_attempts_use_distinct_branch_ids() -> None:
    graph = build_wave0_subgraph()
    first = await graph.ainvoke({"branch_prefix": "g0-wave0-a1", "branch_results": ()})
    second = await graph.ainvoke({"branch_prefix": "g0-wave0-a2", "branch_results": ()})
    assert {item.branch_id for item in first["normalized_results"]}.isdisjoint(
        item.branch_id for item in second["normalized_results"]
    )
