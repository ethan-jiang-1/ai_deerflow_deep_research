"""Fault scenarios crossing real bridge and filesystem publication seams.

@impl EVH-003
@impl EVH-008
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from deerflow_deep_research.agents.policies import ExecutionBudget, ExecutionPolicy
from deerflow_deep_research.domain.context import NodeAgentContext, NodeExecutionRequest
from deerflow_deep_research.domain.profile import ResearchProfile
from deerflow_deep_research.runtime.node_agent_bridge import RuntimeNodeAgentBridge
from deerflow_deep_research.runtime.request_bundle import RequestBundleStore
from tests.fixtures.fake_models import BlockingChatModel
from tests.fixtures.runtime import local_runtime_envelope, unique_run_identity
from tests.scenarios.catalog import SCENARIOS


def _scenario(scenario_id: str):
    return next(scenario for scenario in SCENARIOS if scenario.scenario_id == scenario_id)


def _profile() -> ResearchProfile:
    return ResearchProfile(
        depth="standard",
        audience="practitioner",
        format="detailed_report",
        cost_tolerance="moderate",
        time_budget="standard",
        must_answer=("Which evidence supports the conclusion?",),
    )


async def test_filesystem_fault_leaves_no_partial_authoritative_profile(tmp_path: Path) -> None:
    scenario = _scenario("sandbox-filesystem-failure")
    identity = unique_run_identity()
    envelope = local_runtime_envelope(tmp_path, identity=identity)

    async def ready(*_args: object, **_kwargs: object):
        from deerflow_deep_research.runtime.work_unit_storage import WorkUnitStorageCheck

        return WorkUnitStorageCheck("ready", "local_thread_mount")

    def fault(point: str) -> None:
        if point == "after_staging_fsync":
            raise RuntimeError(f"{scenario.scenario_id}:after_staging_fsync")

    store = await RequestBundleStore.create(
        envelope,
        research_id=identity.research_id,
        storage_verifier=ready,
        token_factory=lambda: "f" * 32,
        fault_hook=fault,
    )
    with pytest.raises(RuntimeError, match=scenario.scenario_id):
        await store.write_profile(_profile())

    request_dir = envelope.workspace_host_path / "deep-research" / identity.research_id / "request"
    assert not (request_dir / "profile.json").exists()
    assert not tuple(request_dir.glob(".profile.*.tmp"))


async def test_model_timeout_cancellation_propagates_through_real_runtime_bridge(tmp_path: Path) -> None:
    scenario = _scenario("tool-unavailable-timeout")
    identity = unique_run_identity()
    envelope = local_runtime_envelope(tmp_path, identity=identity)
    workspace = f"/mnt/user-data/workspace/deep-research/{identity.research_id}"
    attempt_root = f"{workspace}/attempts/a1"
    budget = ExecutionBudget(
        max_model_calls=1,
        max_total_tool_calls=1,
        max_tool_calls_per_response=1,
        max_parallel_tool_calls=1,
        total_token_budget=2_000,
        per_call_output_token_cap=500,
        per_tool_result_bytes=1_024,
        structured_result_bytes=1_024,
        wall_time_seconds=1,
    )
    policy = ExecutionPolicy(
        policy_name="eval-timeout",
        allowed_tool_names=frozenset(),
        read_roots=(workspace,),
        write_roots=(),
        attempt_root=attempt_root,
        budget=budget,
    )
    started = asyncio.Event()
    bridge = RuntimeNodeAgentBridge(
        envelope=envelope,
        policy=policy,
        system_prompt="Bounded evaluation agent.",
        model_resolver=lambda _envelope: BlockingChatModel(started=started),
        tools_resolver=lambda _envelope, _policy: [],
    )
    context = NodeAgentContext(
        research_scope_id=identity.research_id,
        node_name="wave2_synthesis",
        attempt_id="a1",
        workspace_root=workspace,
        attempt_root=attempt_root,
        policy_name=policy.policy_name,
    )
    request = NodeExecutionRequest(objective=scenario.scenario_id, expected_output="one bounded result")
    task = asyncio.create_task(bridge.run_agent(context=context, request=request))
    await asyncio.wait_for(started.wait(), timeout=1)
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task


async def test_wall_time_timeout_returns_typed_budget_exhausted_outcome(tmp_path: Path) -> None:
    identity = unique_run_identity()
    envelope = local_runtime_envelope(tmp_path, identity=identity)
    workspace = f"/mnt/user-data/workspace/deep-research/{identity.research_id}"
    attempt_root = f"{workspace}/attempts/a1"
    budget = ExecutionBudget(
        max_model_calls=1,
        max_total_tool_calls=1,
        max_tool_calls_per_response=1,
        max_parallel_tool_calls=1,
        total_token_budget=2_000,
        per_call_output_token_cap=500,
        per_tool_result_bytes=1_024,
        structured_result_bytes=1_024,
        wall_time_seconds=0.01,
    )
    policy = ExecutionPolicy(
        policy_name="eval-wall-timeout",
        allowed_tool_names=frozenset(),
        read_roots=(workspace,),
        write_roots=(),
        attempt_root=attempt_root,
        budget=budget,
    )
    bridge = RuntimeNodeAgentBridge(
        envelope=envelope,
        policy=policy,
        system_prompt="Bounded evaluation agent.",
        model_resolver=lambda _envelope: BlockingChatModel(started=asyncio.Event()),
        tools_resolver=lambda _envelope, _policy: [],
    )
    result = await bridge.run_agent(
        context=NodeAgentContext(
            research_scope_id=identity.research_id,
            node_name="wave2_synthesis",
            attempt_id="a1",
            workspace_root=workspace,
            attempt_root=attempt_root,
            policy_name=policy.policy_name,
        ),
        request=NodeExecutionRequest(objective="timeout", expected_output="one bounded result"),
    )

    from deerflow_deep_research.domain.enums import NodeFinishReason

    assert result.finish_reason is NodeFinishReason.BUDGET_EXHAUSTED
    assert result.error_code == "wall_time"
