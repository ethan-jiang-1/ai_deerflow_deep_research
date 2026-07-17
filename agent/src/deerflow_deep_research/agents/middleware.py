"""Bounded phase-agent middleware: admission-controlled budgets.

@impl NOA-002

Budget enforcement is admission control, not only after-the-fact accounting.
Before every text-only model call the middleware computes a deterministic,
no-network UTF-8 byte upper bound over the actual request (a token count never
exceeds its UTF-8 byte length) plus the policy's per-call output cap, and refuses
the call if it could exceed the remaining token budget. Non-text content without
an explicit conservative estimator fails admission. Actual ``usage_metadata``
reconciles the estimate; a response without usable accounting is terminal
``usage_unavailable`` and cannot issue tools or another model call.

A fresh middleware instance is bound to exactly one ``run_agent`` request (the
bridge builds a new agent per request), so mutable counters here are per-run.
The assembled-chain order assertion is finalized in group 11; this module owns
only the budget/cancellation behaviour.
"""

from __future__ import annotations

from typing import Any

from langchain.agents.middleware import AgentMiddleware

from deerflow_deep_research.agents.policies import ExecutionBudget, ExecutionPolicy, path_within_roots
from deerflow_deep_research.domain.enums import NodeFinishReason


class PhaseAgentStop(RuntimeError):
    """Base for typed, non-success stops raised by the bounded agent chain."""

    def __init__(self, finish_reason: NodeFinishReason, detail: str) -> None:
        super().__init__(f"[{finish_reason}] {detail}")
        self.finish_reason = finish_reason
        self.detail = detail


class AgentBudgetError(PhaseAgentStop):
    """Raised to stop the agent with a typed budget/usage finish reason."""


class AgentPolicyError(PhaseAgentStop):
    """Raised to deny a tool/path before dispatch with POLICY_DENIED."""

    def __init__(self, detail: str) -> None:
        super().__init__(NodeFinishReason.POLICY_DENIED, detail)


def _content_upper_bound(content: Any) -> int:
    """Conservative UTF-8 byte upper bound for text content; None for non-text."""
    if isinstance(content, str):
        return len(content.encode("utf-8"))
    return -1  # non-text: no deterministic estimator in this policy


class BudgetMiddleware(AgentMiddleware):
    def __init__(self, budget: ExecutionBudget) -> None:
        super().__init__()
        self._budget = budget
        self.model_calls = 0
        self.tokens_used = 0
        self.tool_calls = 0

    def _request_upper_bound(self, request: Any) -> int:
        total = 0
        system = getattr(request, "system_message", None)
        if system is not None:
            bound = _content_upper_bound(getattr(system, "content", ""))
            if bound < 0:
                raise AgentBudgetError(NodeFinishReason.BUDGET_EXHAUSTED, "non-text content lacks a modality estimator")
            total += bound
        for message in getattr(request, "messages", []) or []:
            bound = _content_upper_bound(getattr(message, "content", ""))
            if bound < 0:
                raise AgentBudgetError(NodeFinishReason.BUDGET_EXHAUSTED, "non-text content lacks a modality estimator")
            total += bound
        for tool in getattr(request, "tools", []) or []:
            total += len(str(tool).encode("utf-8"))
        return total

    async def awrap_model_call(self, request: Any, handler: Any) -> Any:
        budget = self._budget
        if self.model_calls >= budget.max_model_calls:
            raise AgentBudgetError(NodeFinishReason.BUDGET_EXHAUSTED, "maximum model calls reached")

        projected = self._request_upper_bound(request) + budget.per_call_output_token_cap
        if self.tokens_used + projected > budget.total_token_budget:
            raise AgentBudgetError(NodeFinishReason.BUDGET_EXHAUSTED, "token admission upper bound exceeds budget")

        response = await handler(request)

        message = self._response_message(response)
        usage = getattr(message, "usage_metadata", None) if message is not None else None
        if not usage or usage.get("total_tokens") is None or usage.get("output_tokens") is None:
            raise AgentBudgetError(NodeFinishReason.USAGE_UNAVAILABLE, "model response has no usable token accounting")

        if usage["output_tokens"] > budget.per_call_output_token_cap:
            raise AgentBudgetError(NodeFinishReason.BUDGET_EXHAUSTED, "per-call output token cap exceeded")

        self.tokens_used += int(usage["total_tokens"])
        if self.tokens_used > budget.total_token_budget:
            raise AgentBudgetError(NodeFinishReason.BUDGET_EXHAUSTED, "total token budget exhausted")
        self.model_calls += 1

        tool_calls = getattr(message, "tool_calls", None) or []
        if len(tool_calls) > budget.max_tool_calls_per_response:
            raise AgentBudgetError(NodeFinishReason.BUDGET_EXHAUSTED, "too many tool calls in one response")
        if len(tool_calls) > budget.max_parallel_tool_calls:
            raise AgentBudgetError(NodeFinishReason.BUDGET_EXHAUSTED, "parallel tool-call limit exceeded")
        return response

    async def awrap_tool_call(self, request: Any, handler: Any) -> Any:
        budget = self._budget
        if self.tool_calls >= budget.max_total_tool_calls:
            raise AgentBudgetError(NodeFinishReason.BUDGET_EXHAUSTED, "maximum total tool calls reached")
        self.tool_calls += 1
        result = await handler(request)
        return self._bound_tool_result(result, budget.per_tool_result_bytes)

    @staticmethod
    def _response_message(response: Any) -> Any:
        result = getattr(response, "result", None)
        if result:
            return result[-1]
        return response if getattr(response, "usage_metadata", None) is not None else None

    @staticmethod
    def _bound_tool_result(result: Any, limit: int) -> Any:
        content = getattr(result, "content", None)
        if isinstance(content, str) and len(content.encode("utf-8")) > limit:
            truncated = content.encode("utf-8")[:limit].decode("utf-8", "ignore")
            try:
                result.content = f"{truncated}\n[truncated to {limit} bytes]"
            except (AttributeError, ValueError):
                return result
        return result


class ToolPolicyMiddleware(AgentMiddleware):
    """Deny-by-default tool and path authorization, revalidated before dispatch.

    The model only ever receives curated tools, but a compromised or confused
    model could still emit a call for a name it should not use, so every call is
    re-authorized here: the runtime tool name must be allow-listed and backed by
    an eligible ``ToolPolicySpec``, and each declared path argument must normalize
    within the policy's read/write roots. Writes stay within the attempt root;
    an unknown argument shape, a non-cancellable tool, a write tool whose provider
    cannot prove containment, or a path escape is denied before execution.
    """

    def __init__(self, policy: ExecutionPolicy, *, tool_call_limit: int | None = None) -> None:
        super().__init__()
        self._policy = policy
        if tool_call_limit is not None and not 1 <= tool_call_limit <= policy.budget.max_total_tool_calls:
            raise ValueError("tool_call_limit_invalid")
        self._tool_call_limit = tool_call_limit
        self.tool_calls = 0
        self.tool_results: list[str] = []

    async def awrap_model_call(self, request: Any, handler: Any) -> Any:
        if self._tool_call_limit is not None and self.tool_calls >= self._tool_call_limit:
            request = request.override(tools=[], tool_choice=None)
        return await handler(request)

    async def awrap_tool_call(self, request: Any, handler: Any) -> Any:
        name, args = self._extract(request)
        self._authorize(name, args)
        result = await handler(request)
        self.tool_calls += 1
        content = getattr(result, "content", None)
        if isinstance(content, str) and len(self.tool_results) < 8:
            limit = self._policy.budget.per_tool_result_bytes
            self.tool_results.append(content.encode("utf-8")[:limit].decode("utf-8", "ignore"))
        return result

    def _authorize(self, name: str, args: dict[str, Any]) -> None:
        policy = self._policy
        if not policy.is_tool_allowed(name):
            raise AgentPolicyError(f"tool is not allow-listed: {name}")
        spec = policy.spec_for(name)
        if spec is None:
            raise AgentPolicyError(f"tool has no typed policy spec: {name}")
        if not spec.is_eligible:
            raise AgentPolicyError(f"tool is ineligible (cancellation/containment): {name}")
        for field_name in spec.path_fields:
            if field_name not in args:
                raise AgentPolicyError(f"tool call is missing declared path field: {field_name}")
            value = args[field_name]
            roots = policy.write_roots if spec.effect == "write" else policy.read_roots
            if not path_within_roots(value, roots):
                raise AgentPolicyError(f"path field {field_name} escapes the policy roots")

    @staticmethod
    def _extract(request: Any) -> tuple[str, dict[str, Any]]:
        tool_call = getattr(request, "tool_call", None)
        if not isinstance(tool_call, dict):
            raise AgentPolicyError("tool call has an unknown request shape")
        name = tool_call.get("name")
        args = tool_call.get("args")
        if not isinstance(name, str) or not isinstance(args, dict):
            raise AgentPolicyError("tool call has an unknown argument shape")
        return name, args


__all__ = ["AgentBudgetError", "AgentPolicyError", "BudgetMiddleware", "PhaseAgentStop", "ToolPolicyMiddleware"]
