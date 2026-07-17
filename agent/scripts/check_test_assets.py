#!/usr/bin/env python3
"""Validate incident mappings against the deterministic pytest collection.

@impl EVH-006
@impl EVH-009
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

AGENT_ROOT = Path(__file__).resolve().parents[1]
if str(AGENT_ROOT) not in sys.path:
    sys.path.insert(0, str(AGENT_ROOT))

from deerflow_deep_research.graph.registry import load_research_node_specs  # noqa: E402
from tests.assets.inventory import INCIDENTS, CoverageError, validate_incident_coverage  # noqa: E402
from tests.assets.node_conformance import NODE_CONFORMANCE, validate_node_conformance  # noqa: E402
from tests.assets.selection import DETERMINISTIC_EXCLUDE  # noqa: E402


def collect_deterministic_selectors(agent_root: Path = AGENT_ROOT) -> set[str]:
    result = subprocess.run(
        [
            "uv",
            "run",
            "--extra",
            "operations",
            "pytest",
            "--collect-only",
            "-q",
            "-m",
            f"not ({DETERMINISTIC_EXCLUDE})",
        ],
        cwd=agent_root,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise CoverageError(f"pytest collection failed:\n{result.stderr or result.stdout}")
    return {line.strip() for line in result.stdout.splitlines() if "::" in line and not line.startswith("=")}


def main() -> int:
    try:
        collected = collect_deterministic_selectors()
        validate_incident_coverage(INCIDENTS, collected, excluded_selectors=set())
        validate_node_conformance(
            NODE_CONFORMANCE,
            collected,
            registered_names=set(load_research_node_specs()),
        )
    except CoverageError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(
        f"Test asset coverage passed: {len(INCIDENTS)} incidents, "
        f"{len(NODE_CONFORMANCE)} real nodes, {len(collected)} deterministic tests collected."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
