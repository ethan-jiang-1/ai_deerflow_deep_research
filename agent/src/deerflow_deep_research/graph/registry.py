"""Explicit workflow-node package registry."""

from __future__ import annotations

import ast
import importlib
import importlib.util
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from types import MappingProxyType, ModuleType

from deerflow_deep_research.domain.node_spec import NodeBuildDependencies, NodeSpec

_DOTTED_NAME_RE = re.compile(r"^[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*$")
_REQUIRED_FILES = frozenset({"__init__.py", "node.py", "fake.py", "contracts.py"})
_REGISTRY_MODULE = "deerflow_deep_research.graph.registry"


class NodeRegistryError(ValueError):
    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"[{code}] {detail}")
        self.code = code
        self.detail = detail


def _imports_registry(path: Path) -> bool:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import) and any(alias.name == _REGISTRY_MODULE for alias in node.names):
            return True
        if not isinstance(node, ast.ImportFrom):
            continue
        module = node.module or ""
        if module == _REGISTRY_MODULE or (
            module == "deerflow_deep_research.graph" and any(alias.name == "registry" for alias in node.names)
        ):
            return True
    return False


class NodeRegistry:
    def __init__(self, *, package_prefix: str, package_names: Sequence[str] | None) -> None:
        if not _DOTTED_NAME_RE.fullmatch(package_prefix):
            raise NodeRegistryError("registry.package_prefix", "package_prefix must be a dotted Python package")
        if package_names is None:
            raise NodeRegistryError(
                "registry.explicit_packages_required",
                "package_names is required; filesystem discovery is forbidden",
            )
        names = tuple(package_names)
        if len(set(names)) != len(names):
            raise NodeRegistryError("registry.duplicate_package", "package_names contains duplicates")
        direct_prefix = f"{package_prefix}."
        for name in names:
            if not name.startswith(direct_prefix):
                raise NodeRegistryError("registry.package_root", f"{name} is outside {package_prefix}")
            relative = name.removeprefix(direct_prefix)
            if "." in relative:
                raise NodeRegistryError("registry.private_module", f"{name} is not a node package root")
            if not relative.isidentifier():
                raise NodeRegistryError("registry.package_root", f"{name} is not a valid node package")
        self._package_prefix = package_prefix
        self._package_names = names

    @property
    def package_names(self) -> tuple[str, ...]:
        return self._package_names

    def load(self) -> Mapping[str, NodeSpec]:
        specs: dict[str, NodeSpec] = {}
        for package_name in self._package_names:
            package = self._load_package(package_name)
            exports = getattr(package, "__all__", None)
            if exports != ["NODE_SPEC"]:
                raise NodeRegistryError("node.exports", f"{package_name} must export only NODE_SPEC")
            node_spec = getattr(package, "NODE_SPEC", None)
            if not isinstance(node_spec, NodeSpec):
                raise NodeRegistryError("node.spec_type", f"{package_name}.NODE_SPEC is not a NodeSpec")
            expected_name = package_name.rsplit(".", 1)[1]
            if node_spec.logical_name != expected_name:
                raise NodeRegistryError(
                    "node.logical_name",
                    f"{package_name} declares logical name {node_spec.logical_name!r}",
                )
            if node_spec.logical_name in specs:
                raise NodeRegistryError("node.duplicate_name", f"duplicate logical node {node_spec.logical_name}")
            specs[node_spec.logical_name] = node_spec
        return MappingProxyType(specs)

    def _load_package(self, package_name: str) -> ModuleType:
        module_spec = importlib.util.find_spec(package_name)
        if module_spec is None or not module_spec.submodule_search_locations:
            raise NodeRegistryError("registry.package_not_found", f"node package not found: {package_name}")
        package_root = Path(next(iter(module_spec.submodule_search_locations)))
        missing = sorted(name for name in _REQUIRED_FILES if not (package_root / name).is_file())
        if missing:
            raise NodeRegistryError("node.file_missing", f"{package_name} is missing {', '.join(missing)}")
        for path in sorted(package_root.glob("*.py")):
            if _imports_registry(path):
                raise NodeRegistryError("node.registry_import", f"{package_name} imports graph.registry")
        try:
            return importlib.import_module(package_name)
        except (ImportError, TypeError, ValueError) as exc:
            raise NodeRegistryError("node.import", f"cannot load {package_name}: {exc}") from exc


__all__ = ["NodeBuildDependencies", "NodeRegistry", "NodeRegistryError"]
