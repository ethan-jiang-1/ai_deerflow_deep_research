"""Normalized logical topology for the Deep Research graph.

@impl REG-001
@impl REG-005
"""

from __future__ import annotations

from dataclasses import dataclass

START = "__start__"
TERMINALS = frozenset({"completed", "stopped", "blocked", "cancelled"})

LOGICAL_NODES = (
    "bootstrap",
    "hitl1",
    "topic_planning",
    "wave0",
    "wave1",
    "wave2_synthesis",
    "targeted_evidence",
    "hitl2",
    "rerun",
    "readiness",
    "final_delivery",
)


@dataclass(frozen=True, order=True)
class TopologyEdge:
    source: str
    route: str
    target: str


NORMALIZED_EDGES = tuple(
    sorted(
        (
            TopologyEdge(START, "start", "bootstrap"),
            TopologyEdge("bootstrap", "needs_input", "hitl1"),
            TopologyEdge("bootstrap", "profile_complete", "topic_planning"),
            TopologyEdge("bootstrap", "exhausted", "blocked"),
            TopologyEdge("hitl1", "accepted", "topic_planning"),
            TopologyEdge("hitl1", "cancel", "cancelled"),
            TopologyEdge("hitl1", "exhausted", "blocked"),
            TopologyEdge("hitl1", "needs_followup", "hitl1"),
            TopologyEdge("topic_planning", "next", "wave0"),
            TopologyEdge("topic_planning", "exhausted", "blocked"),
            TopologyEdge("wave0", "repair", "wave0"),
            TopologyEdge("wave0", "pass", "wave1"),
            TopologyEdge("wave0", "exhausted", "blocked"),
            TopologyEdge("wave1", "repair", "wave1"),
            TopologyEdge("wave1", "pass", "wave2_synthesis"),
            TopologyEdge("wave1", "exhausted", "blocked"),
            TopologyEdge("wave2_synthesis", "evidence_needed", "targeted_evidence"),
            TopologyEdge("wave2_synthesis", "pass", "hitl2"),
            TopologyEdge("targeted_evidence", "next", "wave2_synthesis"),
            TopologyEdge("hitl2", "revise_view", "wave2_synthesis"),
            TopologyEdge("hitl2", "repair", "targeted_evidence"),
            TopologyEdge("hitl2", "rerun", "rerun"),
            TopologyEdge("hitl2", "proceed", "readiness"),
            TopologyEdge("hitl2", "stop", "stopped"),
            TopologyEdge("hitl2", "cancel", "cancelled"),
            TopologyEdge("rerun", "next", "topic_planning"),
            TopologyEdge("rerun", "topic_planning", "topic_planning"),
            TopologyEdge("rerun", "wave0", "wave0"),
            TopologyEdge("rerun", "wave1", "wave1"),
            TopologyEdge("rerun", "exhausted", "blocked"),
            TopologyEdge("readiness", "repair_targeted", "targeted_evidence"),
            TopologyEdge("readiness", "repair_synthesis", "wave2_synthesis"),
            TopologyEdge("readiness", "repair_hitl2", "hitl2"),
            TopologyEdge("readiness", "pass", "final_delivery"),
            TopologyEdge("readiness", "exhausted", "blocked"),
            TopologyEdge("final_delivery", "repair", "final_delivery"),
            TopologyEdge("final_delivery", "evidence_blocked", "readiness"),
            TopologyEdge("final_delivery", "pass", "completed"),
            TopologyEdge("final_delivery", "exhausted", "blocked"),
        )
    )
)


def validate_topology(nodes: tuple[str, ...], edges: tuple[TopologyEdge, ...]) -> None:
    if len(nodes) != len(set(nodes)):
        raise ValueError("topology_duplicate_node")
    node_set = set(nodes)
    if any(edge.source not in node_set | {START} or edge.target not in node_set | TERMINALS for edge in edges):
        raise ValueError("topology_unknown_endpoint")
    if len(edges) != len(set(edges)):
        raise ValueError("topology_duplicate_edge")
    reachable = {START}
    while True:
        expanded = reachable | {edge.target for edge in edges if edge.source in reachable}
        if expanded == reachable:
            break
        reachable = expanded
    if not node_set <= reachable:
        raise ValueError("topology_unreachable_node")
    reverse = set(TERMINALS)
    while True:
        expanded = reverse | {edge.source for edge in edges if edge.target in reverse}
        if expanded == reverse:
            break
        reverse = expanded
    if not node_set <= reverse:
        raise ValueError("topology_no_terminal_path")


validate_topology(LOGICAL_NODES, NORMALIZED_EDGES)

__all__ = ["LOGICAL_NODES", "NORMALIZED_EDGES", "START", "TERMINALS", "TopologyEdge", "validate_topology"]
