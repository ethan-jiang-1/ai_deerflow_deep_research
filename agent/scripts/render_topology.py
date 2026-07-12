#!/usr/bin/env python3
"""Render the committed Deep Research semantic topology snapshot."""

from pathlib import Path

from deerflow_deep_research.graph.topology_snapshot import render_topology_snapshot

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "docs" / "deep-research-topology.md"


def main() -> None:
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    TARGET.write_text(render_topology_snapshot(), encoding="utf-8")


if __name__ == "__main__":
    main()
