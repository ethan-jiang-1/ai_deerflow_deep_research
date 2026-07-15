#!/usr/bin/env python3
"""Validate the permanent project-structure registry without external packages.

@impl PRS-004
@impl PRS-002
@impl PRS-003
"""

from __future__ import annotations

import argparse
import ast
import os
import re
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

MANIFEST_RELATIVE = PurePosixPath("openspec/governance/project-structure.toml")
REGISTRY_RELATIVE = PurePosixPath("openspec/governance/req-registry.yaml")
MAIN_SPEC_RELATIVE = PurePosixPath("openspec/specs/project-structure/spec.md")
SPEC_REFERENCE = "> structure: openspec/governance/project-structure.toml"
ID_RE = re.compile(r"^[A-Z]{3}-\d{3}$")
REGISTRY_ID_RE = re.compile(r"^([A-Z]{3}-\d{3}):", re.MULTILINE)
REQ_HEADER_RE = re.compile(r"^> req:\s*(.+)$", re.MULTILINE)
PACKAGE_NAME = "deerflow_deep_research"
INTERNAL_LAYERS = {"domain", "engine", "agents", "graph", "nodes", "runtime"}
REQUIRED_IMPORT_POLICY = {
    "domain": {"stdlib", "pydantic"},
    "engine": {"domain"},
    "agents": {"domain", "deerflow", "langchain"},
    "graph": {"domain", "engine", "nodes", "langgraph"},
    "nodes": {"domain", "engine", "langgraph"},
    "runtime": {"domain", "graph", "agents", "deerflow", "langchain", "langgraph"},
}


class ContractViolation(Exception):
    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail


@dataclass(frozen=True)
class RequiredPath:
    path: PurePosixPath
    kind: str
    owner: str


@dataclass(frozen=True)
class StructureManifest:
    requirement_ids: tuple[str, ...]
    guide_path: PurePosixPath
    begin_marker: str
    end_marker: str
    source_root: PurePosixPath
    test_root: PurePosixPath
    ownership_layers: tuple[str, ...]
    forbidden_source_roots: tuple[PurePosixPath, ...]
    forbidden_shared_modules: tuple[str, ...]
    required_paths: tuple[RequiredPath, ...]
    imports: dict[str, tuple[str, ...]]
    node_root: PurePosixPath
    node_required_files: tuple[str, ...]
    node_optional_files: tuple[str, ...]
    node_public_export: str


def _expect_mapping(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ContractViolation("manifest.schema", f"{label} must be a TOML table")
    return value


def _expect_string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ContractViolation("manifest.schema", f"{label} must be a non-empty string")
    return value


def _expect_string_list(value: Any, label: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not value or any(not isinstance(item, str) or not item for item in value):
        raise ContractViolation("manifest.schema", f"{label} must be a non-empty string array")
    if len(set(value)) != len(value):
        raise ContractViolation("manifest.schema", f"{label} contains duplicates")
    return tuple(value)


def _relative_path(value: Any, label: str) -> PurePosixPath:
    raw = _expect_string(value, label)
    if raw.startswith("/") or PurePosixPath(raw).is_absolute():
        raise ContractViolation("path.absolute", f"{label} must be repository-relative: {raw}")
    if "\\" in raw:
        raise ContractViolation("path.normalization", f"{label} must use POSIX separators: {raw}")
    path = PurePosixPath(raw)
    if ".." in path.parts:
        raise ContractViolation("path.traversal", f"{label} contains parent traversal: {raw}")
    if raw in {"", "."} or path.as_posix() != raw:
        raise ContractViolation("path.normalization", f"{label} is not normalized: {raw}")
    return path


def _registered_ids(root: Path) -> set[str]:
    path = root / REGISTRY_RELATIVE
    if not path.is_file():
        raise ContractViolation("owner.registry_missing", f"requirement registry is missing: {REGISTRY_RELATIVE}")
    return set(REGISTRY_ID_RE.findall(path.read_text(encoding="utf-8")))


def load_manifest(root: Path) -> StructureManifest:
    path = root / MANIFEST_RELATIVE
    if not path.is_file():
        raise ContractViolation("manifest.missing", f"structure registry is missing: {MANIFEST_RELATIVE}")
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, tomllib.TOMLDecodeError) as exc:
        raise ContractViolation("manifest.parse", f"cannot parse {MANIFEST_RELATIVE}: {exc}") from exc

    if data.get("schema_version") != 1:
        raise ContractViolation("manifest.schema", "schema_version must be integer 1")
    if data.get("contract") != "project-structure":
        raise ContractViolation("manifest.schema", "contract must be 'project-structure'")

    requirement_ids = _expect_string_list(data.get("requirement_ids"), "requirement_ids")
    if any(not ID_RE.fullmatch(requirement_id) for requirement_id in requirement_ids):
        raise ContractViolation("manifest.schema", "requirement_ids contains an invalid ID")
    registered = _registered_ids(root)
    unknown_requirements = sorted(set(requirement_ids) - registered)
    if unknown_requirements:
        raise ContractViolation(
            "owner.unknown",
            f"unregistered manifest requirement IDs: {', '.join(unknown_requirements)}",
        )

    guide = _expect_mapping(data.get("guide"), "guide")
    guide_path = _relative_path(guide.get("path"), "guide.path")
    begin_marker = _expect_string(guide.get("begin_marker"), "guide.begin_marker")
    end_marker = _expect_string(guide.get("end_marker"), "guide.end_marker")
    if begin_marker == end_marker:
        raise ContractViolation("manifest.schema", "guide markers must be distinct")

    package = _expect_mapping(data.get("package"), "package")
    source_root = _relative_path(package.get("source_root"), "package.source_root")
    test_root = _relative_path(package.get("test_root"), "package.test_root")
    ownership_layers = _expect_string_list(package.get("ownership_layers"), "package.ownership_layers")
    forbidden_source_roots = tuple(
        _relative_path(item, "package.forbidden_source_roots")
        for item in _expect_string_list(package.get("forbidden_source_roots"), "package.forbidden_source_roots")
    )
    forbidden_shared_modules = _expect_string_list(
        package.get("forbidden_shared_modules"), "package.forbidden_shared_modules"
    )

    raw_required_paths = data.get("required_paths")
    if not isinstance(raw_required_paths, list) or not raw_required_paths:
        raise ContractViolation("manifest.schema", "required_paths must be a non-empty array of tables")
    required_paths: list[RequiredPath] = []
    seen_paths: set[PurePosixPath] = set()
    for index, raw_entry in enumerate(raw_required_paths):
        entry = _expect_mapping(raw_entry, f"required_paths[{index}]")
        item_path = _relative_path(entry.get("path"), f"required_paths[{index}].path")
        if item_path in seen_paths:
            raise ContractViolation("path.duplicate", f"required path appears more than once: {item_path}")
        seen_paths.add(item_path)
        kind = _expect_string(entry.get("kind"), f"required_paths[{index}].kind")
        if kind not in {"file", "directory"}:
            raise ContractViolation("manifest.schema", f"unsupported required path kind: {kind}")
        owner = _expect_string(entry.get("owner"), f"required_paths[{index}].owner")
        if owner not in registered or owner not in requirement_ids:
            raise ContractViolation("owner.unknown", f"required path {item_path} has unknown owner {owner}")
        if any(item_path == root_path or root_path in item_path.parents for root_path in forbidden_source_roots):
            raise ContractViolation("path.forbidden_owner", f"required path is under an upstream root: {item_path}")
        required_paths.append(RequiredPath(item_path, kind, owner))

    raw_imports = _expect_mapping(data.get("imports"), "imports")
    imports = {name: _expect_string_list(values, f"imports.{name}") for name, values in raw_imports.items()}
    if set(imports) != {"domain", "engine", "agents", "graph", "nodes", "runtime"}:
        raise ContractViolation(
            "manifest.schema",
            "imports must define domain, engine, agents, graph, nodes, and runtime",
        )
    for layer, required_policy in REQUIRED_IMPORT_POLICY.items():
        if set(imports[layer]) != required_policy:
            raise ContractViolation(
                "imports.policy",
                f"imports.{layer} must match the project-structure requirement: {sorted(required_policy)}",
            )

    node_packages = _expect_mapping(data.get("node_packages"), "node_packages")
    node_root = _relative_path(node_packages.get("root"), "node_packages.root")
    node_required_files = _expect_string_list(node_packages.get("required_files"), "node_packages.required_files")
    node_optional_files = _expect_string_list(node_packages.get("optional_files"), "node_packages.optional_files")
    node_public_export = _expect_string(node_packages.get("public_export"), "node_packages.public_export")

    return StructureManifest(
        requirement_ids=requirement_ids,
        guide_path=guide_path,
        begin_marker=begin_marker,
        end_marker=end_marker,
        source_root=source_root,
        test_root=test_root,
        ownership_layers=ownership_layers,
        forbidden_source_roots=forbidden_source_roots,
        forbidden_shared_modules=forbidden_shared_modules,
        required_paths=tuple(required_paths),
        imports=imports,
        node_root=node_root,
        node_required_files=node_required_files,
        node_optional_files=node_optional_files,
        node_public_export=node_public_export,
    )


def _directory_display(path: PurePosixPath) -> str:
    return f"{path.as_posix()}/"


def render_guide_block(manifest: StructureManifest) -> str:
    required_lines = [
        f"  - `{_directory_display(item.path) if item.kind == 'directory' else item.path.as_posix()}` "
        f"({item.kind}; `{item.owner}`)"
        for item in manifest.required_paths
    ]
    lines = [
        manifest.begin_marker,
        "## Canonical Structure Contract",
        "",
        f"Registry: `{MANIFEST_RELATIVE.as_posix()}`",
        "",
        f"- Source root: `{_directory_display(manifest.source_root)}`",
        f"- Test root: `{_directory_display(manifest.test_root)}`",
        "- Ownership layers: " + ", ".join(f"`{layer}`" for layer in manifest.ownership_layers),
        "- Forbidden source roots: "
        + ", ".join(f"`{_directory_display(path)}`" for path in manifest.forbidden_source_roots),
        "- Required current paths:",
        *required_lines,
        f"- Top-level node root: `{_directory_display(manifest.node_root)}`",
        "- Required node files: " + ", ".join(f"`{name}`" for name in manifest.node_required_files),
        f"- Public node export: `{manifest.node_public_export}`",
        manifest.end_marker,
    ]
    return "\n".join(lines) + "\n"


def _validate_spec_authority(root: Path, manifest: StructureManifest) -> None:
    main_spec = root / MAIN_SPEC_RELATIVE
    if main_spec.is_file():
        text = main_spec.read_text(encoding="utf-8")
        reference_count = text.count(SPEC_REFERENCE)
        if reference_count == 0:
            raise ContractViolation("spec.reference_missing", f"active main spec lacks {SPEC_REFERENCE!r}")
        if reference_count != 1:
            raise ContractViolation("spec.reference_ambiguous", "active main spec has duplicate structure references")
        return

    changes_dir = root / "openspec" / "changes"
    active_specs = sorted(changes_dir.glob("*/specs/project-structure/spec.md")) if changes_dir.is_dir() else []
    owning_specs: list[Path] = []
    referenced_specs: list[Path] = []
    for spec_path in active_specs:
        text = spec_path.read_text(encoding="utf-8")
        header = REQ_HEADER_RE.search(text)
        declared = set(re.findall(r"[A-Z]{3}-\d{3}", header.group(1))) if header else set()
        if set(manifest.requirement_ids).issubset(declared):
            owning_specs.append(spec_path)
            if SPEC_REFERENCE in text:
                referenced_specs.append(spec_path)

    if len(referenced_specs) > 1 or len(owning_specs) > 1:
        raise ContractViolation("spec.reference_ambiguous", "more than one active delta claims structural authority")
    if len(referenced_specs) == 1 and len(owning_specs) == 1:
        return
    if owning_specs:
        raise ContractViolation("spec.reference_missing", f"pending owning delta lacks {SPEC_REFERENCE!r}")

    archived_specs = root.glob("openspec/changes/archive/*/specs/project-structure/spec.md")
    if any(SPEC_REFERENCE in path.read_text(encoding="utf-8") for path in archived_specs):
        raise ContractViolation("spec.archived_only", "an archived delta cannot be the active structural authority")
    raise ContractViolation("spec.reference_missing", "no lifecycle-appropriate project-structure spec was found")


def _validate_guide(root: Path, manifest: StructureManifest) -> None:
    path = root / manifest.guide_path
    if not path.is_file():
        raise ContractViolation("guide.marker_missing", f"module guide is missing: {manifest.guide_path}")
    text = path.read_text(encoding="utf-8")
    begin_count = text.count(manifest.begin_marker)
    end_count = text.count(manifest.end_marker)
    if begin_count == 0 or end_count == 0:
        raise ContractViolation("guide.marker_missing", "module guide lacks the generated structure markers")
    if begin_count != 1 or end_count != 1:
        raise ContractViolation(
            "guide.marker_duplicate",
            "module guide must contain exactly one generated structure block",
        )
    start = text.index(manifest.begin_marker)
    end = text.index(manifest.end_marker, start) + len(manifest.end_marker)
    actual = text[start:end]
    expected = render_guide_block(manifest).rstrip("\n")
    if actual != expected:
        raise ContractViolation("guide.drift", "generated module-guide block does not match the structure registry")


def _validate_required_paths(root: Path, manifest: StructureManifest) -> None:
    for item in manifest.required_paths:
        path = root / item.path
        if not path.exists():
            raise ContractViolation("path.missing", f"required {item.kind} is missing: {item.path}")
        if item.kind == "file" and not path.is_file():
            raise ContractViolation("path.kind", f"required file is not a file: {item.path}")
        if item.kind == "directory" and not path.is_dir():
            raise ContractViolation("path.kind", f"required directory is not a directory: {item.path}")


def _validate_single_source_root(root: Path, manifest: StructureManifest) -> None:
    excluded = {
        PurePosixPath(".git"),
        PurePosixPath(".venv"),
        PurePosixPath("_backlog"),
        PurePosixPath("frontend/.next"),
        PurePosixPath("node_modules"),
        PurePosixPath("openspec/changes/archive"),
        manifest.test_root / "fixtures",
    }

    def is_excluded(path: PurePosixPath) -> bool:
        return any(path == prefix or prefix in path.parents for prefix in excluded)

    for current, directories, _files in os.walk(root):
        relative_current = Path(current).relative_to(root)
        current_posix = PurePosixPath(relative_current.as_posix()) if relative_current.parts else PurePosixPath(".")
        directories[:] = [
            directory
            for directory in directories
            if not is_excluded(
                (current_posix / directory) if current_posix != PurePosixPath(".") else PurePosixPath(directory)
            )
        ]
        for directory in directories:
            if directory != manifest.source_root.name:
                continue
            candidate = current_posix / directory if current_posix != PurePosixPath(".") else PurePosixPath(directory)
            if candidate != manifest.source_root:
                raise ContractViolation("source.second_root", f"non-canonical package source root found: {candidate}")


def _python_files(base: Path) -> list[Path]:
    if not base.is_dir():
        return []
    excluded_names = {".git", ".venv", "venv", "node_modules", ".next", "__pycache__"}
    files: list[Path] = []
    for current, directories, names in os.walk(base):
        directories[:] = sorted(directory for directory in directories if directory not in excluded_names)
        files.extend(Path(current) / name for name in sorted(names) if name.endswith(".py"))
    return files


def _module_parts(source_root: Path, path: Path) -> tuple[str, ...]:
    parts = list(path.relative_to(source_root).with_suffix("").parts)
    if parts and parts[-1] == "__init__":
        parts.pop()
    return tuple(parts)


def _resolved_imports(tree: ast.AST, module_parts: tuple[str, ...], is_package: bool) -> list[str]:
    imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
            continue
        if not isinstance(node, ast.ImportFrom):
            continue
        if node.level:
            package_parts = module_parts if is_package else module_parts[:-1]
            ascend = node.level - 1
            if ascend > len(package_parts):
                imports.append("")
                continue
            base_parts = package_parts[: len(package_parts) - ascend]
            module_suffix = tuple(node.module.split(".")) if node.module else ()
            resolved_parts = (PACKAGE_NAME, *base_parts, *module_suffix)
        else:
            resolved_parts = tuple(node.module.split(".")) if node.module else ()
        if not resolved_parts:
            imports.append("")
            continue
        for alias in node.names:
            suffix = () if alias.name == "*" else tuple(alias.name.split("."))
            imports.append(".".join((*resolved_parts, *suffix)))
    return imports


def _source_owner(relative: PurePosixPath) -> tuple[str, str | None]:
    parts = relative.parts
    if not parts:
        return "package", None
    if parts[0] == "graph" and len(parts) >= 3 and parts[1] == "nodes":
        return "nodes", parts[2]
    if parts[0] in {"domain", "engine", "agents", "graph", "runtime"}:
        return parts[0], None
    if len(parts) == 1 and parts[0] == "tool.py":
        return "tool", None
    return "package", None


def _target_owner(module_name: str) -> tuple[str | None, str | None]:
    parts = module_name.split(".")
    if not parts or parts[0] != PACKAGE_NAME:
        return None, None
    if len(parts) == 1:
        return "package", None
    if parts[1] == "graph" and len(parts) >= 4 and parts[2] == "nodes":
        return "nodes", parts[3]
    if parts[1] in {"domain", "engine", "agents", "graph", "runtime"}:
        return parts[1], None
    return "package", None


def _external_allowed(layer: str, module_root: str, manifest: StructureManifest) -> bool:
    if module_root in sys.stdlib_module_names or module_root == "__future__":
        return True
    allowed = set(manifest.imports.get(layer, ())) - INTERNAL_LAYERS - {"stdlib"}
    if layer == "tool":
        allowed = {"langchain", "pydantic"}
    if layer == "package":
        allowed = set()
    return any(module_root == prefix or module_root.startswith(f"{prefix}_") for prefix in allowed)


def _validate_module_imports(
    root: Path,
    source_root: Path,
    path: Path,
    manifest: StructureManifest,
) -> None:
    relative = PurePosixPath(path.relative_to(source_root).as_posix())
    if path.stem in manifest.forbidden_shared_modules:
        raise ContractViolation("module.generic", f"generic shared module is forbidden: {path.relative_to(root)}")
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (OSError, UnicodeError, SyntaxError) as exc:
        raise ContractViolation("import.syntax", f"cannot parse {path.relative_to(root)}: {exc}") from exc

    layer, source_node = _source_owner(relative)
    module_parts = _module_parts(source_root, path)
    for imported in _resolved_imports(tree, module_parts, path.name == "__init__.py"):
        if not imported:
            raise ContractViolation("import.boundary", f"invalid relative import in {path.relative_to(root)}")
        module_root = imported.split(".", 1)[0]
        if module_root == "app":
            raise ContractViolation("import.app", f"production downstream code imports app.*: {path.relative_to(root)}")

        target_layer, target_node = _target_owner(imported)
        if target_layer is None:
            if layer == "nodes" and module_root == "langgraph":
                hitl_interrupt = (
                    source_node in {"hitl1", "hitl2"}
                    and path.name in {"fake.py", "node.py"}
                    and imported == "langgraph.types.interrupt"
                )
                if path.name != "subgraph.py" and not hitl_interrupt:
                    raise ContractViolation(
                        "import.boundary",
                        f"node LangGraph import is outside subgraph/HITL-interrupt exceptions: {path.relative_to(root)}",
                    )
            if not _external_allowed(layer, module_root, manifest):
                raise ContractViolation(
                    "import.external",
                    f"{path.relative_to(root)} imports undeclared external namespace {module_root}",
                )
            continue

        if layer == "nodes" and target_layer == "nodes":
            if target_node != source_node:
                raise ContractViolation(
                    "import.sibling",
                    f"node {source_node} imports sibling node {target_node}: {path.relative_to(root)}",
                )
            continue
        if layer == "nodes" and target_layer == "graph":
            component_prefix = f"{PACKAGE_NAME}.graph.components"
            if path.name == "subgraph.py" and (
                imported == component_prefix or imported.startswith(f"{component_prefix}.")
            ):
                continue
        if target_layer == layer or (layer == "package" and target_layer == "package"):
            continue
        if layer == "tool":
            allowed_internal = {"runtime"}
        elif layer == "package":
            allowed_internal = set()
        else:
            allowed_internal = set(manifest.imports[layer]) & INTERNAL_LAYERS
        if target_layer not in allowed_internal:
            raise ContractViolation(
                "import.boundary",
                f"{layer} module {path.relative_to(root)} imports forbidden {target_layer} module {imported}",
            )


def _validate_upstream_does_not_import_downstream(root: Path, manifest: StructureManifest) -> None:
    for upstream_root in manifest.forbidden_source_roots:
        for path in _python_files(root / upstream_root):
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            except (OSError, UnicodeError, SyntaxError) as exc:
                raise ContractViolation("import.syntax", f"cannot parse {path.relative_to(root)}: {exc}") from exc
            for node in ast.walk(tree):
                if isinstance(node, ast.Import) and any(
                    alias.name.split(".", 1)[0] == PACKAGE_NAME for alias in node.names
                ):
                    raise ContractViolation(
                        "source.upstream_import",
                        f"upstream module imports downstream package: {path.relative_to(root)}",
                    )
                if isinstance(node, ast.ImportFrom) and (node.module or "").split(".", 1)[0] == PACKAGE_NAME:
                    raise ContractViolation(
                        "source.upstream_import",
                        f"upstream module imports downstream package: {path.relative_to(root)}",
                    )


def _static_all_exports(path: Path) -> list[str] | None:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (OSError, UnicodeError, SyntaxError) as exc:
        raise ContractViolation("import.syntax", f"cannot parse {path}: {exc}") from exc
    for node in tree.body:
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        if not any(isinstance(target, ast.Name) and target.id == "__all__" for target in targets):
            continue
        value = node.value
        if not isinstance(value, (ast.List, ast.Tuple)):
            return None
        exports: list[str] = []
        for element in value.elts:
            if not isinstance(element, ast.Constant) or not isinstance(element.value, str):
                return None
            exports.append(element.value)
        return exports
    return None


def _validate_node_packages(root: Path, manifest: StructureManifest) -> None:
    node_root = root / manifest.node_root
    if not node_root.exists():
        return
    if not node_root.is_dir():
        raise ContractViolation("node.root_kind", f"node root is not a directory: {manifest.node_root}")
    reserved = {"components", "topology"}
    for package_root in sorted(path for path in node_root.iterdir() if path.is_dir() and path.name != "__pycache__"):
        relative = package_root.relative_to(root)
        if package_root.name in reserved:
            raise ContractViolation(
                "node.package_confusion",
                f"reusable components/topology cannot be top-level nodes: {relative}",
            )
        missing = sorted(name for name in manifest.node_required_files if not (package_root / name).is_file())
        if missing:
            raise ContractViolation(
                "node.file_missing",
                f"node package {relative} is missing {', '.join(missing)}",
            )
        exports = _static_all_exports(package_root / "__init__.py")
        if exports != [manifest.node_public_export]:
            raise ContractViolation(
                "node.exports",
                f"node package {relative} must export only {manifest.node_public_export}",
            )


def validate_imports(root: Path, manifest: StructureManifest) -> None:
    source_root = root / manifest.source_root
    if not source_root.is_dir():
        raise ContractViolation("path.missing", f"source root is missing: {manifest.source_root}")
    for path in _python_files(source_root):
        _validate_module_imports(root, source_root, path, manifest)
    _validate_upstream_does_not_import_downstream(root, manifest)
    _validate_node_packages(root, manifest)


def validate_project(root: Path, manifest: StructureManifest) -> None:
    _validate_spec_authority(root, manifest)
    _validate_guide(root, manifest)
    _validate_required_paths(root, manifest)
    _validate_single_source_root(root, manifest)
    validate_imports(root, manifest)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project_root", nargs="?", default=".")
    parser.add_argument("--render-guide", action="store_true", help="print the deterministic AGENTS.md block")
    parser.add_argument(
        "--imports-only",
        action="store_true",
        help="validate only manifest and Python import contracts",
    )
    args = parser.parse_args()
    root = Path(args.project_root).resolve()
    try:
        manifest = load_manifest(root)
        if args.render_guide:
            print(render_guide_block(manifest), end="")
            return 0
        if args.imports_only:
            validate_imports(root, manifest)
        else:
            validate_project(root, manifest)
    except ContractViolation as violation:
        print(f"ERROR [{violation.code}] {violation.detail}", file=sys.stderr)
        return 1
    print(f"Architecture governance passed for {root}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
