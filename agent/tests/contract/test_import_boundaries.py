"""Manifest-backed AST import and source-ownership contracts."""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
CHECKER = REPO_ROOT / "openspec" / "governance" / "check_project_architecture.py"

MANIFEST = """\
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
path = "agent/src/deerflow_deep_research"
kind = "directory"
owner = "PRS-001"

[imports]
domain = ["stdlib", "pydantic"]
engine = ["domain"]
agents = ["domain", "deerflow", "langchain"]
graph = ["domain", "nodes", "langgraph"]
nodes = ["domain", "engine", "langgraph"]
runtime = ["domain", "graph", "agents", "deerflow", "langchain", "langgraph"]

[node_packages]
root = "agent/src/deerflow_deep_research/graph/nodes"
required_files = ["__init__.py", "node.py", "fake.py", "contracts.py"]
optional_files = ["subgraph.py"]
public_export = "NODE_SPEC"
"""

REGISTRY = """\
PRS-001: project-structure - package ownership
PRS-002: project-structure - imports
PRS-003: project-structure - nodes
PRS-004: project-structure - governance
"""

VALID_MODULES = {
    "domain/models.py": "from dataclasses import dataclass\nfrom pydantic import BaseModel\n",
    "engine/runner.py": "from deerflow_deep_research.domain import models\n",
    "agents/factory.py": (
        "from deerflow.agents import create_deerflow_agent\n"
        "from langchain_core.tools import BaseTool\n"
        "from deerflow_deep_research.domain import models\n"
    ),
    "graph/builder.py": "from langgraph.graph import StateGraph\nfrom deerflow_deep_research.domain import models\n",
    "runtime/adapter.py": (
        "from deerflow.tools.types import Runtime\n"
        "from langchain_core.tools import BaseTool\n"
        "from langgraph.runtime import Runtime as LangGraphRuntime\n"
        "from deerflow_deep_research.agents import factory\n"
        "from deerflow_deep_research.domain import models\n"
        "from deerflow_deep_research.graph import builder\n"
    ),
    "graph/nodes/alpha/__init__.py": 'NODE_SPEC = object()\n__all__ = ["NODE_SPEC"]\n',
    "graph/nodes/alpha/contracts.py": "from deerflow_deep_research.domain import models\n",
    "graph/nodes/alpha/fake.py": "from deerflow_deep_research.engine import runner\n",
    "graph/nodes/alpha/node.py": ("from . import contracts\nfrom deerflow_deep_research.engine import runner\n"),
    "graph/nodes/alpha/subgraph.py": "from langgraph.types import Send\n",
    "tool.py": "from deerflow_deep_research import runtime\n",
}


def _write(root: Path, relative: str, content: str = "") -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


@pytest.fixture
def project_root() -> Path:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        _write(root, "openspec/governance/project-structure.toml", MANIFEST)
        _write(root, "openspec/governance/req-registry.yaml", REGISTRY)
        source_root = "agent/src/deerflow_deep_research"
        for relative, content in VALID_MODULES.items():
            _write(root, f"{source_root}/{relative}", content)
        yield root


def _run_checker(root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(CHECKER), str(root), "--imports-only"],
        check=False,
        capture_output=True,
        text=True,
    )


def _assert_error(root: Path, code: str) -> None:
    result = _run_checker(root)
    assert result.returncode != 0, result.stdout
    assert code in result.stderr


def test_valid_layer_dependencies_pass(project_root: Path) -> None:
    result = _run_checker(project_root)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize(
    ("relative", "statement"),
    [
        ("domain/reverse.py", "from deerflow_deep_research.runtime import adapter\n"),
        ("engine/reverse.py", "from deerflow_deep_research.agents import factory\n"),
        ("agents/reverse.py", "from deerflow_deep_research.runtime import adapter\n"),
        ("agents/graph_reverse.py", "from deerflow_deep_research.graph import builder\n"),
        ("graph/nodes/alpha/agent_reverse.py", "from deerflow_deep_research.agents import factory\n"),
        ("graph/nodes/alpha/runtime_reverse.py", "from deerflow_deep_research.runtime import adapter\n"),
        ("graph/nodes/alpha/graph_reverse.py", "from deerflow_deep_research.graph import builder\n"),
    ],
)
def test_reverse_dependency_fails(project_root: Path, relative: str, statement: str) -> None:
    _write(project_root, f"agent/src/deerflow_deep_research/{relative}", statement)
    _assert_error(project_root, "import.boundary")


def test_sibling_node_import_fails(project_root: Path) -> None:
    _write(
        project_root,
        "agent/src/deerflow_deep_research/graph/nodes/beta/node.py",
        "from deerflow_deep_research.graph.nodes.alpha import node\n",
    )
    _assert_error(project_root, "import.sibling")


def test_ordinary_node_module_cannot_import_langgraph(project_root: Path) -> None:
    _write(
        project_root,
        "agent/src/deerflow_deep_research/graph/nodes/alpha/fake.py",
        "from langgraph.types import Send\n",
    )
    _assert_error(project_root, "import.boundary")


def test_hitl_fake_may_import_only_public_interrupt(project_root: Path) -> None:
    _write(
        project_root,
        "agent/src/deerflow_deep_research/graph/nodes/alpha/fake.py",
        "from langgraph.types import interrupt\n",
    )
    result = _run_checker(project_root)
    assert result.returncode == 0, result.stderr


def test_production_app_import_fails(project_root: Path) -> None:
    _write(project_root, "agent/src/deerflow_deep_research/runtime/app_reverse.py", "from app.gateway import app\n")
    _assert_error(project_root, "import.app")


@pytest.mark.parametrize("name", ["utils.py", "helpers.py", "common.py"])
def test_generic_shared_module_fails(project_root: Path, name: str) -> None:
    _write(project_root, f"agent/src/deerflow_deep_research/domain/{name}")
    _assert_error(project_root, "module.generic")


@pytest.mark.parametrize("upstream_root", ["backend", "frontend"])
def test_upstream_import_of_downstream_fails(project_root: Path, upstream_root: str) -> None:
    _write(project_root, f"{upstream_root}/rogue.py", "import deerflow_deep_research\n")
    _assert_error(project_root, "source.upstream_import")


def test_manifest_cannot_weaken_domain_boundary(project_root: Path) -> None:
    manifest = project_root / "openspec/governance/project-structure.toml"
    manifest.write_text(
        manifest.read_text(encoding="utf-8").replace(
            'domain = ["stdlib", "pydantic"]',
            'domain = ["stdlib", "pydantic", "runtime"]',
        ),
        encoding="utf-8",
    )
    _assert_error(project_root, "imports.policy")


def test_manifest_node_shape_requires_fake(project_root: Path) -> None:
    (project_root / "agent/src/deerflow_deep_research/graph/nodes/alpha/fake.py").unlink()
    _assert_error(project_root, "node.file_missing")


def test_manifest_node_shape_rejects_export_leakage(project_root: Path) -> None:
    _write(
        project_root,
        "agent/src/deerflow_deep_research/graph/nodes/alpha/__init__.py",
        'NODE_SPEC = object()\ninternal = object()\n__all__ = ["NODE_SPEC", "internal"]\n',
    )
    _assert_error(project_root, "node.exports")


def test_components_cannot_be_top_level_nodes(project_root: Path) -> None:
    _write(project_root, "agent/src/deerflow_deep_research/graph/nodes/components/__init__.py")
    _assert_error(project_root, "node.package_confusion")
