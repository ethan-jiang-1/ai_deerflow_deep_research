from langgraph.types import interrupt

from deerflow_deep_research.domain.lifecycle import (
    AcceptedHumanResponse,
    HumanInputMode,
    HumanInputRequest,
    InternalCancelDecision,
    LifecycleStatus,
    PendingResearchInterrupt,
    TerminalReason,
    make_hitl_request_id,
)
from deerflow_deep_research.domain.node_spec import NodeBuildDependencies
from deerflow_deep_research.domain.state import PhaseStatus
from deerflow_deep_research.engine.fake_control import completed_visits, node_update


def build_fake(_dependencies: NodeBuildDependencies):
    async def run(state):
        request_id = make_hitl_request_id(
            research_id=state["research_id"],
            phase="hitl1",
            generation=int(state.get("generation", 0)),
            ordinal=completed_visits(state, "hitl1") + 1,
        )
        cursor = (state.get("consumed_message_ids") or (state["start_message_id"],))[-1]
        descriptor = PendingResearchInterrupt(
            request=HumanInputRequest(
                request_id=request_id,
                mode=HumanInputMode.TEXT,
                title="Deep Research input — implementation_mode=full_fake",
                context="Development skeleton only; this request does not represent real research.",
            ),
            suspension_cursor=cursor,
            phase="hitl1",
            generation=int(state.get("generation", 0)),
        )
        raw = interrupt(descriptor.model_dump(mode="json"))
        if isinstance(raw, dict) and raw.get("kind") == "internal_cancel":
            InternalCancelDecision.model_validate(raw)
            return node_update(
                "hitl1",
                route="cancel",
                terminal_status=LifecycleStatus.CANCELLED.value,
                phase_status=PhaseStatus.TERMINAL.value,
                terminal_reason=TerminalReason.USER_CANCELLED.value,
            )
        response = AcceptedHumanResponse.model_validate(raw)
        if response.request_id != request_id:
            raise ValueError("response_mismatch")
        return node_update(
            "hitl1",
            route="accepted",
            consumed_request_ids=(*state.get("consumed_request_ids", ()), response.request_id),
            consumed_message_ids=(*state.get("consumed_message_ids", ()), response.message_id),
        )

    return run
