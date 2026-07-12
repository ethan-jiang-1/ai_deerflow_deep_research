"""Node-agent bridge, full-takeover factory, and no-clarification contract.

@impl NOA-001
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from deerflow_deep_research.agents.policies import ExecutionBudget, ExecutionPolicy
from deerflow_deep_research.domain.context import NodeAgentContext, NodeExecutionRequest
from deerflow_deep_research.domain.enums import NodeFinishReason
from deerflow_deep_research.runtime import node_agent_bridge as bridge_module
from deerflow_deep_research.runtime.node_agent_bridge import RuntimeNodeAgentBridge
from deerflow_deep_research.runtime.runtime_adapter import TrustedRuntimeEnvelope
from tests.fixtures.fake_models import (
    BlockingChatModel,
    CapturingChatModel,
    ScriptedChatModel,
    ai_message,
)

WORKSPACE = "/mnt/user-data/workspace/deep-research/r1"
ATTEMPT = f"{WORKSPACE}/attempts/a1"
HOST_MARKER = "/srv/secret-host/users/alice"


class FakeSandbox:
    sandbox_id = "sb-1"


def _budget(**overrides) -> ExecutionBudget:
    base = {
        "max_model_calls": 3,
        "max_total_tool_calls": 6,
        "max_tool_calls_per_response": 2,
        "max_parallel_tool_calls": 2,
        "total_token_budget": 5_000,
        "per_call_output_token_cap": 500,
        "per_tool_result_bytes": 4_096,
        "structured_result_bytes": 2_048,
        "wall_time_seconds": 5.0,
    }
    base.update(overrides)
    return ExecutionBudget(**base)


def _policy(budget: ExecutionBudget | None = None) -> ExecutionPolicy:
    return ExecutionPolicy(
        policy_name="node-default",
        allowed_tool_names=frozenset(),
        read_roots=(WORKSPACE,),
        write_roots=(ATTEMPT,),
        attempt_root=ATTEMPT,
        budget=budget or _budget(),
    )


def _envelope(*, parent_sandbox: object = FakeSandbox()) -> TrustedRuntimeEnvelope:
    return TrustedRuntimeEnvelope(
        effective_user_id="alice",
        outer_thread_id="thread-1",
        outer_run_id="run-1",
        app_config=object(),
        workspace_host_path=Path(HOST_MARKER) / "workspace",
        uploads_host_path=Path(HOST_MARKER) / "uploads",
        outputs_host_path=Path(HOST_MARKER) / "outputs",
        workspace_virtual_root="/mnt/user-data/workspace",
        uploads_virtual_root="/mnt/user-data/uploads",
        outputs_virtual_root="/mnt/user-data/outputs",
        parent_sandbox=parent_sandbox,
        progress=None,
    )


def _context() -> NodeAgentContext:
    return NodeAgentContext(
        research_scope_id="r1",
        node_name="collect",
        attempt_id="a1",
        workspace_root=WORKSPACE,
        attempt_root=ATTEMPT,
        policy_name="node-default",
    )


def _request() -> NodeExecutionRequest:
    return NodeExecutionRequest(objective="summarize the sources", expected_output="a short summary")


def _bridge(model_factory, *, envelope=None, policy=None, tools_resolver=lambda e, p: []) -> RuntimeNodeAgentBridge:
    return RuntimeNodeAgentBridge(
        envelope=envelope or _envelope(),
        policy=policy or _policy(),
        system_prompt="You are a bounded phase agent.",
        model_resolver=lambda _e: model_factory(),
        tools_resolver=tools_resolver,
    )


async def test_run_agent_completes_within_budget() -> None:
    bridge = _bridge(lambda: ScriptedChatModel(responses=[ai_message("the summary")]))
    result = await bridge.run_agent(context=_context(), request=_request())
    assert result.finish_reason == NodeFinishReason.SUCCESS
    assert result.summary == "the summary"


async def test_missing_parent_isolation_fails_closed() -> None:
    bridge = _bridge(lambda: ScriptedChatModel(responses=[ai_message("x")]), envelope=_envelope(parent_sandbox=None))
    result = await bridge.run_agent(context=_context(), request=_request())
    assert result.finish_reason == NodeFinishReason.FAILED
    assert result.error_code == "parent_isolation_missing"


async def test_fresh_runnable_built_per_request() -> None:
    bridge = _bridge(lambda: ScriptedChatModel(responses=[ai_message("one"), ai_message("two")]))
    await bridge.run_agent(context=_context(), request=_request())
    await bridge.run_agent(context=_context(), request=_request())
    assert bridge.agents_built == 2  # separate runnable per request, nothing cached


async def test_missing_usage_metadata_is_terminal() -> None:
    bridge = _bridge(lambda: ScriptedChatModel(responses=[ai_message("x", input_tokens=None, output_tokens=None)]))
    result = await bridge.run_agent(context=_context(), request=_request())
    assert result.finish_reason == NodeFinishReason.USAGE_UNAVAILABLE


async def test_token_admission_upper_bound_refuses_oversized_request() -> None:
    tight = _budget(total_token_budget=60, per_call_output_token_cap=40)
    request = NodeExecutionRequest(objective="x" * 200, expected_output="y")
    bridge = _bridge(lambda: ScriptedChatModel(responses=[ai_message("never reached")]), policy=_policy(tight))
    result = await bridge.run_agent(context=_context(), request=request)
    assert result.finish_reason == NodeFinishReason.BUDGET_EXHAUSTED


async def test_per_call_output_cap_exceeded_is_budget_exhausted() -> None:
    bridge = _bridge(
        lambda: ScriptedChatModel(responses=[ai_message("big", input_tokens=10, output_tokens=9_000)]),
        policy=_policy(_budget(per_call_output_token_cap=500, total_token_budget=5_000)),
    )
    result = await bridge.run_agent(context=_context(), request=_request())
    assert result.finish_reason == NodeFinishReason.BUDGET_EXHAUSTED


async def test_result_leaks_no_raw_identity_host_or_appconfig() -> None:
    bridge = _bridge(lambda: ScriptedChatModel(responses=[ai_message("clean summary")]))
    result = await bridge.run_agent(context=_context(), request=_request())
    serialized = str(result.model_dump())
    assert HOST_MARKER not in serialized
    assert "app_config" not in serialized
    assert "sb-1" not in serialized  # sandbox id never enters the model-facing result


async def test_model_request_carries_no_raw_authority() -> None:
    model = CapturingChatModel(reply=ai_message("done"), seen=[])
    bridge = _bridge(lambda: model)
    await bridge.run_agent(context=_context(), request=_request())
    flattened = str(model.seen)
    assert HOST_MARKER not in flattened
    assert "app_config" not in flattened
    assert "alice" not in flattened  # raw user id never reaches model-visible context
    assert "sb-1" not in flattened


async def test_outer_cancellation_is_not_converted_to_success() -> None:
    started = asyncio.Event()
    bridge = _bridge(lambda: BlockingChatModel(started=started))
    task = asyncio.create_task(bridge.run_agent(context=_context(), request=_request()))
    await asyncio.wait_for(started.wait(), timeout=2)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


def test_factory_uses_full_takeover_with_no_checkpointer(monkeypatch: pytest.MonkeyPatch) -> None:
    from deerflow_deep_research.agents import factory as factory_module

    captured: dict = {}

    def fake_create(**kwargs):
        captured.update(kwargs)
        return "COMPILED"

    monkeypatch.setattr("deerflow.agents.factory.create_deerflow_agent", fake_create)
    sentinel_mw = object()
    agent = factory_module.build_phase_agent(
        model="MODEL",
        tools=["TOOL"],
        middleware=[sentinel_mw],
        system_prompt="p",
    )
    assert agent == "COMPILED"
    # Full takeover: exact middleware list, no features/extra_middleware, no checkpointer.
    assert captured["middleware"] == [sentinel_mw]
    assert captured["checkpointer"] is None
    assert "features" not in captured and "extra_middleware" not in captured
    # No tools are auto-injected in full takeover, so ask_clarification is absent.
    assert captured["tools"] == ["TOOL"]


async def test_fabricated_clarification_call_is_refused_without_interrupt() -> None:
    # The model fabricates an ask_clarification tool call. There is no
    # clarification middleware and the tool is not allow-listed, so the call is
    # refused by policy (POLICY_DENIED) and can never create a graph interrupt or
    # human-input artifact.
    responses = [
        ai_message("", tool_calls=[{"name": "ask_clarification", "args": {"question": "?"}, "id": "c1"}]),
        ai_message("this should never be reached"),
    ]
    bridge = _bridge(lambda: ScriptedChatModel(responses=responses))
    result = await bridge.run_agent(context=_context(), request=_request())
    assert result.finish_reason == NodeFinishReason.POLICY_DENIED
    assert "human_input" not in str(result.model_dump())


def test_bridge_module_does_not_import_app() -> None:
    source = Path(bridge_module.__file__).read_text(encoding="utf-8")
    assert "import app" not in source and "from app" not in source


async def test_middleware_chain_order_is_pinned(monkeypatch: pytest.MonkeyPatch) -> None:
    from types import SimpleNamespace

    from deerflow_deep_research.agents.middleware import BudgetMiddleware, ToolPolicyMiddleware

    captured: dict = {}

    class FakeAgent:
        async def ainvoke(self, _state, context=None):  # noqa: ARG002
            return {"messages": [SimpleNamespace(content="ok")]}

    def fake_build(*, model, tools, middleware, system_prompt, name="x"):  # noqa: ARG001
        captured["middleware"] = middleware
        return FakeAgent()

    monkeypatch.setattr(bridge_module, "build_phase_agent", fake_build)
    bridge = _bridge(lambda: ScriptedChatModel(responses=[ai_message("ok")]))
    await bridge.run_agent(context=_context(), request=_request())
    # Budget admission wraps outermost; tool/path policy wraps tool dispatch.
    assert [type(m) for m in captured["middleware"]] == [BudgetMiddleware, ToolPolicyMiddleware]
