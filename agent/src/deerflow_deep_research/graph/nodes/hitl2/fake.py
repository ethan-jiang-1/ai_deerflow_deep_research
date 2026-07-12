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
from deerflow_deep_research.engine.fake_control import completed_visits, node_update


def _options() -> tuple[HumanInputOption, ...]:
    return tuple(
        HumanInputOption(id=value, label=value.value.replace("_", " ").title(), value=value) for value in Hitl2Decision
    )


def build_fake(_dependencies: NodeBuildDependencies):
    async def run(state):
        generation = int(state.get("generation", 0))
        request_id = make_hitl_request_id(
            research_id=state["research_id"],
            phase="hitl2",
            generation=generation,
            ordinal=completed_visits(state, "hitl2") + 1,
        )
        cursor = (state.get("consumed_message_ids") or (state["start_message_id"],))[-1]
        descriptor = PendingResearchInterrupt(
            request=HumanInputRequest(
                request_id=request_id,
                mode=HumanInputMode.CHOICE,
                title="Deep Research decision — implementation_mode=full_fake",
                context="Choose a fake control-flow route; no real research findings exist.",
                options=_options(),
            ),
            suspension_cursor=cursor,
            phase="hitl2",
            generation=generation,
        )
        raw = interrupt(descriptor.model_dump(mode="json"))
        if isinstance(raw, dict) and raw.get("kind") == "internal_cancel":
            InternalCancelDecision.model_validate(raw)
            return node_update(
                "hitl2",
                route="cancel",
                status=LifecycleStatus.CANCELLED.value,
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
        updates = {}
        if decision is Hitl2Decision.STOP:
            updates = {
                "status": LifecycleStatus.STOPPED.value,
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
