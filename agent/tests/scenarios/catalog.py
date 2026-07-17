"""Canonical first-wave Deep Research scenario families.

@impl EVH-001
@impl EVH-003
@impl EVH-004
@impl EVH-007
"""

from __future__ import annotations

from .model import AuthenticityLevel, Scenario, ScenarioOutcome


def _scenario(
    scenario_id: str,
    risk: str,
    *,
    requirements: tuple[str, ...] = ("EVH-001",),
    route: str = "pass",
    terminal: str | None = None,
    degradation: tuple[str, ...] = (),
) -> Scenario:
    return Scenario(
        scenario_id=scenario_id,
        risk_family=risk,
        requirement_ids=requirements,
        regression_ids=(),
        entrypoint="start",
        authenticity=AuthenticityLevel.SCRIPTED_REAL_WORKFLOW,
        preconditions={"checkpoint": "empty", "workspace": "mounted"},
        scripted_inputs=(f"{scenario_id}:model", f"{scenario_id}:tool"),
        live_requirements=("model", "web_search"),
        expected=ScenarioOutcome(route=route, terminal=terminal),
        hard_invariants=("authority", "containment", "typed outcome"),
        metrics=("citation_precision", "must_answer_coverage"),
        permitted_degradation=degradation,
    )


SCENARIOS = (
    _scenario("quick-factual", "normal-research"),
    _scenario("claim-verification", "contradictory-evidence"),
    _scenario("insufficient-evidence", "honest-degradation", degradation=("insufficient_evidence",)),
    _scenario("prompt-injection", "untrusted-source", requirements=("EVH-004",)),
    _scenario("malformed-output", "structured-output", route="next"),
    _scenario("tool-unavailable-timeout", "external-tool", route="repair"),
    _scenario("budget-exhaustion", "execution-budget", route="exhausted", terminal="blocked"),
    _scenario("partial-worker-success", "gate-fatigue", route="repair"),
    _scenario("checkpoint-control", "resume-cancel-idempotency", requirements=("EVH-003",)),
    _scenario("sandbox-filesystem-failure", "artifact-authority", route="exhausted", terminal="blocked"),
)


__all__ = ["SCENARIOS"]
