"""Validated, redacted result projection contract (NOA-005)."""

from __future__ import annotations

import pytest

from deerflow_deep_research.agents.policies import ExecutionBudget, ExecutionPolicy
from deerflow_deep_research.agents.structured_output import (
    project_failure,
    project_success,
    redact,
    validate_artifact_refs,
)
from deerflow_deep_research.domain.context import ArtifactRef
from deerflow_deep_research.domain.enums import NodeFinishReason

WORKSPACE = "/mnt/user-data/workspace/deep-research/r1"
ATTEMPT = f"{WORKSPACE}/attempts/a1"


def _policy(structured_result_bytes: int = 2_048) -> ExecutionPolicy:
    return ExecutionPolicy(
        policy_name="node-default",
        allowed_tool_names=frozenset(),
        read_roots=(WORKSPACE,),
        write_roots=(ATTEMPT,),
        attempt_root=ATTEMPT,
        budget=ExecutionBudget(
            max_model_calls=2,
            max_total_tool_calls=2,
            max_tool_calls_per_response=1,
            max_parallel_tool_calls=1,
            total_token_budget=1_000,
            per_call_output_token_cap=200,
            per_tool_result_bytes=1_000,
            structured_result_bytes=structured_result_bytes,
            wall_time_seconds=5.0,
        ),
    )


def test_success_result_is_bounded_to_structured_cap() -> None:
    result = project_success("A" * 5_000, (), policy=_policy(structured_result_bytes=100))
    assert result.finish_reason == NodeFinishReason.SUCCESS
    assert len(result.summary.encode("utf-8")) <= 100


def test_artifact_ref_within_roots_is_accepted() -> None:
    ref = ArtifactRef(artifact_id="a1", virtual_path=f"{ATTEMPT}/out.md")
    result = project_success("done", (ref,), policy=_policy())
    assert result.artifact_refs == (ref,)


def test_artifact_ref_escaping_roots_is_rejected() -> None:
    ref = ArtifactRef(artifact_id="a1", virtual_path="/mnt/user-data/workspace/deep-research/OTHER/x")
    with pytest.raises(ValueError, match="escapes"):
        project_success("done", (ref,), policy=_policy())


def test_validate_artifact_refs_direct() -> None:
    good = ArtifactRef(artifact_id="g", virtual_path=f"{WORKSPACE}/read.json")
    validate_artifact_refs((good,), allowed_roots=(WORKSPACE, ATTEMPT))
    bad = ArtifactRef(artifact_id="b", virtual_path="/etc/passwd")
    with pytest.raises(ValueError, match="escapes"):
        validate_artifact_refs((bad,), allowed_roots=(WORKSPACE, ATTEMPT))


def test_failure_result_carries_redacted_detail() -> None:
    detail = "auth failed token=sk-abcdef123456 at /Users/alice/secret and postgres://u:p@h/db"
    result = project_failure(NodeFinishReason.FAILED, error_code="boom", detail=detail)
    assert result.finish_reason == NodeFinishReason.FAILED
    assert result.error_code == "boom"
    assert "sk-abcdef123456" not in result.summary
    assert "/Users/alice/secret" not in result.summary
    assert "postgres://" not in result.summary


@pytest.mark.parametrize(
    "secret",
    [
        "sk-1234567890abcd",
        "api_key: supersecretvalue",
        "postgres://user:pass@host:5432/db",
        "/home/bob/.ssh/id_rsa",
    ],
)
def test_redact_strips_known_secret_shapes(secret: str) -> None:
    assert "[redacted]" in redact(f"prefix {secret} suffix")
