"""Syntax-discovered real-bridge workflow ownership contracts.

@impl EVH-008
@impl EVH-009
"""

from __future__ import annotations

import subprocess
from dataclasses import replace
from pathlib import Path

import pytest

from tests.assets.evidence import EVIDENCE_CLAIMS, AssetClass, AuthenticityLevel, FocusedSelection, claim_index
from tests.assets.workflow_nodes import (
    MODEL_WORKFLOW_COVERAGE,
    WorkflowCoverageError,
    discover_run_agent_owners,
    validate_model_workflow_coverage,
)

NODE_ROOT = Path("src/deerflow_deep_research/graph/nodes")
EXPECTED_OWNERS = {
    "hitl1",
    "topic_planning",
    "wave0",
    "wave1",
    "wave2_synthesis",
    "targeted_evidence",
}


def _collect_workflow_selectors() -> set[str]:
    result = subprocess.run(
        ["uv", "run", "--extra", "operations", "pytest", "--collect-only", "-q", "-m", "workflow"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr or result.stdout
    return {line.strip() for line in result.stdout.splitlines() if "::" in line and not line.startswith("=")}


def test_ast_discovery_finds_exact_loaded_run_agent_owners() -> None:
    assert discover_run_agent_owners(NODE_ROOT) == EXPECTED_OWNERS


def test_every_discovered_owner_has_scripted_real_workflow_claim() -> None:
    claims = claim_index(EVIDENCE_CLAIMS)

    validate_model_workflow_coverage(
        MODEL_WORKFLOW_COVERAGE,
        claims=claims,
        discovered_owners=discover_run_agent_owners(NODE_ROOT),
        workflow_selectors=_collect_workflow_selectors(),
    )

    assert {entry.logical_name for entry in MODEL_WORKFLOW_COVERAGE} == EXPECTED_OWNERS


@pytest.mark.parametrize("field", ["asset_class", "authenticity"])
def test_downgraded_workflow_claim_reports_node_id(field: str) -> None:
    claims = claim_index(EVIDENCE_CLAIMS)
    entry = MODEL_WORKFLOW_COVERAGE[0]
    claim = claims[entry.claim_id]
    downgraded = replace(
        claim,
        **(
            {"asset_class": AssetClass.CODE_CORRECTNESS, "expected_selection": FocusedSelection.FAST}
            if field == "asset_class"
            else {"authenticity": AuthenticityLevel.REAL_NODE_FAKE_CAPABILITIES}
        ),
    )
    claims[entry.claim_id] = downgraded

    with pytest.raises(WorkflowCoverageError, match=entry.logical_name):
        validate_model_workflow_coverage(
            MODEL_WORKFLOW_COVERAGE,
            claims=claims,
            discovered_owners=EXPECTED_OWNERS,
            workflow_selectors={claim.selector},
        )


def test_missing_workflow_selector_reports_node_id() -> None:
    claims = claim_index(EVIDENCE_CLAIMS)
    entry = MODEL_WORKFLOW_COVERAGE[0]

    with pytest.raises(WorkflowCoverageError, match=entry.logical_name):
        validate_model_workflow_coverage(
            MODEL_WORKFLOW_COVERAGE,
            claims=claims,
            discovered_owners=EXPECTED_OWNERS,
            workflow_selectors=set(),
        )


def test_known_violation_smoke_rejects_empty_or_mis_scoped_discovery(tmp_path: Path) -> None:
    empty_root = tmp_path / "nodes"
    empty_root.mkdir()

    discovered = discover_run_agent_owners(empty_root)
    assert discovered == set()
    with pytest.raises(WorkflowCoverageError, match="hitl1"):
        validate_model_workflow_coverage(
            MODEL_WORKFLOW_COVERAGE,
            claims=claim_index(EVIDENCE_CLAIMS),
            discovered_owners=discovered,
            workflow_selectors=set(),
        )


def test_ast_classification_accepts_call_and_method_reference_but_not_name_or_store(tmp_path: Path) -> None:
    root = tmp_path / "nodes"
    for owner, source in {
        "direct": "async def run(c):\n    return await c.run_agent()\n",
        "reference": "def bind(c):\n    return consume(c.run_agent)\n",
        "name_only": "def run_agent():\n    return None\n",
        "store_only": "def bind(c):\n    c.run_agent = None\n",
    }.items():
        package = root / owner
        package.mkdir(parents=True)
        (package / "node.py").write_text(source, encoding="utf-8")

    assert discover_run_agent_owners(root) == {"direct", "reference"}
