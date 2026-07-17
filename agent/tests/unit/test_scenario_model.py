"""Typed reusable scenario model and runner contracts.

@impl EVH-001
@impl EVH-007
"""

from __future__ import annotations

import pytest

from tests.scenarios.model import (
    AuthenticityLevel,
    ExecutionLane,
    Scenario,
    ScenarioAssertionError,
    ScenarioOutcome,
    ScenarioRunner,
)


def _scenario(**overrides) -> Scenario:
    values = {
        "scenario_id": "quick-factual",
        "risk_family": "normal-research",
        "requirement_ids": ("EVH-001",),
        "regression_ids": (),
        "entrypoint": "start",
        "authenticity": AuthenticityLevel.SCRIPTED_REAL_WORKFLOW,
        "preconditions": {"checkpoint": "empty"},
        "scripted_inputs": ("model-response", "tool-result"),
        "live_requirements": ("model", "web_search"),
        "expected": ScenarioOutcome(route="pass", artifacts=("report.md",)),
        "hard_invariants": ("route", "artifact containment"),
        "metrics": ("citation_precision",),
        "permitted_degradation": (),
    }
    values.update(overrides)
    return Scenario(**values)


def test_scenario_requires_stable_identity_requirements_and_invariants() -> None:
    with pytest.raises(ValueError, match="scenario_id_invalid"):
        _scenario(scenario_id="Bad ID")
    with pytest.raises(ValueError, match="scenario_requirement_ids_invalid"):
        _scenario(requirement_ids=("bad",))
    with pytest.raises(ValueError, match="scenario_invariants_required"):
        _scenario(hard_invariants=())


async def test_runner_rejects_lower_authenticity_claim_with_diagnostics() -> None:
    async def executor(_scenario):
        return ScenarioOutcome(route="pass", artifacts=("report.md",))

    runner = ScenarioRunner(ExecutionLane.DETERMINISTIC, AuthenticityLevel.FAKE_GRAPH, executor)
    with pytest.raises(ScenarioAssertionError) as exc_info:
        await runner.run(_scenario())
    detail = str(exc_info.value)
    assert "scenario=quick-factual" in detail
    assert "lane=deterministic" in detail
    assert "authenticity=fake_graph" in detail


async def test_runner_reports_failed_invariant_and_accepts_expected_outcome() -> None:
    async def wrong(_scenario):
        return ScenarioOutcome(route="repair")

    runner = ScenarioRunner(ExecutionLane.DETERMINISTIC, AuthenticityLevel.SCRIPTED_REAL_WORKFLOW, wrong)
    with pytest.raises(ScenarioAssertionError, match="invariant failed"):
        await runner.run(_scenario())

    async def correct(_scenario):
        return ScenarioOutcome(route="pass", artifacts=("report.md",))

    outcome = await ScenarioRunner(ExecutionLane.DETERMINISTIC, AuthenticityLevel.SCRIPTED_REAL_WORKFLOW, correct).run(
        _scenario()
    )
    assert outcome.route == "pass"
