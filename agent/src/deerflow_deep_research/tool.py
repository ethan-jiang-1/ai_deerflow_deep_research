"""Strict reflected Deep Research control tool.

@impl RUI-001
@impl RUI-006
@impl REG-004
"""

from __future__ import annotations

import json
import secrets
from typing import Any

from langchain.tools import ToolRuntime
from langchain_core.messages import AIMessage
from langchain_core.tools import tool
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from deerflow_deep_research.runtime.checkpoint import CheckpointNamespaceError
from deerflow_deep_research.runtime.control import get_default_graph_host
from deerflow_deep_research.runtime.graph_host import GraphHostError
from deerflow_deep_research.runtime.human_input import HumanInputError, select_start_message
from deerflow_deep_research.runtime.identity import TrustedIdentityError
from deerflow_deep_research.runtime.projection import ProjectionError
from deerflow_deep_research.runtime.research import (
    Durability,
    InfrastructureResultCode,
    LifecycleAction,
    ResearchActionInput,
    ResultCode,
    denial_result,
    derive_research_id,
)
from deerflow_deep_research.runtime.runtime_adapter import RuntimeAdapter, RuntimeAdapterError
from deerflow_deep_research.runtime.work_unit_storage import WorkUnitStoreError

ADVERTISED_ACTION = "infra_probe"
ADVERTISED_ACTIONS = ("infra_probe", "start", "resume", "status", "cancel")
_PROBE_ID_PATTERN = r"^[A-Za-z0-9_-]{1,64}$"
_RESEARCH_ID_PATTERN = r"^r_[A-Za-z0-9_-]{43}$"


class DeepResearchArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: str = Field(min_length=1, max_length=32)
    probe_id: str | None = Field(default=None, pattern=_PROBE_ID_PATTERN)
    research_id: str | None = Field(default=None, pattern=_RESEARCH_ID_PATTERN)

    @model_validator(mode="after")
    def validate_action_fields(self) -> DeepResearchArgs:
        if self.action == "infra_probe":
            if self.research_id is not None:
                raise ValueError("infra_probe cannot include research_id")
        elif self.action == "start":
            if self.probe_id is not None or self.research_id is not None:
                raise ValueError("start accepts no caller-selected id")
        elif self.action in {"resume", "status", "cancel"}:
            if self.research_id is None or self.probe_id is not None:
                raise ValueError("lifecycle action requires only research_id")
        elif self.probe_id is not None or self.research_id is not None:
            raise ValueError("unknown action accepts no id fields")
        return self


def generate_probe_id() -> str:
    return secrets.token_urlsafe(16)


def normalize_validation_error(exc: ValidationError) -> dict[str, Any]:
    fields = sorted({".".join(str(part) for part in error["loc"]) for error in exc.errors()})
    codes = sorted({error["type"] for error in exc.errors()})
    return {"code": "invalid_arguments", "fields": fields, "violations": codes}


def _exclusive_lifecycle_call(runtime: Any) -> bool:
    state = getattr(runtime, "state", None)
    messages = state.get("messages", ()) if isinstance(state, dict) else ()
    latest = next((message for message in reversed(messages) if isinstance(message, AIMessage)), None)
    if latest is None or len(latest.tool_calls) != 1:
        return False
    call = latest.tool_calls[0]
    return call.get("name") == "deep_research" and call.get("id") == getattr(runtime, "tool_call_id", None)


def _runtime_messages(runtime: Any) -> tuple[Any, ...]:
    state = getattr(runtime, "state", None)
    return tuple(state.get("messages", ())) if isinstance(state, dict) else ()


async def run_deep_research(
    *,
    action: str,
    probe_id: str | None,
    runtime: Any,
    research_id: str | None = None,
    adapter: RuntimeAdapter | None = None,
    host_factory: Any = None,
) -> Any:
    """Dispatch in the fixed schema -> registry -> correlation -> adapter order."""
    host = host_factory() if host_factory is not None else get_default_graph_host()
    if not host.is_registered(action):
        return {
            "code": "action_unavailable",
            "supported": [candidate for candidate in ADVERTISED_ACTIONS if host.is_registered(candidate)],
        }

    lifecycle_action = LifecycleAction(action) if action in {item.value for item in LifecycleAction} else None
    if lifecycle_action is not None and not _exclusive_lifecycle_call(runtime):
        return denial_result(action=lifecycle_action, code=ResultCode.EXCLUSIVE_CONTROL_CALL_REQUIRED)

    adapter = adapter or RuntimeAdapter()
    try:
        initialize_parent_sandbox = lifecycle_action not in {LifecycleAction.STATUS, LifecycleAction.CANCEL}
        envelope = await adapter.adapt(
            runtime,
            initialize_parent_sandbox=initialize_parent_sandbox,
        )
    except (TrustedIdentityError, RuntimeAdapterError) as exc:
        if lifecycle_action is None:
            return {"code": exc.code}
        try:
            code = InfrastructureResultCode(exc.code)
        except ValueError:
            code = InfrastructureResultCode.RUNTIME_CONTEXT_REQUIRED
        return denial_result(action=lifecycle_action, code=code)

    if lifecycle_action is None:
        return await host.run_action(
            action=action,
            envelope=envelope,
            action_input=probe_id or generate_probe_id(),
        )

    resolved_research_id = research_id or derive_research_id(
        effective_user_id=envelope.effective_user_id,
        outer_thread_id=envelope.outer_thread_id,
    )
    context = getattr(runtime, "context", None)
    context = context if isinstance(context, dict) else {}
    if action in {"start", "resume"} and (
        context.get("non_interactive") is True or context.get("disable_clarification") is True
    ):
        return denial_result(
            action=lifecycle_action,
            code=ResultCode.INTERACTIVE_REQUIRED,
            research_id=resolved_research_id,
        )
    if action in {"start", "resume"} and (context.get("channel_user_id") or context.get("channel_name")):
        return denial_result(
            action=lifecycle_action,
            code=ResultCode.HUMAN_INPUT_TRANSPORT_UNAVAILABLE,
            research_id=resolved_research_id,
        )

    messages = _runtime_messages(runtime)
    start_message = None
    if lifecycle_action is LifecycleAction.START:
        try:
            start_message = select_start_message(messages)
        except HumanInputError:
            return denial_result(
                action=lifecycle_action,
                code=ResultCode.START_MESSAGE_INVALID,
                research_id=resolved_research_id,
            )
    action_input = ResearchActionInput(
        action=lifecycle_action,
        research_id=resolved_research_id,
        tool_call_id=str(getattr(runtime, "tool_call_id", "")),
        messages=messages,
        start_message=start_message,
    )
    try:
        return await host.run_action(action=action, envelope=envelope, action_input=action_input)
    except WorkUnitStoreError as exc:
        return denial_result(
            action=lifecycle_action,
            code=exc.code,
            research_id=resolved_research_id,
            durability=Durability.UNAVAILABLE,
            infrastructure_reason=exc.reason,
        )
    except (GraphHostError, CheckpointNamespaceError, ProjectionError, HumanInputError) as exc:
        try:
            code: ResultCode | InfrastructureResultCode = ResultCode(exc.code)
        except ValueError:
            try:
                code = InfrastructureResultCode(exc.code)
            except ValueError:
                code = ResultCode.CHECKPOINT_INCONSISTENT
        return denial_result(
            action=lifecycle_action,
            code=code,
            research_id=None if code is ResultCode.RESEARCH_NOT_FOUND else resolved_research_id,
            durability=Durability.UNAVAILABLE,
        )
    except Exception:
        return denial_result(
            action=lifecycle_action,
            code=ResultCode.CHECKPOINT_INCONSISTENT,
            research_id=resolved_research_id,
            durability=Durability.UNAVAILABLE,
        )


@tool("deep_research", args_schema=DeepResearchArgs)
async def deep_research_tool(
    action: str,
    probe_id: str | None = None,
    research_id: str | None = None,
    runtime: ToolRuntime = None,
) -> Any:
    """Route the infra probe or a full-fake research lifecycle action.

    Args:
        action: One of ``infra_probe|start|resume|status|cancel``.
        probe_id: Optional opaque id accepted only by ``infra_probe``.
        research_id: Opaque id required only by resume, status, and cancel.
        runtime: Trusted runtime injected by LangGraph ToolNode.
    """
    try:
        args = DeepResearchArgs(action=action, probe_id=probe_id, research_id=research_id)
    except ValidationError as exc:
        return json.dumps(normalize_validation_error(exc), sort_keys=True)
    result = await run_deep_research(
        action=args.action,
        probe_id=args.probe_id,
        research_id=args.research_id,
        runtime=runtime,
    )
    if not isinstance(result, dict):
        return result
    return json.dumps(result, sort_keys=True)


__all__ = ["DeepResearchArgs", "deep_research_tool", "generate_probe_id", "run_deep_research"]
