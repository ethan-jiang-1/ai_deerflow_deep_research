#!/usr/bin/env python3
"""Validate incident mappings against the deterministic pytest collection.

@impl EVH-006
@impl EVH-009
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

AGENT_ROOT = Path(__file__).resolve().parents[1]
if str(AGENT_ROOT) not in sys.path:
    sys.path.insert(0, str(AGENT_ROOT))

from deerflow_deep_research.graph.registry import load_research_node_specs  # noqa: E402
from tests.assets.evidence import (  # noqa: E402
    EVIDENCE_CLAIMS,
    EvidenceClaimError,
    FocusedSelection,
    claim_index,
    validate_claim_selections,
    validate_inventory_claim_references,
)
from tests.assets.fault_matrix import CRITICAL_FAULTS, FaultMatrixError, validate_fault_matrix  # noqa: E402
from tests.assets.inventory import INCIDENTS, CoverageError, validate_incident_coverage  # noqa: E402
from tests.assets.node_conformance import (  # noqa: E402
    NODE_CONFORMANCE,
    NodeConformanceError,
    validate_node_conformance,
)
from tests.assets.provider_shapes import (  # noqa: E402
    LIVE_DISCOVERY_DISPOSITIONS,
    RELEASE_DISCOVERY_DISPOSITIONS_01_14,
    RELEASE_DISCOVERY_DISPOSITIONS_15_25,
    load_provider_shape_archive,
    validate_provider_shape_catalog,
)
from tests.assets.requirement_evidence import (  # noqa: E402
    REQUIREMENT_EVIDENCE_POLICY,
    RequirementEvidenceError,
    collected_deterministic_impl_ids,
    load_alive_requirement_ids,
    validate_requirement_evidence,
)
from tests.assets.selection import (  # noqa: E402
    DETERMINISTIC_EXCLUDE,
    FAST_EXPRESSION,
    FAST_PATHS,
    INTEGRATION_EXPRESSION,
    INTEGRATION_PATHS,
    LIVE_EXPRESSION,
    LIVE_PATHS,
    RELEASE_EXPRESSION,
    RELEASE_PATHS,
    WORKFLOW_EXPRESSION,
    WORKFLOW_PATHS,
)
from tests.assets.workflow_nodes import (  # noqa: E402
    MODEL_WORKFLOW_COVERAGE,
    WorkflowCoverageError,
    discover_run_agent_owners,
    validate_model_workflow_coverage,
)
from tests.scenarios.canaries import LIVE_CANARIES  # noqa: E402
from tests.scenarios.governance import ScenarioGovernanceError, validate_real_scenario_catalog  # noqa: E402
from tests.scenarios.replays import (  # noqa: E402
    FIRST_WAVE_CASES,
    FIRST_WAVE_FAMILIES,
    REQUIRED_FIRST_WAVE_FAMILY_IDS,
)

NODE_ROOT = AGENT_ROOT / "src/deerflow_deep_research/graph/nodes"
PROVIDER_SHAPE_ROOT = AGENT_ROOT / "tests/fixtures/provider_shapes"
PROVIDER_DISCOVERY_IDS = {
    *(f"LIVE-20260717-{index:02d}" for index in range(1, 7)),
    *(f"RELEASE-20260717-{index:02d}" for index in range(1, 26)),
}
PROVIDER_DISCOVERY_DISPOSITIONS = (
    *LIVE_DISCOVERY_DISPOSITIONS,
    *RELEASE_DISCOVERY_DISPOSITIONS_01_14,
    *RELEASE_DISCOVERY_DISPOSITIONS_15_25,
)


def collect_pytest_selectors(
    *,
    paths: tuple[str, ...],
    expression: str,
    label: str,
    agent_root: Path = AGENT_ROOT,
    command: tuple[str, ...] = ("uv", "run", "--extra", "operations", "pytest"),
) -> set[str]:
    result = subprocess.run(
        [
            *command,
            "--collect-only",
            "-q",
            *paths,
            "-m",
            expression,
        ],
        cwd=agent_root,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise CoverageError(f"{label} pytest collection failed:\n{result.stderr or result.stdout}")
    selectors = {line.strip() for line in result.stdout.splitlines() if "::" in line and not line.startswith("=")}
    if not selectors:
        raise CoverageError(f"{label} pytest collection returned no selectors")
    return selectors


def collect_deterministic_selectors(agent_root: Path = AGENT_ROOT) -> set[str]:
    return collect_pytest_selectors(
        paths=("tests",),
        expression=f"not ({DETERMINISTIC_EXCLUDE})",
        label="deterministic aggregate",
        agent_root=agent_root,
    )


def main() -> int:
    try:
        collected = collect_deterministic_selectors()
        focused = {
            FocusedSelection.FAST: collect_pytest_selectors(
                paths=FAST_PATHS,
                expression=FAST_EXPRESSION,
                label="fast",
            ),
            FocusedSelection.INTEGRATION: collect_pytest_selectors(
                paths=INTEGRATION_PATHS,
                expression=INTEGRATION_EXPRESSION,
                label="integration",
            ),
            FocusedSelection.WORKFLOW: collect_pytest_selectors(
                paths=WORKFLOW_PATHS,
                expression=WORKFLOW_EXPRESSION,
                label="workflow",
            ),
            FocusedSelection.LIVE: collect_pytest_selectors(
                paths=LIVE_PATHS,
                expression=LIVE_EXPRESSION,
                label="live",
            ),
            FocusedSelection.RELEASE: collect_pytest_selectors(
                paths=RELEASE_PATHS,
                expression=RELEASE_EXPRESSION,
                label="release",
            ),
        }
        claims = claim_index(EVIDENCE_CLAIMS)
        validate_claim_selections(EVIDENCE_CLAIMS, focused_selectors=focused)
        validate_requirement_evidence(
            policy=REQUIREMENT_EVIDENCE_POLICY,
            claims=EVIDENCE_CLAIMS,
            alive_requirement_ids=load_alive_requirement_ids(AGENT_ROOT.parent),
            deterministic_impl_ids=collected_deterministic_impl_ids(AGENT_ROOT, collected),
            collected_selectors=set().union(*focused.values()),
        )
        validate_inventory_claim_references(
            (
                *((f"incident:{entry.incident_id}", entry.claim_ids) for entry in INCIDENTS),
                *(
                    (f"node:{entry.logical_name}", (entry.success_claim_id, entry.risk_claim_id))
                    for entry in NODE_CONFORMANCE
                ),
                *((f"fault:{entry.fault.value}", (entry.claim_id,)) for entry in CRITICAL_FAULTS),
            ),
            claims=claims,
        )
        validate_incident_coverage(INCIDENTS, claims, collected, excluded_selectors=set())
        validate_node_conformance(
            NODE_CONFORMANCE,
            claims,
            collected,
            registered_names=set(load_research_node_specs()),
        )
        validate_fault_matrix(CRITICAL_FAULTS, claims, collected)
        validate_model_workflow_coverage(
            MODEL_WORKFLOW_COVERAGE,
            claims=claims,
            discovered_owners=discover_run_agent_owners(NODE_ROOT),
            workflow_selectors=focused[FocusedSelection.WORKFLOW],
        )
        validate_real_scenario_catalog(
            FIRST_WAVE_FAMILIES,
            FIRST_WAVE_CASES,
            EVIDENCE_CLAIMS,
            deterministic_selectors=collected,
            workflow_selectors=focused[FocusedSelection.WORKFLOW],
            required_family_ids=REQUIRED_FIRST_WAVE_FAMILY_IDS,
        )
        try:
            validate_provider_shape_catalog(
                PROVIDER_DISCOVERY_DISPOSITIONS,
                cases=load_provider_shape_archive(PROVIDER_SHAPE_ROOT),
                required_discovery_ids=PROVIDER_DISCOVERY_IDS,
                claims=claims,
                collected_selectors=set().union(*focused.values()),
                live_case_ids={case.scenario_id for case in LIVE_CANARIES},
            )
        except ValueError as exc:
            raise CoverageError(f"provider-shape catalog invalid: {exc}") from exc
    except (
        CoverageError,
        EvidenceClaimError,
        FaultMatrixError,
        NodeConformanceError,
        ScenarioGovernanceError,
        RequirementEvidenceError,
        WorkflowCoverageError,
    ) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(
        f"Test asset coverage passed: {len(INCIDENTS)} incidents, "
        f"{len(NODE_CONFORMANCE)} real nodes, {len(CRITICAL_FAULTS)} critical faults, "
        f"{len(MODEL_WORKFLOW_COVERAGE)} model-workflow nodes, "
        f"{len(EVIDENCE_CLAIMS)} central claims, {len(collected)} deterministic tests; "
        + ", ".join(f"{selection.value}={len(focused[selection])}" for selection in FocusedSelection)
        + "."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
