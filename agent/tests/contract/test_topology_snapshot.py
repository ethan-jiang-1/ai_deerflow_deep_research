from pathlib import Path

from deerflow_deep_research.graph.topology_snapshot import render_topology_snapshot

AGENT_ROOT = Path(__file__).resolve().parents[2]


def test_committed_topology_snapshot_matches_normalized_semantics() -> None:
    target = AGENT_ROOT / "docs" / "deep-research-topology.md"
    assert target.read_text(encoding="utf-8") == render_topology_snapshot()
    text = target.read_text(encoding="utf-8")
    assert "dispatch" not in text and "join" not in text
    assert "final_delivery --evidence_blocked--> readiness" in text
