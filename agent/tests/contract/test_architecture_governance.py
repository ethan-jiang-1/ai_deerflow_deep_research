"""Deterministic contracts for the permanent project-structure governance gate."""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
CHECKER = REPO_ROOT / "openspec" / "governance" / "check_project_architecture.py"
MANIFEST_PATH = Path("openspec/governance/project-structure.toml")
ACTIVE_SPEC_PATH = Path("openspec/changes/change-00/specs/project-structure/spec.md")
MAIN_SPEC_PATH = Path("openspec/specs/project-structure/spec.md")
ARCHIVED_SPEC_PATH = Path("openspec/changes/archive/change-00/specs/project-structure/spec.md")
GUIDE_PATH = Path("agent/AGENTS.md")
BEGIN_MARKER = "<!-- BEGIN GENERATED: PROJECT-STRUCTURE -->"
END_MARKER = "<!-- END GENERATED: PROJECT-STRUCTURE -->"

VALID_MANIFEST = """\
schema_version = 1
contract = "project-structure"
requirement_ids = ["PRS-001", "PRS-002", "PRS-003", "PRS-004"]

[guide]
path = "agent/AGENTS.md"
begin_marker = "<!-- BEGIN GENERATED: PROJECT-STRUCTURE -->"
end_marker = "<!-- END GENERATED: PROJECT-STRUCTURE -->"

[package]
source_root = "agent/src/deerflow_deep_research"
test_root = "agent/tests"
ownership_layers = ["runtime", "domain", "engine", "agents", "graph"]
forbidden_source_roots = ["backend", "frontend"]
forbidden_shared_modules = ["utils", "helpers", "common"]

[[required_paths]]
path = "agent/pyproject.toml"
kind = "file"
owner = "PRS-001"

[[required_paths]]
path = "agent/src/deerflow_deep_research"
kind = "directory"
owner = "PRS-001"

[[required_paths]]
path = "agent/tests"
kind = "directory"
owner = "PRS-001"

[imports]
domain = ["stdlib", "pydantic"]
engine = ["domain"]
agents = ["domain", "deerflow", "langchain"]
graph = ["domain", "engine", "nodes", "langgraph"]
nodes = ["domain", "engine", "langgraph"]
runtime = ["domain", "graph", "agents", "deerflow", "langchain", "langgraph"]

[node_packages]
root = "agent/src/deerflow_deep_research/graph/nodes"
required_files = ["__init__.py", "node.py", "fake.py", "contracts.py"]
optional_files = ["subgraph.py"]
public_export = "NODE_SPEC"
"""

SPEC_TEXT = """\
> req: PRS-001, PRS-002, PRS-003, PRS-004
> structure: openspec/governance/project-structure.toml

## ADDED Requirements

### Requirement: Structural authority survives change archival
The owning spec normatively identifies the permanent structure registry.
"""

MAIN_SPEC_TEXT = SPEC_TEXT.replace("## ADDED Requirements", "## Purpose\n\nFixture.\n\n## Requirements")

REGISTRY_TEXT = """\
prefixes:
  PRS: project-structure

PRS-001: project-structure - package ownership
PRS-002: project-structure - imports
PRS-003: project-structure - node surface
PRS-004: project-structure - durable authority
"""

VALID_GENERATED_BLOCK = """\
<!-- BEGIN GENERATED: PROJECT-STRUCTURE -->
## Canonical Structure Contract

Registry: `openspec/governance/project-structure.toml`

- Source root: `agent/src/deerflow_deep_research/`
- Test root: `agent/tests/`
- Ownership layers: `runtime`, `domain`, `engine`, `agents`, `graph`
- Forbidden source roots: `backend/`, `frontend/`
- Required current paths:
  - `agent/pyproject.toml` (file; `PRS-001`)
  - `agent/src/deerflow_deep_research/` (directory; `PRS-001`)
  - `agent/tests/` (directory; `PRS-001`)
- Top-level node root: `agent/src/deerflow_deep_research/graph/nodes/`
- Required node files: `__init__.py`, `node.py`, `fake.py`, `contracts.py`
- Public node export: `NODE_SPEC`
<!-- END GENERATED: PROJECT-STRUCTURE -->
"""


def _write(root: Path, relative_path: Path | str, content: str = "") -> None:
    path = root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _replace(root: Path, relative_path: Path | str, old: str, new: str) -> None:
    path = root / relative_path
    path.write_text(path.read_text(encoding="utf-8").replace(old, new), encoding="utf-8")


class ArchitectureGovernanceContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temporary = tempfile.TemporaryDirectory()
        self.root = Path(self._temporary.name)
        _write(self.root, MANIFEST_PATH, VALID_MANIFEST)
        _write(self.root, "openspec/governance/req-registry.yaml", REGISTRY_TEXT)
        _write(self.root, ACTIVE_SPEC_PATH, SPEC_TEXT)
        _write(self.root, GUIDE_PATH, f"# Agent Guide\n\n{VALID_GENERATED_BLOCK}\nOperational text.\n")
        _write(self.root, "agent/pyproject.toml", '[project]\nname = "fixture"\n')
        (self.root / "agent/src/deerflow_deep_research").mkdir(parents=True)
        (self.root / "agent/tests").mkdir(parents=True)

    def tearDown(self) -> None:
        self._temporary.cleanup()

    def run_checker(self) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(CHECKER), str(self.root)],
            check=False,
            capture_output=True,
            text=True,
        )

    def assert_checker_error(self, code: str) -> None:
        result = self.run_checker()
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn(code, result.stderr)

    def test_valid_pending_project_passes(self) -> None:
        result = self.run_checker()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("architecture governance passed", result.stdout.lower())

    def test_missing_manifest_fails(self) -> None:
        (self.root / MANIFEST_PATH).unlink()
        self.assert_checker_error("manifest.missing")

    def test_malformed_manifest_fails(self) -> None:
        _write(self.root, MANIFEST_PATH, "schema_version = [")
        self.assert_checker_error("manifest.parse")

    def test_absolute_path_fails(self) -> None:
        _replace(self.root, MANIFEST_PATH, 'path = "agent/pyproject.toml"', 'path = "/agent/pyproject.toml"')
        self.assert_checker_error("path.absolute")

    def test_traversing_path_fails(self) -> None:
        _replace(self.root, MANIFEST_PATH, 'path = "agent/pyproject.toml"', 'path = "agent/../pyproject.toml"')
        self.assert_checker_error("path.traversal")

    def test_duplicate_path_fails(self) -> None:
        duplicate = """\

[[required_paths]]
path = "agent/pyproject.toml"
kind = "file"
owner = "PRS-001"
"""
        _write(self.root, MANIFEST_PATH, VALID_MANIFEST + duplicate)
        self.assert_checker_error("path.duplicate")

    def test_unknown_requirement_owner_fails(self) -> None:
        _replace(self.root, MANIFEST_PATH, 'owner = "PRS-001"', 'owner = "PRS-999"')
        self.assert_checker_error("owner.unknown")

    def test_forbidden_upstream_ownership_fails(self) -> None:
        _replace(self.root, MANIFEST_PATH, 'path = "agent/pyproject.toml"', 'path = "backend/deep-research.py"')
        _write(self.root, "backend/deep-research.py")
        self.assert_checker_error("path.forbidden_owner")

    def test_missing_owning_spec_reference_fails(self) -> None:
        _replace(self.root, ACTIVE_SPEC_PATH, "> structure: openspec/governance/project-structure.toml\n", "")
        self.assert_checker_error("spec.reference_missing")

    def test_ambiguous_pending_owning_specs_fail(self) -> None:
        _write(self.root, "openspec/changes/change-other/specs/project-structure/spec.md", SPEC_TEXT)
        self.assert_checker_error("spec.reference_ambiguous")

    def test_archived_delta_cannot_be_pending_authority(self) -> None:
        _write(self.root, ARCHIVED_SPEC_PATH, SPEC_TEXT)
        shutil.rmtree(self.root / "openspec/changes/change-00")
        self.assert_checker_error("spec.archived_only")

    def test_archived_delta_cannot_replace_existing_main_spec(self) -> None:
        _write(self.root, ARCHIVED_SPEC_PATH, SPEC_TEXT)
        _write(self.root, MAIN_SPEC_PATH, MAIN_SPEC_TEXT.replace("> structure:", "> historical-structure:"))
        shutil.rmtree(self.root / "openspec/changes/change-00")
        self.assert_checker_error("spec.reference_missing")

    def test_missing_guide_markers_fail(self) -> None:
        _write(self.root, GUIDE_PATH, "# Agent Guide\n")
        self.assert_checker_error("guide.marker_missing")

    def test_duplicate_guide_markers_fail(self) -> None:
        _write(self.root, GUIDE_PATH, f"{VALID_GENERATED_BLOCK}\n{VALID_GENERATED_BLOCK}")
        self.assert_checker_error("guide.marker_duplicate")

    def test_stale_generated_guide_block_fails(self) -> None:
        _replace(self.root, GUIDE_PATH, "Ownership layers:", "Old ownership layers:")
        self.assert_checker_error("guide.drift")

    def test_second_source_root_fails(self) -> None:
        _write(self.root, "rogue/deerflow_deep_research/__init__.py")
        self.assert_checker_error("source.second_root")

    def test_missing_required_path_fails(self) -> None:
        (self.root / "agent/pyproject.toml").unlink()
        self.assert_checker_error("path.missing")


if __name__ == "__main__":
    unittest.main()
