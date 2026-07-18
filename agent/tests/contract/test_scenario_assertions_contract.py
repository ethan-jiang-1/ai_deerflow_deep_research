"""Shared scenario assertion interface contracts.

@impl EVH-001
@impl EVH-007
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from tests.assets.evidence import AssetClass, AuthenticityLevel, StableSeam
from tests.scenarios.assertions import ScenarioAssertionError, assert_scenario
from tests.scenarios.contracts import (
    ScenarioBounds,
    ScenarioCase,
    ScenarioExpectations,
    ScenarioFamily,
    ScenarioLane,
)
from tests.scenarios.inputs import ScenarioInputs
from tests.scenarios.observation import (
    CheckpointFacts,
    InvariantName,
    LedgerFacts,
    SandboxFacts,
    ScenarioObservation,
)


def _family() -> ScenarioFamily:
    return ScenarioFamily(
        family_id="quick-factual",
        risk_intent="Produce one bounded supported answer.",
        requirement_ids=("EVH-001",),
        regression_ids=(),
        permitted_degradation=("insufficient-evidence",),
    )


def _case(**overrides: object) -> ScenarioCase:
    values: dict[str, object] = {
        "case_id": "quick-factual-scripted",
        "family_id": "quick-factual",
        "lane": ScenarioLane.DETERMINISTIC,
        "entrypoint": "wave0-worker",
        "asset_class": AssetClass.DETERMINISTIC_WORKFLOW_CONFORMANCE,
        "seam": StableSeam.RUNTIME_INTEGRATION,
        "authenticity": AuthenticityLevel.SCRIPTED_REAL_WORKFLOW,
        "preconditions": ("contained-workspace",),
        "inputs": ScenarioInputs(),
        "bounds": ScenarioBounds(1, 3, 2, 10),
        "expectations": ScenarioExpectations(
            route="pass",
            terminal="completed",
            artifacts=("final/report.md",),
            support=("h_accepted",),
            citations=("claim-1",),
        ),
        "hard_invariants": (
            InvariantName.ROUTE_EXPECTED,
            InvariantName.TERMINAL_COMPLETED,
            InvariantName.ACCEPTED_AUTHORITY,
            InvariantName.PATHS_CONTAINED,
            InvariantName.CITATIONS_BOUND,
        ),
        "applicable_metrics": ("citation-binding-rate",),
    }
    values.update(overrides)
    return ScenarioCase(**values)


def _observation(**overrides: object) -> ScenarioObservation:
    values: dict[str, object] = {
        "checkpoint": CheckpointFacts("pass", "completed", True, 1),
        "ledger": LedgerFacts(("h_accepted",), False, True),
        "sandbox": SandboxFacts(
            True,
            (("final/report.md", "h_report"),),
            (("claim-1", ("h_accepted",)),),
        ),
        "diagnostic_codes": ("completed",),
        "degradation": None,
    }
    values.update(overrides)
    return ScenarioObservation(**values)


def test_shared_assertion_checks_all_case_expectations_and_invariants() -> None:
    result = assert_scenario(_family(), _case(), _observation())

    assert result.family_id == "quick-factual"
    assert result.case_id == "quick-factual-scripted"
    assert all(passed for _name, passed in result.invariant_results)


@pytest.mark.parametrize(
    ("observation", "message"),
    [
        (_observation(checkpoint=CheckpointFacts("repair", "completed", True, 1)), "route"),
        (_observation(checkpoint=CheckpointFacts("pass", "blocked", True, 1)), "terminal"),
        (_observation(sandbox=SandboxFacts(True, (), (("claim-1", ("h_accepted",)),))), "artifacts"),
        (_observation(ledger=LedgerFacts((), False, True)), "support"),
        (_observation(sandbox=SandboxFacts(True, (("final/report.md", "h_report"),), ())), "citations"),
    ],
)
def test_each_expectation_surface_fails_with_case_identity(observation: ScenarioObservation, message: str) -> None:
    with pytest.raises(ScenarioAssertionError) as exc_info:
        assert_scenario(_family(), _case(), observation)
    detail = str(exc_info.value)
    assert "family=quick-factual case=quick-factual-scripted lane=deterministic" in detail
    assert message in detail


def test_every_declared_invariant_is_evaluated_not_assumed_true() -> None:
    observation = _observation(ledger=LedgerFacts(("h_accepted",), True, True))
    case = replace(_case(), hard_invariants=(InvariantName.NO_LEDGER_CONFLICT,))

    with pytest.raises(ScenarioAssertionError, match="no-ledger-conflict"):
        assert_scenario(_family(), case, observation)


def test_degradation_must_be_allowed_by_both_family_and_case() -> None:
    observation = _observation(degradation="insufficient-evidence")
    case = replace(
        _case(),
        expectations=replace(_case().expectations, permitted_degradation=("insufficient-evidence",)),
    )
    assert_scenario(_family(), case, observation)

    with pytest.raises(ScenarioAssertionError, match="degradation"):
        assert_scenario(_family(), _case(), observation)
