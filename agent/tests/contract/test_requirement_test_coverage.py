"""Requirement-to-collected-test governance checker contracts.

@impl EVH-009
@impl EVH-010
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

CHECKER = Path(__file__).resolve().parents[3] / "openspec" / "governance" / "check_project_req_coverage.py"


def _write(root: Path, relative: str, content: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _run(root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, str(CHECKER), str(root)], capture_output=True, text=True, check=False)


def _project(tmp_path: Path) -> Path:
    _write(tmp_path, "openspec/governance/req-registry.yaml", "ABC-001: alpha\nABC-002: beta\n")
    _write(tmp_path, "openspec/specs/example/spec.md", "> req: ABC-001, ABC-002\n")
    _write(
        tmp_path,
        "agent/tests/unit/test_example.py",
        '"""@impl ABC-001, ABC-002"""\n\ndef test_example():\n    assert True\n',
    )
    return tmp_path


def test_valid_collected_requirement_coverage_passes(tmp_path: Path) -> None:
    result = _run(_project(tmp_path))
    assert result.returncode == 0, result.stderr


def test_unknown_test_requirement_fails(tmp_path: Path) -> None:
    root = _project(tmp_path)
    _write(root, "agent/tests/unit/test_unknown.py", '"""@impl XYZ-999"""\n\ndef test_unknown(): pass\n')
    result = _run(root)
    assert result.returncode == 1
    assert "unknown test requirement" in result.stderr
    assert "XYZ-999" in result.stderr


def test_alive_requirement_without_test_fails(tmp_path: Path) -> None:
    root = _project(tmp_path)
    (root / "agent/tests/unit/test_example.py").write_text(
        '"""@impl ABC-001"""\n\ndef test_example(): pass\n', encoding="utf-8"
    )
    result = _run(root)
    assert result.returncode == 1
    assert "uncovered requirement" in result.stderr
    assert "ABC-002" in result.stderr


def test_package_only_reference_does_not_count(tmp_path: Path) -> None:
    root = _project(tmp_path)
    _write(root, "agent/tests/__init__.py", '"""@impl ABC-002"""\n')
    (root / "agent/tests/unit/test_example.py").write_text(
        '"""@impl ABC-001"""\n\ndef test_example(): pass\n', encoding="utf-8"
    )
    result = _run(root)
    assert result.returncode == 1
    assert "ABC-002" in result.stderr
