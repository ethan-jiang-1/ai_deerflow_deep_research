"""Real Wave2 synthesis behavior at the NodeSpec/capabilities seam.

@impl WSN-001, WSN-002, WSN-003
"""

from __future__ import annotations

import json
import time
from datetime import UTC, datetime
from pathlib import Path

import pytest

from deerflow_deep_research.domain.context import GraphContextView, NodeAgentContext, NodeExecutionResult
from deerflow_deep_research.domain.enums import NodeFinishReason
from deerflow_deep_research.domain.node_spec import NodeBuildDependencies
from deerflow_deep_research.domain.synthesis import SynthesisEvidence, SynthesisResult
from deerflow_deep_research.graph.nodes.wave2_synthesis import NODE_SPEC
from deerflow_deep_research.runtime.work_unit_store import WorkUnitStore
from tests.assets.provider_shapes import load_provider_shape_cases, thaw_provider_shape_payload

RESEARCH_ID = "r_" + "W" * 43
SUBMISSION_REF = "h_" + "S" * 43
SHAPE_CASES = {
    case.case_id: case
    for case in load_provider_shape_cases(Path(__file__).parents[1] / "fixtures/provider_shapes/wave2.json")
}


def _synthesis_json(*, backing_refs: tuple[str, ...] = (SUBMISSION_REF,)) -> str:
    return json.dumps(
        {
            "schema_version": 1,
            "findings": [
                {
                    "finding_id": "finding:grid-storage",
                    "statement": "Storage duration changes project economics.",
                    "priority": 1,
                    "affected_topics": ["storage"],
                    "backing_refs": list(backing_refs),
                    "confidence": "high",
                    "search_required": False,
                }
            ],
            "relations": [],
            "gaps": [],
            "summary": "One supported cross-topic finding.",
        }
    )


class _Capabilities:
    def __init__(self, result: object) -> None:
        self.result = result
        self.contexts: list[NodeAgentContext] = []
        self.requests: list[object] = []

    async def run_agent(self, *, context: NodeAgentContext, request: object) -> NodeExecutionResult:
        if not isinstance(context, NodeAgentContext):
            raise TypeError("node_agent_context_required")
        self.contexts.append(context)
        self.requests.append(request)
        if isinstance(self.result, BaseException):
            raise self.result
        return self.result  # type: ignore[return-value]


class _RepairCapabilities:
    def __init__(self) -> None:
        self.requests: list[object] = []

    async def run_agent(self, *, context: NodeAgentContext, request: object) -> NodeExecutionResult:
        self.requests.append(request)
        summary = "not-json" if len(self.requests) == 1 else _synthesis_json()
        return NodeExecutionResult(finish_reason=NodeFinishReason.SUCCESS, summary=summary)


class _EmptyRepairCapabilities:
    def __init__(self) -> None:
        self.requests: list[object] = []

    async def run_agent(self, *, context: NodeAgentContext, request: object) -> NodeExecutionResult:
        self.requests.append(request)
        summary = (
            json.dumps({"tool": "read_file", "path": "submission-ledger.jsonl"})
            if len(self.requests) == 1
            else json.dumps(
                {
                    "schema_version": 1,
                    "findings": [],
                    "relations": [],
                    "gaps": [],
                    "summary": "",
                }
            )
        )
        return NodeExecutionResult(finish_reason=NodeFinishReason.SUCCESS, summary=summary)


class _SynthesisStore:
    def __init__(self, delegate: WorkUnitStore) -> None:
        self.delegate = delegate

    async def read_synthesis_evidence(self, accepted_refs: tuple[str, ...]) -> tuple[SynthesisEvidence, ...]:
        assert accepted_refs == (SUBMISSION_REF,)
        return (
            SynthesisEvidence(
                submission_ref=SUBMISSION_REF,
                phase="wave1",
                result_contract="wave1.evidence-extraction",
                content=json.dumps(
                    {
                        "claims": [
                            {
                                "statement": "Storage duration changes project economics.",
                                "support_refs": ["source:storage"],
                            }
                        ]
                    },
                    sort_keys=True,
                ),
            ),
        )

    async def write_synthesis(self, result: SynthesisResult) -> None:
        await self.delegate.write_synthesis(result)


def _dependencies(tmp_path: Path, capabilities: _Capabilities) -> NodeBuildDependencies:
    store = WorkUnitStore(
        workspace_host_path=tmp_path,
        research_id=RESEARCH_ID,
        clock=lambda: datetime(2026, 7, 17, tzinfo=UTC),
        monotonic=time.monotonic,
        lock_sleep=time.sleep,
        token_factory=lambda: "5" * 32,
        fault_hook=None,
    )
    graph_context = GraphContextView(
        research_scope_id=RESEARCH_ID,
        workspace_root=str(tmp_path),
        uploads_root=str(tmp_path / "uploads"),
        outputs_root=str(tmp_path / "outputs"),
    )
    return NodeBuildDependencies(
        graph_context=graph_context,
        agent_context=NodeAgentContext(
            research_scope_id=RESEARCH_ID,
            node_name="wave2_synthesis",
            attempt_id="g0-wave2-synthesis-a1",
            workspace_root=str(tmp_path),
            attempt_root=str(tmp_path / "attempts" / "g0-wave2-synthesis-a1"),
            policy_name="skeleton-wave2-synthesis",
        ),
        capabilities=capabilities,
        synthesis_bundle=_SynthesisStore(store),
    )


def _state() -> dict[str, object]:
    return {
        "research_id": RESEARCH_ID,
        "topic_registry": ({"topic_id": "storage", "title": "Storage"},),
        "accepted_submission_refs": (SUBMISSION_REF,),
        "execution_trace": (),
    }


async def test_real_synthesis_uses_node_context_and_materializes_canonical_findings(tmp_path: Path) -> None:
    capabilities = _Capabilities(NodeExecutionResult(finish_reason=NodeFinishReason.SUCCESS, summary=_synthesis_json()))

    update = await NODE_SPEC.real_factory(_dependencies(tmp_path, capabilities))(_state())

    assert update["execution_trace"] == ("wave2_synthesis",)
    assert capabilities.contexts[0].node_name == "wave2_synthesis"
    assert SUBMISSION_REF in capabilities.requests[0].objective
    artifact = tmp_path / "deep-research" / RESEARCH_ID / "synthesis" / "findings.json"
    payload = json.loads(artifact.read_text(encoding="utf-8"))
    assert payload["findings"][0]["backing_refs"] == [SUBMISSION_REF]
    assert artifact.read_bytes().endswith(b"\n") is False


async def test_real_synthesis_repairs_malformed_output_once_without_tools(tmp_path: Path) -> None:
    capabilities = _RepairCapabilities()

    update = await NODE_SPEC.real_factory(_dependencies(tmp_path, capabilities))(_state())  # type: ignore[arg-type]

    assert update["execution_trace"] == ("wave2_synthesis",)
    assert len(capabilities.requests) == 2
    assert capabilities.requests[1].tools_enabled is False
    assert "Storage duration changes project economics" in capabilities.requests[0].objective
    assert "Storage duration changes project economics" in capabilities.requests[1].objective


async def test_real_synthesis_rejects_empty_repair_when_accepted_evidence_exists(tmp_path: Path) -> None:
    capabilities = _EmptyRepairCapabilities()

    with pytest.raises(ValueError, match="synthesis_findings_or_gaps_required"):
        await NODE_SPEC.real_factory(_dependencies(tmp_path, capabilities))(_state())  # type: ignore[arg-type]

    assert len(capabilities.requests) == 2
    assert not (tmp_path / "deep-research" / RESEARCH_ID / "synthesis" / "findings.json").exists()


@pytest.mark.parametrize(
    "case",
    [pytest.param(SHAPE_CASES["shape-wave2-evidence-alias-binding"], id="shape-wave2-evidence-alias-binding")],
)
async def test_real_synthesis_maps_source_aliases_to_accepted_record_refs(tmp_path: Path, case) -> None:
    capabilities = _Capabilities(
        NodeExecutionResult(
            finish_reason=NodeFinishReason.SUCCESS,
            summary=json.dumps(thaw_provider_shape_payload(case.payload)),
        )
    )

    await NODE_SPEC.real_factory(_dependencies(tmp_path, capabilities))(_state())

    artifact = tmp_path / "deep-research" / RESEARCH_ID / "synthesis" / "findings.json"
    result = json.loads(artifact.read_text(encoding="utf-8"))
    assert result["findings"][0]["backing_refs"] == thaw_provider_shape_payload(case.expected_payload)["backing_refs"]


@pytest.mark.parametrize(
    ("result", "error"),
    [
        (NodeExecutionResult(finish_reason=NodeFinishReason.FAILED, error_code="provider_failed"), "synthesis_failed"),
        (
            NodeExecutionResult(finish_reason=NodeFinishReason.SUCCESS, summary="not-json"),
            "synthesis_output_json_invalid",
        ),
    ],
)
async def test_real_synthesis_fails_explicitly_without_publishing_partial_artifact(
    tmp_path: Path,
    result: NodeExecutionResult,
    error: str,
) -> None:
    with pytest.raises(ValueError, match=error):
        await NODE_SPEC.real_factory(_dependencies(tmp_path, _Capabilities(result)))(_state())

    assert not (tmp_path / "deep-research" / RESEARCH_ID / "synthesis" / "findings.json").exists()


async def test_real_synthesis_malformed_output_fails_without_artifact(tmp_path: Path) -> None:
    result = NodeExecutionResult(finish_reason=NodeFinishReason.SUCCESS, summary="not-json")
    with pytest.raises(ValueError, match="synthesis_output_json_invalid"):
        await NODE_SPEC.real_factory(_dependencies(tmp_path, _Capabilities(result)))(_state())
    assert not (tmp_path / "deep-research" / RESEARCH_ID / "synthesis" / "findings.json").exists()
