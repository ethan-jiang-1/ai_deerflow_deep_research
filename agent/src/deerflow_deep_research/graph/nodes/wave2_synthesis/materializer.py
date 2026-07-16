"""Deterministic materializer for Wave2 synthesis artifacts.

@impl WSN-002
"""

from __future__ import annotations

from pathlib import Path

from deerflow_deep_research.domain.synthesis import SynthesisResult
from deerflow_deep_research.domain.work_units import canonical_json_bytes


def materialize_synthesis(result: SynthesisResult, workspace_root: Path) -> None:
    dest = workspace_root / "synthesis" / "findings.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(canonical_json_bytes(result))
