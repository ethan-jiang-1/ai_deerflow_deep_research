"""Synthetic joins across scenario cases, claims, and observations.

@impl EVH-001
@impl EVH-007
@impl EVH-009
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from tests.assets.evidence import (
    AssetClass,
    AuthenticityLevel,
    FocusedSelection,
    StableSeam,
    TestEvidenceClaim,
)
from tests.scenarios.contracts import (
    ScenarioBounds,
    ScenarioCase,
    ScenarioExpectations,
    ScenarioFamily,
    ScenarioLane,
)
from tests.scenarios.governance import (
    ScenarioGovernanceError,
    validate_real_scenario_catalog,
    validate_scenario_evidence,
)
from tests.scenarios.inputs import LiveRequirements, ModelTurn, ScenarioInputs
from tests.scenarios.observation import CheckpointFacts, LedgerFacts, SandboxFacts, ScenarioObservation

CASE_ID = "quick-factual-scripted"
SELECTOR = f"tests/integration/test_scenarios.py::test_scenario[{CASE_ID}]"


def _family() -> ScenarioFamily:
    return ScenarioFamily(
        family_id="quick-factual",
        risk_intent="Produce one bounded supported answer.",
        requirement_ids=("EVH-001",),
        regression_ids=(),
        permitted_degradation=(),
    )


def _case(**overrides: object) -> ScenarioCase:
    values: dict[str, object] = {
        "case_id": CASE_ID,
        "family_id": "quick-factual",
        "lane": ScenarioLane.DETERMINISTIC,
        "entrypoint": "wave0-worker",
        "asset_class": AssetClass.DETERMINISTIC_WORKFLOW_CONFORMANCE,
        "seam": StableSeam.RUNTIME_INTEGRATION,
        "authenticity": AuthenticityLevel.SCRIPTED_REAL_WORKFLOW,
        "preconditions": ("contained-workspace",),
        "inputs": ScenarioInputs(model_turns=(ModelTurn(content="bounded response"),)),
        "bounds": ScenarioBounds(1, 2, 1, 10),
        "expectations": ScenarioExpectations(route="pass"),
        "hard_invariants": ("paths-contained",),
        "applicable_metrics": ("citation-binding-rate",),
    }
    values.update(overrides)
    return ScenarioCase(**values)


def _claim(**overrides: object) -> TestEvidenceClaim:
    values: dict[str, object] = {
        "claim_id": "claim-quick-factual-scripted",
        "selector": SELECTOR,
        "expected_selection": FocusedSelection.WORKFLOW,
        "requirement_ids": ("EVH-001", "EVH-008"),
        "asset_class": AssetClass.DETERMINISTIC_WORKFLOW_CONFORMANCE,
        "seam": StableSeam.RUNTIME_INTEGRATION,
        "authenticity": AuthenticityLevel.SCRIPTED_REAL_WORKFLOW,
        "scenario_case_id": CASE_ID,
    }
    values.update(overrides)
    return TestEvidenceClaim(**values)


def _observation() -> ScenarioObservation:
    return ScenarioObservation(
        checkpoint=CheckpointFacts("pass", None, True, 1),
        ledger=LedgerFacts(("h_accepted",), False, True),
        sandbox=SandboxFacts(True, (), ()),
    )


def test_valid_synthetic_scenario_evidence_join_passes() -> None:
    validate_scenario_evidence(
        (_family(),),
        (_case(),),
        (_claim(),),
        observations={CASE_ID: _observation()},
        collected_selectors={SELECTOR},
    )


def test_case_id_must_be_the_pytest_parameter_id() -> None:
    claim = _claim(selector="tests/integration/test_scenarios.py::test_scenario[wrong-case]")
    with pytest.raises(ScenarioGovernanceError, match="stable pytest parameter id"):
        validate_scenario_evidence(
            (_family(),),
            (_case(),),
            (claim,),
            observations={CASE_ID: _observation()},
            collected_selectors={claim.selector},
        )


@pytest.mark.parametrize(
    ("claim", "message"),
    [
        (
            _claim(
                asset_class=AssetClass.CODE_CORRECTNESS,
                expected_selection=FocusedSelection.INTEGRATION,
                authenticity=None,
            ),
            "asset class",
        ),
        (_claim(seam=StableSeam.NODE_INTERFACE), "seam"),
        (_claim(authenticity=AuthenticityLevel.REAL_NODE_FAKE_CAPABILITIES), "authenticity"),
    ],
)
def test_claim_cannot_substitute_asset_seam_or_authenticity(
    claim: TestEvidenceClaim,
    message: str,
) -> None:
    with pytest.raises(ScenarioGovernanceError, match=message):
        validate_scenario_evidence(
            (_family(),),
            (_case(),),
            (claim,),
            observations={CASE_ID: _observation()},
            collected_selectors={claim.selector},
        )


def test_unbound_case_and_missing_authority_observation_fail() -> None:
    with pytest.raises(ScenarioGovernanceError, match="no evidence claim"):
        validate_scenario_evidence(
            (_family(),),
            (_case(),),
            (),
            observations={CASE_ID: _observation()},
            collected_selectors=set(),
        )
    with pytest.raises(ScenarioGovernanceError, match="missing authority observation"):
        validate_scenario_evidence(
            (_family(),),
            (_case(),),
            (_claim(),),
            observations={},
            collected_selectors={SELECTOR},
        )


def test_case_cannot_resolve_to_multiple_claims() -> None:
    second = _claim(
        claim_id="claim-quick-factual-second",
        selector=f"tests/integration/test_scenarios.py::test_other[{CASE_ID}]",
    )
    with pytest.raises(ScenarioGovernanceError, match="resolves to 2 evidence claims"):
        validate_scenario_evidence(
            (_family(),),
            (_case(),),
            (_claim(), second),
            observations={CASE_ID: _observation()},
            collected_selectors={SELECTOR, second.selector},
        )


def test_deterministic_case_cannot_require_credentials_or_network() -> None:
    with pytest.raises(ValueError, match="case_deterministic_inputs_required"):
        replace(_case(), inputs=LiveRequirements(("model_credentials", "external_network")))

    with pytest.raises(ValueError, match="sensitive_input_forbidden"):
        replace(
            _case(),
            inputs=ScenarioInputs(model_turns=(ModelTurn(content="API_KEY=secret-value"),)),
        )


def test_real_catalog_requires_exact_family_case_claim_closure() -> None:
    validate_real_scenario_catalog(
        (_family(),),
        (_case(),),
        (_claim(),),
        deterministic_selectors={SELECTOR},
        workflow_selectors={SELECTOR},
        required_family_ids={"quick-factual"},
    )

    with pytest.raises(ScenarioGovernanceError, match="no deterministic case"):
        validate_real_scenario_catalog(
            (_family(),),
            (),
            (),
            deterministic_selectors=set(),
            workflow_selectors=set(),
            required_family_ids={"quick-factual"},
        )

    with pytest.raises(ScenarioGovernanceError, match="family catalog mismatch"):
        validate_real_scenario_catalog(
            (_family(),),
            (_case(),),
            (_claim(),),
            deterministic_selectors={SELECTOR},
            workflow_selectors={SELECTOR},
            required_family_ids={"quick-factual", "missing-family"},
        )


def test_only_qualifying_real_catalog_cases_enter_workflow_selection() -> None:
    correctness = replace(
        _case(),
        asset_class=AssetClass.CODE_CORRECTNESS,
        authenticity=None,
    )
    claim = replace(
        _claim(),
        expected_selection=FocusedSelection.FAST,
        asset_class=AssetClass.CODE_CORRECTNESS,
        authenticity=None,
    )
    validate_real_scenario_catalog(
        (_family(),),
        (correctness,),
        (claim,),
        deterministic_selectors={SELECTOR},
        workflow_selectors=set(),
    )

    with pytest.raises(ScenarioGovernanceError, match="non-workflow case collected by workflow"):
        validate_real_scenario_catalog(
            (_family(),),
            (correctness,),
            (claim,),
            deterministic_selectors={SELECTOR},
            workflow_selectors={SELECTOR},
        )
