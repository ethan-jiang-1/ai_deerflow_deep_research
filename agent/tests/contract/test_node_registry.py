"""Contracts for explicit top-level node package registration."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

PACKAGE_PREFIX = "fixture_nodes.nodes"

CONTRACTS_SOURCE = """\
from deerflow_deep_research.domain.node_spec import NodeContracts
from deerflow_deep_research.domain.context import NodeExecutionRequest, NodeExecutionResult

CONTRACTS = NodeContracts(request_type=NodeExecutionRequest, result_type=NodeExecutionResult)
"""

NODE_SOURCE = """\
from deerflow_deep_research.domain.node_spec import NodeBuildDependencies

async def _run(state):
    return state

def build_real(dependencies: NodeBuildDependencies):
    assert dependencies.capabilities is not None
    return _run
"""

FAKE_SOURCE = """\
from deerflow_deep_research.domain.node_spec import NodeBuildDependencies

async def _run(state):
    return state

def build_fake(dependencies: NodeBuildDependencies):
    assert dependencies.capabilities is not None
    return _run
"""


def _package_init(logical_name: str, *, exports: str = '["NODE_SPEC"]', reverse_registry: bool = False) -> str:
    reverse = "from deerflow_deep_research.graph import registry\n" if reverse_registry else ""
    return f"""\
{reverse}from deerflow_deep_research.domain.enums import NodePhase
from deerflow_deep_research.domain.node_spec import NodeSpec, PolicyRef
from .contracts import CONTRACTS as _CONTRACTS
from .fake import build_fake as _build_fake
from .node import build_real as _build_real

NODE_SPEC = NodeSpec(
    logical_name={logical_name!r},
    phase=NodePhase.INFRASTRUCTURE,
    policy=PolicyRef(name="fixture-policy", version="v1"),
    contracts=_CONTRACTS,
    real_factory=_build_real,
    fake_factory=_build_fake,
)
__all__ = {exports}
"""


def _write(path: Path, content: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _make_package(
    root: Path,
    name: str,
    *,
    logical_name: str | None = None,
    exports: str = '["NODE_SPEC"]',
    reverse_registry: bool = False,
) -> str:
    _write(root / "fixture_nodes/__init__.py")
    _write(root / "fixture_nodes/nodes/__init__.py")
    package_root = root / "fixture_nodes/nodes" / name
    _write(
        package_root / "__init__.py",
        _package_init(logical_name or name, exports=exports, reverse_registry=reverse_registry),
    )
    _write(package_root / "contracts.py", CONTRACTS_SOURCE)
    _write(package_root / "node.py", NODE_SOURCE)
    _write(package_root / "fake.py", FAKE_SOURCE)
    return f"{PACKAGE_PREFIX}.{name}"


@pytest.fixture
def fixture_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.syspath_prepend(str(tmp_path))
    importlib.invalidate_caches()
    yield tmp_path
    for module_name in list(sys.modules):
        if module_name == "fixture_nodes" or module_name.startswith("fixture_nodes."):
            sys.modules.pop(module_name, None)


def _registry_types():
    module = importlib.import_module("deerflow_deep_research.graph.registry")
    return module.NodeRegistry, module.NodeRegistryError


def test_valid_node_package_is_loaded_from_its_root(fixture_path: Path) -> None:
    package = _make_package(fixture_path, "valid")
    NodeRegistry, _ = _registry_types()

    registry = NodeRegistry(package_prefix=PACKAGE_PREFIX, package_names=(package,))
    specs = registry.load()

    assert tuple(specs) == ("valid",)
    assert specs["valid"].logical_name == "valid"
    assert specs["valid"].real_factory.__name__ == "build_real"
    assert specs["valid"].fake_factory.__name__ == "build_fake"
    assert specs["valid"].contracts.request_type.__name__ == "NodeExecutionRequest"
    assert specs["valid"].phase.value == "infrastructure"
    assert specs["valid"].policy.name == "fixture-policy"


@pytest.mark.parametrize(("missing", "code"), [("fake.py", "node.file_missing"), ("contracts.py", "node.file_missing")])
def test_partial_node_package_is_rejected(fixture_path: Path, missing: str, code: str) -> None:
    package = _make_package(fixture_path, "partial")
    (fixture_path / "fixture_nodes/nodes/partial" / missing).unlink()
    NodeRegistry, NodeRegistryError = _registry_types()

    with pytest.raises(NodeRegistryError, match=code):
        NodeRegistry(package_prefix=PACKAGE_PREFIX, package_names=(package,)).load()


def test_unstable_logical_name_is_rejected(fixture_path: Path) -> None:
    package = _make_package(fixture_path, "stable_package", logical_name="different_name")
    NodeRegistry, NodeRegistryError = _registry_types()

    with pytest.raises(NodeRegistryError, match="node.logical_name"):
        NodeRegistry(package_prefix=PACKAGE_PREFIX, package_names=(package,)).load()


def test_internal_export_leakage_is_rejected(fixture_path: Path) -> None:
    package = _make_package(fixture_path, "leaky", exports='["NODE_SPEC", "_build_real"]')
    NodeRegistry, NodeRegistryError = _registry_types()

    with pytest.raises(NodeRegistryError, match="node.exports"):
        NodeRegistry(package_prefix=PACKAGE_PREFIX, package_names=(package,)).load()


def test_node_to_registry_reverse_import_is_rejected(fixture_path: Path) -> None:
    package = _make_package(fixture_path, "cyclic", reverse_registry=True)
    NodeRegistry, NodeRegistryError = _registry_types()

    with pytest.raises(NodeRegistryError, match="node.registry_import"):
        NodeRegistry(package_prefix=PACKAGE_PREFIX, package_names=(package,)).load()


def test_implicit_filesystem_discovery_is_not_available() -> None:
    NodeRegistry, NodeRegistryError = _registry_types()

    with pytest.raises(NodeRegistryError, match="registry.explicit_packages_required"):
        NodeRegistry(package_prefix=PACKAGE_PREFIX, package_names=None)


def test_private_node_module_cannot_be_registered(fixture_path: Path) -> None:
    package = _make_package(fixture_path, "private")
    NodeRegistry, NodeRegistryError = _registry_types()

    with pytest.raises(NodeRegistryError, match="registry.private_module"):
        NodeRegistry(package_prefix=PACKAGE_PREFIX, package_names=(f"{package}.node",))


@pytest.mark.parametrize(
    "package",
    ["fixture_nodes.components.reusable", "fixture_nodes.topology"],
)
def test_component_or_topology_module_cannot_be_registered(package: str) -> None:
    NodeRegistry, NodeRegistryError = _registry_types()

    with pytest.raises(NodeRegistryError, match="registry.package_root"):
        NodeRegistry(package_prefix=PACKAGE_PREFIX, package_names=(package,))
