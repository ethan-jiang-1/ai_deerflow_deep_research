#!/usr/bin/env python3
"""Verify requirement IDs are backed by deterministic test modules.

@impl EVH-009
@impl EVH-010
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

ID_RE = re.compile(r"[A-Z]{3}-\d{3}")
RANGE_RE = re.compile(r"([A-Z]{3})-(\d{3})\.\.(\d{3})")
REQ_HEADER_RE = re.compile(r"^\s*>\s*req:\s*(.+)$", re.MULTILINE)
REGISTRY_RE = re.compile(r"^([A-Z]{3}-\d{3}):", re.MULTILINE)
IMPL_LINE_RE = re.compile(r"@impl\s+([^\n]+)")


def _expand_ids(text: str) -> set[str]:
    ids = set(ID_RE.findall(text))
    for prefix, start, end in RANGE_RE.findall(text):
        first, last = int(start), int(end)
        if first <= last:
            ids.update(f"{prefix}-{value:03d}" for value in range(first, last + 1))
    return ids


def _declared_requirements(root: Path) -> set[str]:
    declared: set[str] = set()
    locations = [root / "openspec" / "specs"]
    changes = root / "openspec" / "changes"
    if changes.exists():
        locations.extend(path / "specs" for path in changes.iterdir() if path.is_dir() and path.name != "archive")
    for location in locations:
        if not location.exists():
            continue
        for path in location.rglob("*.md"):
            text = path.read_text(encoding="utf-8")
            for header in REQ_HEADER_RE.findall(text):
                declared.update(_expand_ids(header))
    return declared


def _test_references(root: Path) -> tuple[set[str], list[str]]:
    references: set[str] = set()
    parse_errors: list[str] = []
    tests = root / "agent" / "tests"
    if not tests.exists():
        return references, parse_errors
    for path in sorted(tests.rglob("test_*.py")):
        text = path.read_text(encoding="utf-8")
        try:
            tree = ast.parse(text, filename=str(path))
        except SyntaxError as exc:
            parse_errors.append(f"{path.relative_to(root)}:{exc.lineno}: test parse failed")
            continue
        has_test = any(
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test_")
            for node in ast.walk(tree)
        )
        if not has_test:
            continue
        docstrings: list[str] = []
        module_docstring = ast.get_docstring(tree, clean=False)
        if module_docstring:
            docstrings.append(module_docstring)
        for node in ast.walk(tree):
            if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                docstring = ast.get_docstring(node, clean=False)
                if docstring:
                    docstrings.append(docstring)
        for docstring in docstrings:
            for payload in IMPL_LINE_RE.findall(docstring):
                references.update(_expand_ids(payload))
    return references, parse_errors


def check(root: Path) -> list[str]:
    registry = root / "openspec" / "governance" / "req-registry.yaml"
    if not registry.exists():
        return [f"registry missing: {registry}"]
    registered = set(REGISTRY_RE.findall(registry.read_text(encoding="utf-8")))
    required = _declared_requirements(root)
    references, errors = _test_references(root)
    for requirement_id in sorted(references - registered):
        errors.append(f"unknown test requirement: {requirement_id}")
    for requirement_id in sorted(required - references):
        errors.append(f"uncovered requirement: {requirement_id}")
    return errors


def main() -> int:
    root = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd().resolve()
    errors = check(root)
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1
    print("Requirement-to-test coverage passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
