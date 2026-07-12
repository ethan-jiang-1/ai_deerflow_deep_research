"""Wave0 phase-local three-way Send/fan-in recipe.

@impl REG-002
"""

from __future__ import annotations

import operator
from typing import Annotated, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from deerflow_deep_research.domain.lifecycle import BranchResult


class WaveSubgraphState(TypedDict):
    branch_prefix: str
    branch_id: str
    branch_results: Annotated[tuple[BranchResult, ...], operator.add]
    normalized_results: tuple[BranchResult, ...]


def dispatch(state: WaveSubgraphState) -> list[Send]:
    return [
        Send("worker", {"branch_id": f"{state['branch_prefix']}-b{index}", "branch_results": ()}) for index in range(3)
    ]


async def worker(state: WaveSubgraphState) -> dict:
    return {"branch_results": (BranchResult(branch_id=state["branch_id"], verdict="pass"),)}


def normalize_results(values: tuple[BranchResult, ...]) -> tuple[BranchResult, ...]:
    ids = [value.branch_id for value in values]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate_branch")
    if len(values) != 3:
        raise ValueError("branch_count_invalid")
    return tuple(sorted(values, key=lambda value: value.branch_id))


async def join(state: WaveSubgraphState) -> dict:
    return {"normalized_results": normalize_results(state["branch_results"])}


def build_wave0_subgraph():
    builder = StateGraph(WaveSubgraphState)
    builder.add_node("dispatch", lambda _state: {})
    builder.add_node("worker", worker)
    builder.add_node("join", join, defer=True)
    builder.add_edge(START, "dispatch")
    builder.add_conditional_edges("dispatch", dispatch)
    builder.add_edge("worker", "join")
    builder.add_edge("join", END)
    return builder.compile(checkpointer=None)
