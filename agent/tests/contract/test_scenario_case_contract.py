"""Lane-neutral scenario family and lane-specific case contracts.

@impl EVH-001
@impl EVH-007
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from tests.assets.evidence import AssetClass, AuthenticityLevel, StableSeam
from tests.scenarios.contracts import (
    ScenarioBounds,
    ScenarioCase,
    ScenarioContractError,
    ScenarioExpectations,
    ScenarioFamily,
    ScenarioLane,
    validate_scenario_registry,
)
from tests.scenarios.inputs import LiveRequirements, ScenarioInputs


def _family(**overrides: object) -> ScenarioFamily:
    values: dict[str, object] = {
        "family_id": "quick-factual",
        "risk_intent": "Produce a bounded answer with structurally supported evidence.",
        "requirement_ids": ("EVH-001", "EVH-008"),
        "regression_ids": (),
        "permitted_degradation": ("insufficient-evidence",),
    }
    values.update(overrides)
    return ScenarioFamily(**values)


def _case(**overrides: object) -> ScenarioCase:
    values: dict[str, object] = {
        "case_id": "quick-factual-scripted",
        "family_id": "quick-factual",
        "lane": ScenarioLane.DETERMINISTIC,
        "entrypoint": "wave0-worker",
        "asset_class": AssetClass.DETERMINISTIC_WORKFLOW_CONFORMANCE,
        "seam": StableSeam.RUNTIME_INTEGRATION,
        "authenticity": AuthenticityLevel.SCRIPTED_REAL_WORKFLOW,
        "preconditions": ("empty-checkpoint", "contained-workspace"),
        "inputs": ScenarioInputs(),
        "bounds": ScenarioBounds(max_attempts=1, max_model_calls=3, max_tool_calls=2, max_wall_seconds=10),
        "expectations": ScenarioExpectations(
            route="pass",
            artifacts=("accepted-ledger-record",),
            support=("accepted-source-ref",),
            permitted_degradation=("insufficient-evidence",),
        ),
        "hard_invariants": ("accepted-authority", "paths-contained"),
        "applicable_metrics": ("citation-binding-rate",),
    }
    values.update(overrides)
    return ScenarioCase(**values)


def test_valid_family_and_case_registry_passes() -> None:
    family = _family()
    case = _case()

    validate_scenario_registry((family,), (case,))

    assert case.asset_class is AssetClass.DETERMINISTIC_WORKFLOW_CONFORMANCE
    assert case.seam is StableSeam.RUNTIME_INTEGRATION


@pytest.mark.parametrize(
    ("factory", "overrides", "code"),
    [
        (_family, {"family_id": "Bad Family"}, "family_id_invalid"),
        (_family, {"risk_intent": ""}, "family_risk_intent_required"),
        (_family, {"requirement_ids": ()}, "family_requirement_ids_invalid"),
        (_case, {"case_id": "Bad Case"}, "case_id_invalid"),
        (_case, {"family_id": "Bad Family"}, "case_family_id_invalid"),
        (_case, {"entrypoint": ""}, "case_entrypoint_invalid"),
        (_case, {"preconditions": ()}, "case_preconditions_required"),
        (_case, {"hard_invariants": ()}, "case_hard_invariants_required"),
        (_case, {"applicable_metrics": ()}, "case_metrics_required"),
        (_case, {"lane": "deterministic"}, "case_lane_invalid"),
        (_case, {"asset_class": "workflow"}, "case_asset_class_invalid"),
        (_case, {"seam": "runtime-store"}, "case_seam_invalid"),
        (_case, {"authenticity": "scripted-real-workflow"}, "case_authenticity_invalid"),
    ],
)
def test_contracts_reject_incomplete_or_alias_vocabulary(factory, overrides, code: str) -> None:
    with pytest.raises(ValueError, match=code):
        factory(**overrides)


@pytest.mark.parametrize(
    "overrides",
    [
        {"max_attempts": 0},
        {"max_attempts": 9},
        {"max_model_calls": -1},
        {"max_model_calls": 65},
        {"max_tool_calls": -1},
        {"max_tool_calls": 129},
        {"max_wall_seconds": 0},
        {"max_wall_seconds": 901},
    ],
)
def test_case_bounds_are_finite(overrides: dict[str, int]) -> None:
    values = {"max_attempts": 1, "max_model_calls": 3, "max_tool_calls": 2, "max_wall_seconds": 10}
    values.update(overrides)
    with pytest.raises(ValueError, match="scenario_bounds_invalid"):
        ScenarioBounds(**values)


def test_descriptive_only_family_is_rejected() -> None:
    with pytest.raises(ScenarioContractError, match="quick-factual.*no executable cases"):
        validate_scenario_registry((_family(),), ())


def test_case_degradation_must_be_permitted_by_family() -> None:
    case = replace(
        _case(),
        expectations=replace(_case().expectations, permitted_degradation=("unsupported-claim",)),
    )

    with pytest.raises(ScenarioContractError, match="quick-factual-scripted.*unsupported-claim"):
        validate_scenario_registry((_family(),), (case,))


def test_duplicate_and_unknown_family_bindings_fail() -> None:
    with pytest.raises(ScenarioContractError, match="duplicate family"):
        validate_scenario_registry((_family(), _family()), (_case(),))
    with pytest.raises(ScenarioContractError, match="unknown family"):
        validate_scenario_registry((_family(),), (replace(_case(), family_id="claim-verification"),))


def test_case_lane_requires_the_matching_input_kind() -> None:
    with pytest.raises(ValueError, match="case_deterministic_inputs_required"):
        _case(inputs=LiveRequirements(("model",)))
    with pytest.raises(ValueError, match="case_live_requirements_required"):
        _case(lane=ScenarioLane.LIVE, inputs=ScenarioInputs())

    live = _case(lane=ScenarioLane.LIVE, inputs=LiveRequirements(("model", "web_search")))
    assert live.inputs.dependency_names == ("model", "web_search")
