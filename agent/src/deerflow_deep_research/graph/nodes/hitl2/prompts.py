"""HITL2 deterministic brief builder.

@impl HIT-001
"""

from __future__ import annotations

from typing import Any


def build_hitl2_brief(state: dict[str, Any]) -> dict[str, Any]:
    """Build a structured decision brief from accepted findings and gaps.

    Reads accepted submission refs and synthesis gaps from checkpoint state.
    Returns a dict with confirmed count, pending gap count, and available
    actions — suitable for display in the HITL2 interrupt context string.
    """
    accepted = state.get("accepted_submission_refs") or ()
    gaps = state.get("synthesis_gaps") or ()
    return {
        "confirmed_count": len(accepted),
        "pending_gaps": len(gaps),
        "available_actions": ["proceed", "revise_view", "repair", "rerun", "stop"],
    }
