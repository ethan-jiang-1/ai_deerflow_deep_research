"""ExecutionBudget / ExecutionPolicy validation contract (NOA-002)."""

from __future__ import annotations

import pytest

from deerflow_deep_research.agents.policies import (
    ExecutionBudget,
    ExecutionPolicy,
    PolicyError,
)


def _budget(**overrides) -> ExecutionBudget:
    base = {
        "max_model_calls": 4,
        "max_total_tool_calls": 8,
        "max_tool_calls_per_response": 3,
        "max_parallel_tool_calls": 2,
        "total_token_budget": 20_000,
        "per_call_output_token_cap": 2_000,
        "per_tool_result_bytes": 65_536,
        "structured_result_bytes": 16_384,
        "wall_time_seconds": 30.0,
    }
    base.update(overrides)
    return ExecutionBudget(**base)


def _policy(**overrides) -> ExecutionPolicy:
    base = {
        "policy_name": "node-default",
        "allowed_tool_names": frozenset({"read_file", "write_file"}),
        "read_roots": ("/mnt/user-data/workspace/deep-research/r1",),
        "write_roots": ("/mnt/user-data/workspace/deep-research/r1/attempts/a1",),
        "attempt_root": "/mnt/user-data/workspace/deep-research/r1/attempts/a1",
        "budget": _budget(),
    }
    base.update(overrides)
    return ExecutionPolicy(**base)


def test_valid_budget_and_policy_construct() -> None:
    policy = _policy()
    assert policy.is_tool_allowed("read_file")
    assert not policy.is_tool_allowed("bash")


@pytest.mark.parametrize(
    "field",
    [
        "max_model_calls",
        "max_total_tool_calls",
        "max_tool_calls_per_response",
        "max_parallel_tool_calls",
        "total_token_budget",
        "per_call_output_token_cap",
        "per_tool_result_bytes",
        "structured_result_bytes",
    ],
)
def test_non_positive_budget_fields_are_rejected(field: str) -> None:
    with pytest.raises(PolicyError):
        _budget(**{field: 0})


def test_boolean_is_not_a_valid_budget_integer() -> None:
    with pytest.raises(PolicyError):
        _budget(max_model_calls=True)


def test_wall_time_must_be_positive() -> None:
    with pytest.raises(PolicyError):
        _budget(wall_time_seconds=0)


def test_per_response_cannot_exceed_total_tool_calls() -> None:
    with pytest.raises(PolicyError):
        _budget(max_tool_calls_per_response=9, max_total_tool_calls=8)


def test_parallel_cannot_exceed_per_response() -> None:
    with pytest.raises(PolicyError):
        _budget(max_parallel_tool_calls=4, max_tool_calls_per_response=3)


def test_output_cap_cannot_exceed_total_budget() -> None:
    with pytest.raises(PolicyError):
        _budget(per_call_output_token_cap=30_000, total_token_budget=20_000)


def test_write_roots_must_stay_within_attempt_root() -> None:
    with pytest.raises(PolicyError):
        _policy(write_roots=("/mnt/user-data/workspace/deep-research/r1/attempts/OTHER",))


def test_attempt_root_itself_is_a_valid_write_root() -> None:
    policy = _policy(write_roots=("/mnt/user-data/workspace/deep-research/r1/attempts/a1",))
    assert policy.attempt_root in policy.write_roots


def test_policy_requires_name_and_roots() -> None:
    with pytest.raises(PolicyError):
        _policy(policy_name="")
    with pytest.raises(PolicyError):
        _policy(read_roots=())
