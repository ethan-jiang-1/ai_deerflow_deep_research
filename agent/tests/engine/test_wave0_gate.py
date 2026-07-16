"""Real Wave0 gate definition.

@impl WAN-004
"""

from __future__ import annotations

from deerflow_deep_research.domain.gate import PhaseVerdict
from deerflow_deep_research.engine.gate_fixtures import build_fixture_gate_defs, build_wave0_real_gate_def


def test_real_wave0_gate_is_completion_only() -> None:
    gate = build_wave0_real_gate_def()
    assert gate.phase == "wave0"
    assert len(gate.rules) == 1  # WorkUnitCompletionRule only; no FixtureSequenceRule
    assert gate.default_budget == 3
    assert gate.route_map[PhaseVerdict.PASS] == "pass"
    assert gate.route_map[PhaseVerdict.REPAIR] == "repair"
    assert gate.route_map[PhaseVerdict.BLOCKED] == "exhausted"


def test_real_wave0_gate_drops_the_fixture_sequence_rule() -> None:
    fixture = build_fixture_gate_defs()["wave0"]
    real = build_wave0_real_gate_def()
    assert len(real.rules) == 1
    assert len(fixture.rules) == 2
    # The real gate keeps only the shared work-unit completion rule.
    assert type(real.rules[0]) is type(fixture.rules[0])
