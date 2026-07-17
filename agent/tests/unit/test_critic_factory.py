"""Red tests for critic agent factory runners.

@impl EVC-001, EVC-002, EVC-003, EVC-005
"""

from __future__ import annotations

import json

import pytest

from deerflow_deep_research.agents.policies import ExecutionBudget, ExecutionPolicy
from deerflow_deep_research.domain.context import NodeAgentContext, NodeExecutionRequest, NodeExecutionResult
from deerflow_deep_research.domain.critics import (
    ClaimVerifierResult,
    SourceDiagnosticResult,
)
from deerflow_deep_research.domain.enums import NodeFinishReason
from deerflow_deep_research.graph.nodes.targeted_evidence.subgraph import (
    run_claim_verifier,
    run_source_diagnostic,
)

RESEARCH_ID = "r_" + "A" * 43
ATTEMPT = "g0_wave2_a01"
WS = "/tmp/ws"


def _context() -> NodeAgentContext:
    return NodeAgentContext(
        research_scope_id=RESEARCH_ID,
        node_name="targeted_evidence",
        attempt_id=ATTEMPT,
        workspace_root=WS,
        attempt_root=f"{WS}/attempts/{ATTEMPT}",
        policy_name="test-critic",
    )


def _policy() -> ExecutionPolicy:
    return ExecutionPolicy(
        policy_name="test-critic",
        allowed_tool_names=frozenset(),
        read_roots=(f"/mnt/user-data/workspace/deep-research/{RESEARCH_ID}",),
        write_roots=(),
        attempt_root=f"/mnt/user-data/workspace/deep-research/{RESEARCH_ID}/attempts/{ATTEMPT}",
        budget=ExecutionBudget(
            max_model_calls=1,
            max_total_tool_calls=1,
            max_tool_calls_per_response=1,
            max_parallel_tool_calls=1,
            total_token_budget=8192,
            per_call_output_token_cap=4096,
            per_tool_result_bytes=65536,
            structured_result_bytes=16384,
            wall_time_seconds=120,
        ),
    )


class FakeCapabilities:
    """Fake capabilities that return a canned NodeExecutionResult."""

    def __init__(self, response_json: str):
        self._response = response_json
        self.calls: list[NodeExecutionRequest] = []
        self._policy = _policy()

    async def run_agent(self, *, context: object, request: NodeExecutionRequest) -> NodeExecutionResult:
        self.calls.append(request)
        return NodeExecutionResult(
            finish_reason=NodeFinishReason.SUCCESS,
            summary=self._response,
        )


_SOURCE_DIAG_OUTPUT = json.dumps(
    {
        "schema_version": 1,
        "sources": [
            {
                "source_id": "source:1",
                "trust_tier": "high",
                "materiality": "primary",
                "marketing_risk": False,
                "cross_verification_need": False,
            }
        ],
        "source_ids": ["source:1"],
    }
)


class TestRunSourceDiagnostic:
    async def test_calls_run_agent_once(self) -> None:
        cap = FakeCapabilities(_SOURCE_DIAG_OUTPUT)
        result = await run_source_diagnostic(cap, _context(), ATTEMPT, RESEARCH_ID, ("source:1",), ("content",), WS)
        assert isinstance(result, SourceDiagnosticResult)
        assert len(cap.calls) == 1

    async def test_returns_typed_result(self) -> None:
        cap = FakeCapabilities(_SOURCE_DIAG_OUTPUT)
        result = await run_source_diagnostic(cap, _context(), ATTEMPT, RESEARCH_ID, ("source:1",), ("content",), WS)
        assert result.schema_version == 1
        assert result.sources[0].trust_tier.value == "high"

    async def test_raises_on_invalid_output(self) -> None:
        cap = FakeCapabilities("not json")
        with pytest.raises(ValueError):
            await run_source_diagnostic(cap, _context(), ATTEMPT, RESEARCH_ID, ("source:1",), ("content",), WS)


_CLAIM_OUTPUT = json.dumps(
    {
        "schema_version": 1,
        "claims": [
            {
                "claim_id": "claim:1",
                "verdict": "supported",
                "support_refs": ["source:1"],
                "counter_refs": [],
                "reason": "Evidence supports the claim.",
            }
        ],
    }
)


class TestRunClaimVerifier:
    async def test_calls_run_agent_once(self) -> None:
        cap = FakeCapabilities(_CLAIM_OUTPUT)
        claims = (("claim:1", "The sky is blue."),)
        result = await run_claim_verifier(cap, _context(), ATTEMPT, RESEARCH_ID, claims, ("source:1",), WS)
        assert isinstance(result, ClaimVerifierResult)
        assert len(cap.calls) == 1

    async def test_returns_typed_result(self) -> None:
        cap = FakeCapabilities(_CLAIM_OUTPUT)
        claims = (("claim:1", "test"),)
        result = await run_claim_verifier(cap, _context(), ATTEMPT, RESEARCH_ID, claims, ("source:1",), WS)
        assert result.claims[0].verdict.value == "supported"

    async def test_raises_on_invalid_output(self) -> None:
        cap = FakeCapabilities("bad json")
        claims = (("claim:1", "test"),)
        with pytest.raises(ValueError):
            await run_claim_verifier(cap, _context(), ATTEMPT, RESEARCH_ID, claims, ("source:1",), WS)
