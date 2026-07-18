"""Syntax-discovered production owners of real model workflow coverage.

@impl EVH-008
@impl EVH-009
"""

from __future__ import annotations

import ast
from collections.abc import Iterable, Mapping, Set
from dataclasses import dataclass
from pathlib import Path

from tests.assets.evidence import (
    AssetClass,
    AuthenticityLevel,
    FocusedSelection,
    TestEvidenceClaim,
)


@dataclass(frozen=True)
class ModelWorkflowCoverage:
    logical_name: str
    claim_id: str


class WorkflowCoverageError(ValueError):
    pass


MODEL_WORKFLOW_COVERAGE = (
    ModelWorkflowCoverage("hitl1", "workflow-hitl1-zero-tool-bridge"),
    ModelWorkflowCoverage("topic_planning", "workflow-topic-planning-zero-tool-bridge"),
    ModelWorkflowCoverage("wave0", "workflow-wave0-worker-bridge"),
    ModelWorkflowCoverage("wave1", "workflow-wave1-worker-bridge"),
    ModelWorkflowCoverage("wave2_synthesis", "workflow-wave2-zero-tool-bridge"),
    ModelWorkflowCoverage("targeted_evidence", "workflow-targeted-evidence-worker-bridge"),
)


def discover_run_agent_owners(node_root: Path) -> set[str]:
    """Discover node packages that load a ``.run_agent`` method reference."""
    owners: set[str] = set()
    if not node_root.is_dir():
        return owners
    for package in sorted(path for path in node_root.iterdir() if path.is_dir()):
        for source_path in sorted(package.rglob("*.py")):
            try:
                tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))
            except (OSError, SyntaxError) as exc:
                raise WorkflowCoverageError(f"{package.name}: cannot inspect {source_path}: {exc}") from exc
            if any(
                isinstance(node, ast.Attribute) and node.attr == "run_agent" and isinstance(node.ctx, ast.Load)
                for node in ast.walk(tree)
            ):
                owners.add(package.name)
                break
    return owners


def validate_model_workflow_coverage(
    entries: Iterable[ModelWorkflowCoverage],
    *,
    claims: Mapping[str, TestEvidenceClaim],
    discovered_owners: Set[str],
    workflow_selectors: Set[str],
) -> None:
    entries = tuple(entries)
    errors: list[str] = []
    by_owner: dict[str, ModelWorkflowCoverage] = {}
    for entry in entries:
        if entry.logical_name in by_owner:
            errors.append(f"{entry.logical_name}: duplicate workflow inventory entry")
        by_owner[entry.logical_name] = entry

    for owner in sorted(discovered_owners - by_owner.keys()):
        errors.append(f"{owner}: discovered run_agent owner lacks workflow coverage")
    for owner in sorted(by_owner.keys() - discovered_owners):
        errors.append(f"{owner}: workflow coverage has no discovered run_agent owner")

    for entry in entries:
        claim = claims.get(entry.claim_id)
        if claim is None:
            errors.append(f"{entry.logical_name}: unknown workflow claim {entry.claim_id}")
            continue
        if claim.asset_class is not AssetClass.DETERMINISTIC_WORKFLOW_CONFORMANCE:
            errors.append(f"{entry.logical_name}: {entry.claim_id} is not workflow conformance")
        if claim.expected_selection is not FocusedSelection.WORKFLOW:
            errors.append(f"{entry.logical_name}: {entry.claim_id} is not assigned to workflow selection")
        if claim.authenticity is not AuthenticityLevel.SCRIPTED_REAL_WORKFLOW:
            errors.append(f"{entry.logical_name}: {entry.claim_id} lacks scripted real workflow authenticity")
        if claim.selector not in workflow_selectors:
            errors.append(f"{entry.logical_name}: uncollected workflow selector {claim.selector}")

    if errors:
        raise WorkflowCoverageError("\n".join(errors))


__all__ = [
    "MODEL_WORKFLOW_COVERAGE",
    "ModelWorkflowCoverage",
    "WorkflowCoverageError",
    "discover_run_agent_owners",
    "validate_model_workflow_coverage",
]
