"""Runtime-owned bridge from graph nodes to bounded phase agents.

@impl NOA-001

This is the only raw-binding owner. Nodes call it exclusively through the pure
``NodeExecutionCapabilities`` protocol; they never import ``agents`` or
``runtime`` and never see the ``TrustedRuntimeEnvelope``. Each ``run_agent``
request resolves the model and eligible tools from trusted config, seeds an
ephemeral child state/context (parent sandbox + thread data + raw identity),
builds a *fresh* bounded agent as a separate runnable with ``checkpointer=None``,
invokes it under a wall-time budget, and discards it. Nothing is cached across
requests, users, threads, or attempts, and no second sandbox/thread lifecycle is
created. Raw identity/AppConfig/host paths live only in the ephemeral child
binding required by tools -- never in the node contract, model-facing result, or
graph checkpoint.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

from langchain_core.messages import HumanMessage

from deerflow_deep_research.agents.factory import build_phase_agent
from deerflow_deep_research.agents.middleware import (
    BudgetMiddleware,
    PhaseAgentStop,
    ToolPolicyMiddleware,
)
from deerflow_deep_research.agents.policies import ExecutionPolicy
from deerflow_deep_research.agents.prompts import build_untrusted_data_block, load_policy_prompt
from deerflow_deep_research.agents.structured_output import project_failure, project_success
from deerflow_deep_research.domain.context import (
    NodeAgentContext,
    NodeExecutionRequest,
    NodeExecutionResult,
)
from deerflow_deep_research.domain.enums import NodeFinishReason
from deerflow_deep_research.runtime.events import build_progress_event
from deerflow_deep_research.runtime.runtime_adapter import TrustedRuntimeEnvelope

ModelResolver = Callable[[TrustedRuntimeEnvelope], Any]
ToolsResolver = Callable[[TrustedRuntimeEnvelope, ExecutionPolicy], Sequence[Any]]


class NodeAgentConfigurationError(RuntimeError):
    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"[{code}] {detail}")
        self.code = code


def _default_model_resolver(envelope: TrustedRuntimeEnvelope) -> Any:
    if not getattr(envelope.app_config, "models", None):
        raise NodeAgentConfigurationError("model_not_configured", "node-agent execution requires a configured model")
    from deerflow.models.factory import create_chat_model

    return create_chat_model(app_config=envelope.app_config, attach_tracing=False)


def _default_tools_resolver(envelope: TrustedRuntimeEnvelope, policy: ExecutionPolicy) -> Sequence[Any]:
    from deerflow.tools.tools import get_available_tools

    # When the envelope carries a minimal demo config with no tools, fall
    # back to the global config.yaml so operators can configure web search
    # tools without threading them through the demo shim.
    app_config = envelope.app_config
    if not getattr(app_config, "tools", None):
        from deerflow.config import get_app_config

        app_config = get_app_config()
    loaded = get_available_tools(include_mcp=False, app_config=app_config)
    eligible = [tool for tool in loaded if tool.name in policy.allowed_tool_names]
    if policy.allowed_tool_names and not eligible:
        names = ",".join(sorted(policy.allowed_tool_names))
        raise NodeAgentConfigurationError("tools_unavailable", f"no configured tools satisfy policy: {names}")
    return eligible


@dataclass
class RuntimeNodeAgentBridge:
    """Implements the domain ``NodeExecutionCapabilities`` protocol."""

    envelope: TrustedRuntimeEnvelope
    policy: ExecutionPolicy
    system_prompt: str | None = None
    model_resolver: ModelResolver = _default_model_resolver
    tools_resolver: ToolsResolver = _default_tools_resolver
    agents_built: int = field(default=0)

    async def run_agent(
        self,
        *,
        context: NodeAgentContext,
        request: NodeExecutionRequest,
    ) -> NodeExecutionResult:
        if self.envelope.parent_sandbox is None:
            return project_failure(NodeFinishReason.FAILED, error_code="parent_isolation_missing")

        self._emit(context, operation="run_agent", status="started")
        model = self.model_resolver(self.envelope)
        tools = list(self.tools_resolver(self.envelope, self.policy)) if request.tools_enabled else []
        budget_middleware = BudgetMiddleware(self.policy.budget)
        tool_policy_middleware = ToolPolicyMiddleware(self.policy, tool_call_limit=request.tool_call_limit)
        agent = build_phase_agent(
            model=model,
            tools=tools,
            middleware=[budget_middleware, tool_policy_middleware],
            system_prompt=self.system_prompt or load_policy_prompt(),
        )
        self.agents_built += 1

        child_state = self._ephemeral_child_state(context, request)
        child_context = self._ephemeral_child_context()
        try:
            result = await asyncio.wait_for(
                agent.ainvoke(child_state, context=child_context),
                timeout=self.policy.budget.wall_time_seconds,
            )
        except TimeoutError:
            self._emit(context, operation="run_agent", status="budget_exhausted")
            return project_failure(NodeFinishReason.BUDGET_EXHAUSTED, error_code="wall_time")
        except PhaseAgentStop as exc:
            self._emit(context, operation="run_agent", status=str(exc.finish_reason))
            return project_failure(exc.finish_reason, error_code="policy", detail=exc.detail)
        except asyncio.CancelledError:
            # Never convert cancellation into success; the child runnable and its
            # tasks are torn down as the exception propagates.
            raise
        if tool_policy_middleware.tool_calls < request.minimum_tool_calls:
            self._emit(context, operation="run_agent", status="required_tool_not_called")
            return project_failure(NodeFinishReason.FAILED, error_code="required_tool_not_called")
        node_result = self._project_result(result, untrusted_tool_results=tuple(tool_policy_middleware.tool_results))
        self._emit(context, operation="run_agent", status="completed")
        return node_result

    def _emit(self, context: NodeAgentContext, *, operation: str, status: str) -> None:
        emitter = self.envelope.progress
        if emitter is None:
            return
        emitter.emit(
            build_progress_event(
                kind="node_agent",
                ref=context.research_scope_id,
                operation=f"{context.node_name}.{operation}",
                status=status,
            )
        )

    def _ephemeral_child_state(self, context: NodeAgentContext, request: NodeExecutionRequest) -> dict[str, Any]:
        prompt = (
            f"Objective: {request.objective}\n"
            f"Expected output: {request.expected_output}\n"
            f"Attempt workspace (virtual): {context.attempt_root}\n"
        )
        if request.source_artifact_refs:
            listed = [f"- {ref.artifact_id}: {ref.virtual_path}" for ref in request.source_artifact_refs]
            prompt += f"\n{build_untrusted_data_block(listed)}\n"
        sandbox = self.envelope.parent_sandbox
        sandbox_id = getattr(sandbox, "id", None) or getattr(sandbox, "sandbox_id", None)
        return {
            "messages": [HumanMessage(prompt)],
            "sandbox": {"sandbox_id": sandbox_id},
            "thread_data": {"thread_id": self.envelope.outer_thread_id},
        }

    def _ephemeral_child_context(self) -> dict[str, Any]:
        return {
            "user_id": self.envelope.effective_user_id,
            "thread_id": self.envelope.outer_thread_id,
            "run_id": self.envelope.outer_run_id,
            "app_config": self.envelope.app_config,
        }

    def _project_result(
        self,
        result: Any,
        *,
        untrusted_tool_results: tuple[str, ...] = (),
    ) -> NodeExecutionResult:
        messages = result.get("messages") if isinstance(result, dict) else None
        summary = ""
        if messages:
            content = getattr(messages[-1], "content", "")
            summary = content if isinstance(content, str) else ""
        return project_success(
            summary,
            (),
            policy=self.policy,
            untrusted_tool_results=untrusted_tool_results,
        )


__all__ = ["NodeAgentConfigurationError", "RuntimeNodeAgentBridge"]
