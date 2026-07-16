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
    # Phase progress markers
    assert "→" in output
    assert "⏸" in output
    # Chinese phase labels
    assert "初始化" in output
    assert "研究配置" in output
    assert "主题规划" in output
    assert "决策" in output
    assert "报告生成" in output
    # Terminal completion
    assert "status: completed" in output
    assert "fixture, not completed research" in output
    assert "Blocked deserialization" not in result.stderr
