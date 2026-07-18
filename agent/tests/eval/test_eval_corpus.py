"""Replay-based eval corpus — deterministic scenarios with FakeToolCallingModel.

@impl EVH-001
@impl EVH-002
"""

from __future__ import annotations

from tests.scenarios.replays import FIRST_WAVE_CASES, FIRST_WAVE_FAMILIES


def test_first_wave_scenario_registry_is_complete_and_unique() -> None:
    expected = {
        "quick-factual",
        "claim-verification",
        "insufficient-evidence",
        "prompt-injection",
        "malformed-output",
        "tool-unavailable-timeout",
        "budget-exhaustion",
        "partial-worker-success",
        "checkpoint-control",
        "sandbox-filesystem-failure",
    }
    assert {family.family_id for family in FIRST_WAVE_FAMILIES} == expected
    assert {case.case_id for case in FIRST_WAVE_CASES} == expected
