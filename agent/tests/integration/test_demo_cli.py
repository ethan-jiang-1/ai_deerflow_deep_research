"""Standalone full-fake terminal demo smoke contract."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

AGENT_ROOT = Path(__file__).resolve().parents[2]


def test_scripted_demo_traverses_both_interrupts_and_terminal_fixture() -> None:
    result = subprocess.run(
        [sys.executable, str(AGENT_ROOT / "scripts/demo.py"), "--scripted"],
        cwd=AGENT_ROOT,
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
        env=os.environ | {"LANGGRAPH_STRICT_MSGPACK": "true"},
    )

    output = result.stdout
    assert "=== START RESULT ===" in output
    assert "=== HITL1 REQUEST ===" in output
    assert "=== HITL2 REQUEST ===" in output
    assert "=== TERMINAL RESULT ===" in output
    assert output.count('"implementation_mode": "full_fake"') == 3
    assert '"code": "completed"' in output
    assert "fixture, not completed research" in output
    assert "Blocked deserialization" not in result.stderr
