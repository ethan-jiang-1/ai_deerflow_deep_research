"""Deny-by-default tool and path policy contract.

@impl NOA-003
"""

from __future__ import annotations

import pytest
from langchain_core.messages import AIMessage, ToolMessage

from deerflow_deep_research.agents.middleware import AgentPolicyError, ToolPolicyMiddleware
from deerflow_deep_research.agents.policies import (
    ExecutionBudget,
    ExecutionPolicy,
    ToolPolicySpec,
    path_within_roots,
)

WORKSPACE = "/mnt/user-data/workspace/deep-research/r1"
ATTEMPT = f"{WORKSPACE}/attempts/a1"


def _budget() -> ExecutionBudget:
    return ExecutionBudget(
        max_model_calls=3,
        max_total_tool_calls=6,
        max_tool_calls_per_response=2,
        max_parallel_tool_calls=2,
        total_token_budget=5_000,
        per_call_output_token_cap=500,
        per_tool_result_bytes=4_096,
        structured_result_bytes=2_048,
        wall_time_seconds=5.0,
    )


def _policy() -> ExecutionPolicy:
    return ExecutionPolicy(
        policy_name="node-default",
        allowed_tool_names=frozenset({"read_file", "write_file", "sync_tool", "unsafe_write"}),
        read_roots=(WORKSPACE,),
        write_roots=(ATTEMPT,),
        attempt_root=ATTEMPT,
        budget=_budget(),
        tool_specs=(
            ToolPolicySpec("read_file", "read", ("path",), native_cancellable=True),
            ToolPolicySpec(
                "write_file",
                "write",
                ("path",),
                native_cancellable=True,
                provider_containment_verified=True,
            ),
            ToolPolicySpec("sync_tool", "read", ("path",), native_cancellable=False),
            ToolPolicySpec(
                "unsafe_write",
                "write",
                ("path",),
                native_cancellable=True,
                provider_containment_verified=False,
            ),
        ),
    )


class FakeToolRequest:
    def __init__(self, name, args) -> None:
        self.tool_call = {"name": name, "args": args, "id": "call-1"}


class FakeModelRequest:
    def __init__(self, *, tools, tool_choice) -> None:
        self.tools = tools
        self.tool_choice = tool_choice

    def override(self, **overrides):
        return FakeModelRequest(
            tools=overrides.get("tools", self.tools),
            tool_choice=overrides.get("tool_choice", self.tool_choice),
        )


class Handler:
    def __init__(self) -> None:
        self.called = False

    async def __call__(self, _request):
        self.called = True
        return ToolMessage(content="ok", tool_call_id="call-1")


async def _authorize(name, args, policy=None):
    middleware = ToolPolicyMiddleware(policy or _policy())
    handler = Handler()
    await middleware.awrap_tool_call(FakeToolRequest(name, args), handler)
    return handler


# ── path_within_roots unit ──────────────────────────────────────────────────


def test_path_within_roots_containment_and_traversal() -> None:
    assert path_within_roots(f"{ATTEMPT}/notes.md", (ATTEMPT,))
    assert path_within_roots(ATTEMPT, (ATTEMPT,))
    assert not path_within_roots(f"{ATTEMPT}/../../evil.md", (ATTEMPT,))
    assert not path_within_roots("/etc/passwd", (ATTEMPT,))
    assert not path_within_roots("", (ATTEMPT,))


# ── allow paths ─────────────────────────────────────────────────────────────


async def test_allowed_read_within_read_root_dispatches() -> None:
    handler = await _authorize("read_file", {"path": f"{WORKSPACE}/sources.json"})
    assert handler.called is True


async def test_allowed_write_within_attempt_root_dispatches() -> None:
    handler = await _authorize("write_file", {"path": f"{ATTEMPT}/result.md"})
    assert handler.called is True


async def test_tool_window_removes_tools_from_the_final_model_round() -> None:
    middleware = ToolPolicyMiddleware(_policy(), tool_call_limit=1)
    middleware.tool_calls = 1
    seen = None

    async def handler(request):
        nonlocal seen
        seen = request
        return "done"

    await middleware.awrap_model_call(FakeModelRequest(tools=["read_file"], tool_choice="auto"), handler)
    assert seen.tools == []
    assert seen.tool_choice is None


async def test_tool_window_rejects_parallel_calls_exceeding_remaining_request_quota() -> None:
    middleware = ToolPolicyMiddleware(_policy(), tool_call_limit=2)
    middleware.tool_calls = 1

    async def handler(_request):
        return AIMessage(
            content="",
            tool_calls=[
                {"name": "read_file", "args": {"path": f"{WORKSPACE}/a"}, "id": "call-1"},
                {"name": "read_file", "args": {"path": f"{WORKSPACE}/b"}, "id": "call-2"},
            ],
        )

    with pytest.raises(AgentPolicyError, match="request tool-call limit exceeded"):
        await middleware.awrap_model_call(FakeModelRequest(tools=["read_file"], tool_choice="auto"), handler)

    assert middleware.tool_calls == 1


# ── deny paths ──────────────────────────────────────────────────────────────


@pytest.mark.parametrize("name", ["bash", "ask_clarification", "task", "mcp__server__do", "acp_agent"])
async def test_non_allowlisted_tools_are_denied(name: str) -> None:
    with pytest.raises(AgentPolicyError):
        await _authorize(name, {"path": f"{ATTEMPT}/x"})


async def test_sync_only_tool_is_ineligible() -> None:
    with pytest.raises(AgentPolicyError):
        await _authorize("sync_tool", {"path": f"{WORKSPACE}/x"})


async def test_write_tool_without_provider_containment_is_ineligible() -> None:
    with pytest.raises(AgentPolicyError):
        await _authorize("unsafe_write", {"path": f"{ATTEMPT}/x"})


async def test_write_outside_attempt_root_is_denied() -> None:
    with pytest.raises(AgentPolicyError):
        await _authorize("write_file", {"path": f"{WORKSPACE}/outside-attempt.md"})


async def test_read_outside_read_roots_is_denied() -> None:
    with pytest.raises(AgentPolicyError):
        await _authorize("read_file", {"path": "/mnt/user-data/workspace/deep-research/OTHER/x"})


async def test_traversal_escape_is_denied() -> None:
    with pytest.raises(AgentPolicyError):
        await _authorize("write_file", {"path": f"{ATTEMPT}/../../../etc/passwd"})


async def test_missing_declared_path_field_is_denied() -> None:
    with pytest.raises(AgentPolicyError):
        await _authorize("write_file", {"content": "no path here"})


async def test_unknown_argument_shape_is_denied() -> None:
    middleware = ToolPolicyMiddleware(_policy())
    request = FakeToolRequest("write_file", "not-a-dict")
    with pytest.raises(AgentPolicyError):
        await middleware.awrap_tool_call(request, Handler())


async def test_handler_not_called_when_denied() -> None:
    middleware = ToolPolicyMiddleware(_policy())
    handler = Handler()
    with pytest.raises(AgentPolicyError):
        await middleware.awrap_tool_call(FakeToolRequest("bash", {"cmd": "rm -rf /"}), handler)
    assert handler.called is False
