"""Shared assertions over one declared case and one authority observation.

@impl EVH-001
@impl EVH-007
"""

from __future__ import annotations

from dataclasses import dataclass

from tests.scenarios.contracts import ScenarioCase, ScenarioFamily
from tests.scenarios.observation import InvariantName, ScenarioObservation, evaluate_invariants


@dataclass(frozen=True)
class ScenarioAssertionResult:
    family_id: str
    case_id: str
    invariant_results: tuple[tuple[InvariantName, bool], ...]


class ScenarioAssertionError(AssertionError):
    pass


def assert_scenario(
    family: ScenarioFamily,
    case: ScenarioCase,
    observation: ScenarioObservation,
) -> ScenarioAssertionResult:
    identity = f"family={family.family_id} case={case.case_id} lane={case.lane.value}"
    errors: list[str] = []
    if case.family_id != family.family_id:
        errors.append(f"family binding expected={case.family_id} actual={family.family_id}")

    expected = case.expectations
    checkpoint = observation.checkpoint
    if expected.route is not None and checkpoint.route != expected.route:
        errors.append(f"route expected={expected.route} actual={checkpoint.route}")
    if expected.terminal is not None and checkpoint.terminal != expected.terminal:
        errors.append(f"terminal expected={expected.terminal} actual={checkpoint.terminal}")

    observed_artifacts = {path for path, _content_hash in observation.sandbox.artifact_hashes}
    missing_artifacts = set(expected.artifacts) - observed_artifacts
    if missing_artifacts:
        errors.append(f"artifacts missing={sorted(missing_artifacts)}")

    accepted = set(observation.ledger.accepted_refs)
    missing_support = set(expected.support) - accepted
    if missing_support:
        errors.append(f"support missing={sorted(missing_support)}")

    observed_citations = {claim_id for claim_id, _refs in observation.sandbox.citation_bindings}
    missing_citations = set(expected.citations) - observed_citations
    if missing_citations:
        errors.append(f"citations missing={sorted(missing_citations)}")

    if observation.degradation is not None and (
        observation.degradation not in family.permitted_degradation
        or observation.degradation not in expected.permitted_degradation
    ):
        errors.append(f"degradation not permitted={observation.degradation}")

    invariants = tuple(case.hard_invariants)
    invariant_results = evaluate_invariants(
        observation,
        invariants,
        max_attempts=case.bounds.max_attempts,
        expected_route=expected.route,
    )
    for name, passed in invariant_results.items():
        if not passed:
            errors.append(f"invariant failed={name.value}")

    if errors:
        raise ScenarioAssertionError(f"{identity}: {'; '.join(errors)}")
    return ScenarioAssertionResult(
        family_id=family.family_id,
        case_id=case.case_id,
        invariant_results=tuple(invariant_results.items()),
    )


__all__ = ["ScenarioAssertionError", "ScenarioAssertionResult", "assert_scenario"]
