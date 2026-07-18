"""Scenario-to-evidence joins and real-catalog closure.

@impl EVH-001
@impl EVH-007
@impl EVH-009
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Set

from tests.assets.evidence import (
    AssetClass,
    FocusedSelection,
    TestEvidenceClaim,
)
from tests.scenarios.contracts import ScenarioCase, ScenarioFamily, ScenarioLane, validate_scenario_registry
from tests.scenarios.observation import ScenarioObservation


class ScenarioGovernanceError(ValueError):
    pass


def validate_real_scenario_catalog(
    families: Iterable[ScenarioFamily],
    cases: Iterable[ScenarioCase],
    claims: Iterable[TestEvidenceClaim],
    *,
    deterministic_selectors: Set[str],
    workflow_selectors: Set[str],
    required_family_ids: Set[str] | None = None,
) -> None:
    families = tuple(families)
    cases = tuple(cases)
    claims = tuple(claims)
    errors: list[str] = []
    family_ids = {family.family_id for family in families}
    if required_family_ids is not None and family_ids != set(required_family_ids):
        missing = sorted(set(required_family_ids) - family_ids)
        unknown = sorted(family_ids - set(required_family_ids))
        errors.append(f"family catalog mismatch: missing={missing} unknown={unknown}")
    cases_by_family = {family_id: [] for family_id in family_ids}
    for case in cases:
        if case.family_id in cases_by_family:
            cases_by_family[case.family_id].append(case)
    for family_id, bound_cases in sorted(cases_by_family.items()):
        if not any(case.lane is ScenarioLane.DETERMINISTIC for case in bound_cases):
            errors.append(f"{family_id}: no deterministic case")

    claims_by_case: dict[str, list[TestEvidenceClaim]] = {case.case_id: [] for case in cases}
    for claim in claims:
        if claim.scenario_case_id in claims_by_case:
            claims_by_case[claim.scenario_case_id].append(claim)
    for case in cases:
        bound_claims = claims_by_case[case.case_id]
        if len(bound_claims) != 1:
            errors.append(f"{case.case_id}: resolves to {len(bound_claims)} evidence claims")
            continue
        claim = bound_claims[0]
        if claim.selector not in deterministic_selectors:
            errors.append(f"{case.case_id}: uncollected deterministic selector {claim.selector}")
        if claim.asset_class is not case.asset_class:
            errors.append(f"{case.case_id}: asset class mismatch")
        if claim.seam is not case.seam:
            errors.append(f"{case.case_id}: seam mismatch")
        if claim.authenticity is not case.authenticity:
            errors.append(f"{case.case_id}: authenticity mismatch")
        is_workflow = case.asset_class is AssetClass.DETERMINISTIC_WORKFLOW_CONFORMANCE
        if is_workflow and claim.selector not in workflow_selectors:
            errors.append(f"{case.case_id}: workflow case missing from workflow selection")
        if not is_workflow and claim.selector in workflow_selectors:
            errors.append(f"{case.case_id}: non-workflow case collected by workflow")

    if errors:
        raise ScenarioGovernanceError("\n".join(errors))


def validate_scenario_evidence(
    families: Iterable[ScenarioFamily],
    cases: Iterable[ScenarioCase],
    claims: Iterable[TestEvidenceClaim],
    *,
    observations: Mapping[str, ScenarioObservation],
    collected_selectors: Set[str],
) -> None:
    families = tuple(families)
    cases = tuple(cases)
    claims = tuple(claims)
    validate_scenario_registry(families, cases)
    errors: list[str] = []
    claims_by_case: dict[str, list[TestEvidenceClaim]] = {case.case_id: [] for case in cases}
    for claim in claims:
        if claim.scenario_case_id in claims_by_case:
            claims_by_case[claim.scenario_case_id].append(claim)

    for case in cases:
        bound_claims = claims_by_case[case.case_id]
        if not bound_claims:
            errors.append(f"{case.case_id}: no evidence claim")
            continue
        if len(bound_claims) != 1:
            errors.append(f"{case.case_id}: resolves to {len(bound_claims)} evidence claims")
            continue
        claim = bound_claims[0]
        if f"[{case.case_id}]" not in claim.selector:
            errors.append(f"{case.case_id}: selector lacks stable pytest parameter id: {claim.selector}")
        if claim.selector not in collected_selectors:
            errors.append(f"{case.case_id}: uncollected selector {claim.selector}")
        if claim.asset_class is not case.asset_class:
            errors.append(
                f"{case.case_id}: asset class mismatch case={case.asset_class.value} claim={claim.asset_class.value}"
            )
        if claim.seam is not case.seam:
            errors.append(f"{case.case_id}: seam mismatch case={case.seam.value} claim={claim.seam.value}")
        if claim.authenticity is not case.authenticity:
            case_authenticity = case.authenticity.value if case.authenticity is not None else "none"
            claim_authenticity = claim.authenticity.value if claim.authenticity is not None else "none"
            errors.append(f"{case.case_id}: authenticity mismatch case={case_authenticity} claim={claim_authenticity}")
        if (
            case.asset_class is AssetClass.DETERMINISTIC_WORKFLOW_CONFORMANCE
            and claim.expected_selection is not FocusedSelection.WORKFLOW
        ):
            errors.append(f"{case.case_id}: workflow case claim is not in workflow selection")
        if case.lane is ScenarioLane.DETERMINISTIC and claim.expected_selection not in {
            FocusedSelection.FAST,
            FocusedSelection.INTEGRATION,
            FocusedSelection.WORKFLOW,
        }:
            errors.append(f"{case.case_id}: deterministic case claim is credentialed")
        if case.case_id not in observations:
            errors.append(f"{case.case_id}: missing authority observation")

    unknown_observations = set(observations) - {case.case_id for case in cases}
    for case_id in sorted(unknown_observations):
        errors.append(f"{case_id}: observation has no supplied case")

    if errors:
        raise ScenarioGovernanceError("\n".join(errors))


__all__ = ["ScenarioGovernanceError", "validate_real_scenario_catalog", "validate_scenario_evidence"]
