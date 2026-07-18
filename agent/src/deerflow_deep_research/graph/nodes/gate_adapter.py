"""Thin adapter so the graph layer can invoke gate evaluation without importing
from ``engine`` directly (architecture rule: graph → nodes → engine).

@impl GAK-003
@impl GAK-005
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from deerflow_deep_research.domain.gate import GateDefinition
from deerflow_deep_research.domain.state import WriterRole, apply_research_update
from deerflow_deep_research.domain.synthesis import WAVE2_GATE_PREVIEW_KEY, Wave2GatePreview
from deerflow_deep_research.engine.gate_fixtures import (
    build_final_delivery_real_gate_def,
    build_fixture_gate_defs,
    build_wave0_real_gate_def,
    build_wave1_real_gate_def,
    build_wave2_real_gate_def,
)
from deerflow_deep_research.engine.gate_kernel import (
    evaluate_gate,
    gate_result_to_state_update,
)


def evaluate_gate_for_node(
    state: Mapping[str, Any],
    logical_name: str,
    gate_def: GateDefinition,
) -> dict[str, Any]:
    """Run gate evaluation for *logical_name* and return a state update dict."""
    gate_result = evaluate_gate(state, logical_name, gate_def)
    update = gate_result_to_state_update(gate_result, logical_name, state)
    preview = state.get(WAVE2_GATE_PREVIEW_KEY)
    if logical_name == "wave2_synthesis" and isinstance(preview, Wave2GatePreview):
        gap_update = apply_research_update(
            state,
            {"unresolved_gaps": preview.searchable_gap_ids},
            writer=WriterRole.GATE,
        )
        update = {**update, **gap_update}
    return update


def default_gate_defs() -> dict[str, GateDefinition]:
    """Return the fixture ``GateDefinition`` map for all gated phases."""
    return dict(build_fixture_gate_defs())


def real_wave0_gate_def() -> GateDefinition:
    """Return the real Wave0 ``GateDefinition`` (completion/drain only)."""
    return build_wave0_real_gate_def()


def real_wave1_gate_def() -> GateDefinition:
    """Return the real Wave1 ``GateDefinition`` (completion/drain only)."""
    return build_wave1_real_gate_def()


def real_wave2_gate_def() -> GateDefinition:
    """Return the real Wave2 ``GateDefinition`` (searchable-gap routing)."""
    return build_wave2_real_gate_def()


def real_final_delivery_gate_def() -> GateDefinition:
    """Return the real final delivery ``GateDefinition``."""
    return build_final_delivery_real_gate_def()


__all__ = [
    "default_gate_defs",
    "evaluate_gate_for_node",
    "real_final_delivery_gate_def",
    "real_wave0_gate_def",
    "real_wave1_gate_def",
    "real_wave2_gate_def",
]
