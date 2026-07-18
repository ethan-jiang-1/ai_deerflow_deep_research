"""Small cross-lane requirement-evidence policy and pure validator.

@impl EVH-008
@impl EVH-009
@impl EVH-010
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from pathlib import Path

from tests.assets.evidence import AssetClass, AuthenticityLevel, TestEvidenceClaim

REQUIREMENT_ID_RE = re.compile(r"[A-Z]{3}-\d{3}")
REQUIREMENT_RANGE_RE = re.compile(r"([A-Z]{3})-(\d{3})\.\.(\d{3})")
REQUIREMENT_HEADER_RE = re.compile(r"^\s*>\s*req:\s*(.+)$", re.MULTILINE)
IMPL_LINE_RE = re.compile(r"@impl\s+([^\n]+)")


class RequirementEvidenceError(ValueError):
    pass


@dataclass(frozen=True)
class RequiredEvidence:
    asset_class: AssetClass
    authenticity: AuthenticityLevel | None = None


@dataclass(frozen=True)
class RequirementEvidenceRule:
    requirement_id: str
    required_evidence: tuple[RequiredEvidence, ...]


REQUIREMENT_EVIDENCE_POLICY = (
    RequirementEvidenceRule(
        requirement_id="EVH-004",
        required_evidence=(
            RequiredEvidence(
                AssetClass.DETERMINISTIC_WORKFLOW_CONFORMANCE,
                AuthenticityLevel.SCRIPTED_REAL_WORKFLOW,
            ),
        ),
    ),
    RequirementEvidenceRule(
        requirement_id="EVH-005",
        required_evidence=(
            RequiredEvidence(AssetClass.CODE_CORRECTNESS),
            RequiredEvidence(
                AssetClass.LIVE_BEHAVIORAL_EVALUATION,
                AuthenticityLevel.LIVE_REAL_DEPENDENCIES,
            ),
            RequiredEvidence(
                AssetClass.RELEASE_ACCEPTANCE,
                AuthenticityLevel.FULL_REAL_PIPELINE,
            ),
        ),
    ),
    RequirementEvidenceRule(
        requirement_id="EVH-008",
        required_evidence=(
            RequiredEvidence(
                AssetClass.DETERMINISTIC_WORKFLOW_CONFORMANCE,
                AuthenticityLevel.SCRIPTED_REAL_WORKFLOW,
            ),
        ),
    ),
)


def validate_requirement_evidence(
    *,
    policy: tuple[RequirementEvidenceRule, ...],
    claims: tuple[TestEvidenceClaim, ...],
    alive_requirement_ids: set[str],
    deterministic_impl_ids: set[str],
    collected_selectors: set[str],
) -> None:
    missing_impl = sorted(alive_requirement_ids - deterministic_impl_ids)
    if missing_impl:
        raise RequirementEvidenceError(f"missing deterministic @impl: {','.join(missing_impl)}")
    unknown_impl = sorted(deterministic_impl_ids - alive_requirement_ids)
    if unknown_impl:
        raise RequirementEvidenceError(f"unknown deterministic @impl: {','.join(unknown_impl)}")

    seen_rules: set[str] = set()
    for rule in policy:
        if rule.requirement_id not in alive_requirement_ids:
            raise RequirementEvidenceError(f"unknown policy requirement: {rule.requirement_id}")
        if rule.requirement_id in seen_rules:
            raise RequirementEvidenceError(f"duplicate policy requirement: {rule.requirement_id}")
        seen_rules.add(rule.requirement_id)
        matching = tuple(
            claim
            for claim in claims
            if rule.requirement_id in claim.requirement_ids and claim.selector in collected_selectors
        )
        for required in rule.required_evidence:
            if not any(
                claim.asset_class is required.asset_class
                and (required.authenticity is None or claim.authenticity is required.authenticity)
                for claim in matching
            ):
                suffix = f"/{required.authenticity.value}" if required.authenticity is not None else ""
                raise RequirementEvidenceError(
                    f"requirement evidence missing: {rule.requirement_id} {required.asset_class.value}{suffix}"
                )


def load_alive_requirement_ids(project_root: Path) -> set[str]:
    spec_root = project_root / "openspec/specs"
    alive: set[str] = set()
    for path in sorted(spec_root.rglob("*.md")):
        for header in REQUIREMENT_HEADER_RE.findall(path.read_text(encoding="utf-8")):
            alive.update(_expand_requirement_ids(header))
    return alive


def collected_deterministic_impl_ids(agent_root: Path, selectors: set[str]) -> set[str]:
    paths = {selector.split("::", 1)[0] for selector in selectors}
    requirement_ids: set[str] = set()
    for relative_path in sorted(paths):
        path = agent_root / relative_path
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        docstrings = [ast.get_docstring(tree, clean=False) or ""]
        docstrings.extend(
            ast.get_docstring(node, clean=False) or ""
            for node in ast.walk(tree)
            if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
        )
        for docstring in docstrings:
            for payload in IMPL_LINE_RE.findall(docstring):
                requirement_ids.update(_expand_requirement_ids(payload))
    return requirement_ids


def _expand_requirement_ids(value: str) -> set[str]:
    ids = set(REQUIREMENT_ID_RE.findall(value))
    for prefix, start, end in REQUIREMENT_RANGE_RE.findall(value):
        if int(start) <= int(end):
            ids.update(f"{prefix}-{number:03d}" for number in range(int(start), int(end) + 1))
    return ids


__all__ = [
    "REQUIREMENT_EVIDENCE_POLICY",
    "RequiredEvidence",
    "RequirementEvidenceError",
    "RequirementEvidenceRule",
    "collected_deterministic_impl_ids",
    "load_alive_requirement_ids",
    "validate_requirement_evidence",
]
