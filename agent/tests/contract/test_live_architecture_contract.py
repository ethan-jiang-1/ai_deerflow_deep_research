"""Run the permanent architecture checker against the live repository."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
CHECKER = REPO_ROOT / "openspec" / "governance" / "check_project_architecture.py"


def test_live_repository_satisfies_architecture_contract() -> None:
    result = subprocess.run(
        [sys.executable, str(CHECKER), str(REPO_ROOT)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
