"""Real HITL1 structured-profile node.

@impl HIN-001
@impl HIN-002
@impl HIN-003
@impl HIN-004
@impl HIN-005
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from langgraph.types import interrupt

from deerflow_deep_research.domain.context import NodeExecutionResult
from deerflow_deep_research.domain.enums import NodeFinishReason
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
from deerflow_deep_research.domain.profile import (
    PartialResearchProfile,
    finalize_profile,
    merge_profile_progress,
    missing_dimensions,
    parse_profile_response,
    profile_state_fields,
)
from deerflow_deep_research.domain.state import PhaseStatus
from deerflow_deep_research.engine.fake_control import completed_visits, node_update
from deerflow_deep_research.graph.nodes.hitl1.prompts import (
    build_brief_context,
    build_brief_prompt,
    build_followup_context,
    parse_brief_output,
)

MAX_HITL1_ANSWER_ROUNDS = 3


def _profile_progress_payload(profile: PartialResearchProfile) -> dict[str, Any]:
    return profile.model_dump(mode="json", exclude_none=True)


def _cursor(state: Mapping[str, Any]) -> str:
    return (state.get("consumed_message_ids") or (state["start_message_id"],))[-1]


def _request_id(state: Mapping[str, Any]) -> tuple[str, int]:
    ordinal = completed_visits(state, "hitl1") + 1
    request_id = make_hitl_request_id(
        research_id=state["research_id"],
        phase="hitl1",
        generation=int(state.get("generation", 0)),
        ordinal=ordinal,
    )
    return request_id, ordinal


def _exhausted_update() -> dict[str, Any]:
    return node_update(
        "hitl1",
        route="exhausted",
        terminal_status=LifecycleStatus.BLOCKED.value,
        phase_status=PhaseStatus.TERMINAL.value,
        terminal_reason=TerminalReason.GATE_BLOCKED.value,
    )


def _cancel_update() -> dict[str, Any]:
    return node_update(
        "hitl1",
        route="cancel",
        terminal_status=LifecycleStatus.CANCELLED.value,
        phase_status=PhaseStatus.TERMINAL.value,
        terminal_reason=TerminalReason.USER_CANCELLED.value,
        pending_profile=None,
        profile_followup_round=0,
    )


def _descriptor(
    *,
    state: Mapping[str, Any],
    request_id: str,
    context: str,
) -> PendingResearchInterrupt:
    return PendingResearchInterrupt(
        request=HumanInputRequest(
            request_id=request_id,
            mode=HumanInputMode.TEXT,
            title="Deep Research profile",
            context=context,
        ),
        suspension_cursor=_cursor(state),
        phase="hitl1",
        generation=int(state.get("generation", 0)),
    )


def _parse_response_text(text: str) -> PartialResearchProfile:
    try:
        return parse_profile_response(text)
    except (TypeError, ValueError):
        return PartialResearchProfile()


async def _generate_brief(dependencies: NodeBuildDependencies, question: str):
    repair_error: str | None = None
    for _attempt in range(2):
        try:
            result = await dependencies.capabilities.run_agent(
                context=dependencies.agent_context,
                request=build_brief_prompt(question, repair_error=repair_error),
            )
        except Exception:
            return None
        if not isinstance(result, NodeExecutionResult) or result.finish_reason is not NodeFinishReason.SUCCESS:
            return None
        try:
            return parse_brief_output(result.summary)
        except (TypeError, ValueError) as exc:
            repair_error = type(exc).__name__
    return None


def _pending_progress(state: Mapping[str, Any]) -> PartialResearchProfile | None:
    pending = state.get("pending_profile")
    if pending is None:
        return None
    return PartialResearchProfile.model_validate(pending)


def build_real(dependencies: NodeBuildDependencies):
    async def run(state):
        request_store = dependencies.request_bundle
        if request_store is None:
            raise ValueError("request_bundle_capability_missing")

        pending = _pending_progress(state)
        request_id, ordinal = _request_id(state)
        if pending is None:
            brief = await _generate_brief(dependencies, str(state.get("request_text") or ""))
            if brief is None:
                return _exhausted_update()
            context = build_brief_context(brief)
            progress = PartialResearchProfile()
        else:
            progress = pending
            context = build_followup_context(progress, missing_dimensions(progress))

        descriptor = _descriptor(state=state, request_id=request_id, context=context)
        raw = interrupt(descriptor.model_dump(mode="json"))
        if isinstance(raw, dict) and raw.get("kind") == "internal_cancel":
            InternalCancelDecision.model_validate(raw)
            return _cancel_update()

        response = AcceptedHumanResponse.model_validate(raw)
        if response.request_id != request_id:
            raise ValueError("response_mismatch")

        incoming = _parse_response_text(response.value)
        merged = merge_profile_progress(progress, incoming)
        missing = missing_dimensions(merged)
        consumed = {
            "consumed_request_ids": (*state.get("consumed_request_ids", ()), response.request_id),
            "consumed_message_ids": (*state.get("consumed_message_ids", ()), response.message_id),
        }
        if missing and ordinal < MAX_HITL1_ANSWER_ROUNDS:
            return node_update(
                "hitl1",
                route="needs_followup",
                pending_profile=_profile_progress_payload(merged),
                profile_followup_round=ordinal,
                **consumed,
            )

        profile = finalize_profile(merged, degraded=bool(missing))
        profile_ref = await request_store.write_profile(profile)
        return node_update(
            "hitl1",
            route="accepted",
            **profile_state_fields(profile, profile_ref),
            **consumed,
        )

    return run


__all__ = ["build_real"]
