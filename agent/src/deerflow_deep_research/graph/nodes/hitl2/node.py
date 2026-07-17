"""Real HITL2 human decision node — brief builder + interrupt/resume pipeline.

@impl HIT-001
@impl HIT-002
"""

from __future__ import annotations

from typing import Any

from langgraph.types import interrupt

from deerflow_deep_research.domain.lifecycle import (
    AcceptedHumanResponse,
    Hitl2Decision,
    HumanInputMode,
    HumanInputOption,
    HumanInputRequest,
    InternalCancelDecision,
    LifecycleStatus,
    PendingResearchInterrupt,
    ResponseKind,
    TerminalReason,
    make_hitl_request_id,
)
from deerflow_deep_research.domain.node_spec import NodeBuildDependencies
from deerflow_deep_research.domain.state import PhaseStatus
from deerflow_deep_research.engine.fake_control import completed_visits, node_update

from .prompts import build_hitl2_brief


def _options() -> tuple[HumanInputOption, ...]:
    return tuple(
        HumanInputOption(id=value, label=value.value.replace("_", " ").title(), value=value) for value in Hitl2Decision
    )


def build_real(dependencies: NodeBuildDependencies):
    """Build the real HITL2 node with brief builder + interrupt/resume pipeline.

    The interrupt/resume pipeline is identical to the fake — only the briefing
    text is built from actual accepted findings instead of fixture text.
    """

    async def run(state: dict[str, Any]) -> dict[str, Any]:
        generation = int(state.get("generation", 0))
        request_id = make_hitl_request_id(
            research_id=state["research_id"],
            phase="hitl2",
            generation=generation,
            ordinal=completed_visits(state, "hitl2") + 1,
        )
        cursor = (state.get("consumed_message_ids") or (state["start_message_id"],))[-1]
        brief = build_hitl2_brief(state)
        context = (
            f"Accepted findings: {brief['confirmed_count']}. "
            f"Pending gaps: {brief['pending_gaps']}. "
            f"Available actions: {', '.join(brief['available_actions'])}."
        )
        descriptor = PendingResearchInterrupt(
            request=HumanInputRequest(
                request_id=request_id,
                mode=HumanInputMode.CHOICE,
                title="Deep Research — decision",
                context=context,
                options=_options(),
            ),
            suspension_cursor=cursor,
            phase="hitl2",
            generation=generation,
        )
        # Non-interactive auto-proceed: skip interrupt
        non_interactive = state.get("non_interactive_policy")
        if isinstance(non_interactive, dict) and non_interactive.get("auto_proceed") is True:
            return node_update(
                "hitl2",
                route="proceed",
                consumed_request_ids=(*state.get("consumed_request_ids", ()), request_id),
                consumed_message_ids=(*state.get("consumed_message_ids", ()), "auto-proceed"),
            )

        raw = interrupt(descriptor.model_dump(mode="json"))
        if isinstance(raw, dict) and raw.get("kind") == "internal_cancel":
            InternalCancelDecision.model_validate(raw)
            return node_update(
                "hitl2",
                route="cancel",
                terminal_status=LifecycleStatus.CANCELLED.value,
                phase_status=PhaseStatus.TERMINAL.value,
                terminal_reason=TerminalReason.USER_CANCELLED.value,
            )
        response = AcceptedHumanResponse.model_validate(raw)
        if response.request_id != request_id:
            raise ValueError("response_mismatch")
        if response.response_kind is ResponseKind.OPTION:
            if response.option_id != response.value:
                raise ValueError("response_invalid")
            value = response.value
        else:
            value = response.value.strip().lower()
        try:
            decision = Hitl2Decision(value)
        except ValueError as exc:
            raise ValueError("response_invalid") from exc
        updates: dict[str, Any] = {}
        if decision is Hitl2Decision.STOP:
            updates = {
                "terminal_status": LifecycleStatus.STOPPED.value,
                "phase_status": PhaseStatus.TERMINAL.value,
                "terminal_reason": TerminalReason.USER_STOPPED.value,
            }
        return node_update(
            "hitl2",
            route=decision.value,
            consumed_request_ids=(*state.get("consumed_request_ids", ()), response.request_id),
            consumed_message_ids=(*state.get("consumed_message_ids", ()), response.message_id),
            **updates,
        )

    return run
