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
from deerflow_deep_research.domain.synthesis import (
    WAVE2_GATE_PREVIEW_KEY,
    GapRecord,
    SynthesisEvidence,
    SynthesisResult,
    Wave2GatePreview,
)
from deerflow_deep_research.graph.nodes.wave2_synthesis import NODE_SPEC
from deerflow_deep_research.graph.nodes.wave2_synthesis.prompts import (
    build_synthesis_prompt,
    build_synthesis_repair_prompt,
)
from deerflow_deep_research.runtime.work_unit_store import WorkUnitStore
from tests.assets.provider_shapes import load_provider_shape_cases, thaw_provider_shape_payload

RESEARCH_ID = "r_" + "W" * 43
SUBMISSION_REF = "h_" + "S" * 43
SHAPE_CASES = {
    case.case_id: case
    for case in load_provider_shape_cases(Path(__file__).parents[1] / "fixtures/provider_shapes/wave2.json")
}


def _synthesis_json(
    *,
    backing_refs: tuple[str, ...] = (SUBMISSION_REF,),
    gaps: tuple[dict[str, object], ...] = (),
) -> str:
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
            "gaps": gaps,
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


class _GapsOnlyRepairCapabilities:
    def __init__(self, *, valid_repair: bool) -> None:
        self.valid_repair = valid_repair
        self.requests: list[object] = []

    async def run_agent(self, *, context: NodeAgentContext, request: object) -> NodeExecutionResult:
        self.requests.append(request)
        gap = {
            "gap_id": "gap:storage-cost",
            "description": "Storage cost needs targeted evidence.",
            "priority": 1,
            "affected_topics": ["storage"],
            "search_required": True,
        }
        if len(self.requests) == 2 and self.valid_repair:
            summary = _synthesis_json(gaps=(gap,))
        else:
            summary = json.dumps(
                {
                    "schema_version": 1,
                    "findings": [],
                    "relations": [],
                    "gaps": [gap],
                    "summary": "A searchable gap remains.",
                }
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
    assert update[WAVE2_GATE_PREVIEW_KEY] == Wave2GatePreview(searchable_gap_ids=())
    assert artifact.read_bytes().endswith(b"\n") is False


def test_gap_search_required_is_canonical_and_defaults_false() -> None:
    legacy = GapRecord(
        gap_id="gap:legacy",
        description="Legacy gap",
        priority=3,
        affected_topics=("storage",),
    )
    searchable = GapRecord(
        gap_id="gap:searchable",
        description="Needs targeted evidence",
        priority=1,
        affected_topics=("storage",),
        search_required=True,
    )

    assert legacy.search_required is False
    assert searchable.search_required is True
    assert searchable.model_dump(mode="json")["search_required"] is True


def test_wave2_prompts_distinguish_finding_and_gap_search_flags() -> None:
    request = build_synthesis_prompt()
    repair = build_synthesis_repair_prompt("draft")

    for prompt in (request, repair):
        combined = f"{prompt.objective}\n{prompt.expected_output}"
        assert "finding" in combined.lower()
        assert "gap" in combined.lower()
        assert "finding.search_required" not in combined
        assert "gap.search_required" not in combined
        expected = json.loads(prompt.expected_output)
        assert expected["finding_required_keys"] == [
            "finding_id",
            "statement",
            "priority",
            "affected_topics",
            "backing_refs",
            "confidence",
            "search_required",
        ]
        assert expected["confidence_values"] == ["high", "medium", "low", "tentative"]
        assert expected["relation_required_keys"] == [
            "relation_id",
            "source_finding",
            "target_finding",
            "relation_type",
        ]
        assert expected["relation_type_values"] == ["supports", "contradicts", "extends", "qualifies"]
        assert expected["gap_required_keys"] == [
            "gap_id",
            "description",
            "priority",
            "affected_topics",
            "search_required",
        ]


async def test_real_synthesis_persists_searchable_gap_and_returns_typed_preview(tmp_path: Path) -> None:
    gap = {
        "gap_id": "gap:storage-cost",
        "description": "Storage cost needs targeted evidence.",
        "priority": 1,
        "affected_topics": ["storage"],
        "search_required": True,
    }
    capabilities = _Capabilities(
        NodeExecutionResult(
            finish_reason=NodeFinishReason.SUCCESS,
            summary=_synthesis_json(gaps=(gap,)),
        )
    )

    update = await NODE_SPEC.real_factory(_dependencies(tmp_path, capabilities))(_state())

    assert update[WAVE2_GATE_PREVIEW_KEY] == Wave2GatePreview(searchable_gap_ids=("gap:storage-cost",))
    artifact = tmp_path / "deep-research" / RESEARCH_ID / "synthesis" / "findings.json"
    payload = json.loads(artifact.read_text(encoding="utf-8"))
    assert payload["gaps"] == [gap]


@pytest.mark.parametrize(
    "gap_ids",
    [
        ("gap:duplicate", "gap:duplicate"),
        ("forged",),
        tuple(f"gap:g{index}" for index in range(33)),
    ],
)
def test_wave2_gate_preview_rejects_noncanonical_or_oversize_ids(gap_ids: tuple[str, ...]) -> None:
    with pytest.raises(ValueError, match="wave2_gate_preview_invalid"):
        Wave2GatePreview(searchable_gap_ids=gap_ids)


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

    with pytest.raises(ValueError, match="synthesis_findings_required"):
        await NODE_SPEC.real_factory(_dependencies(tmp_path, capabilities))(_state())  # type: ignore[arg-type]

    assert len(capabilities.requests) == 2
    assert not (tmp_path / "deep-research" / RESEARCH_ID / "synthesis" / "findings.json").exists()


async def test_real_synthesis_repairs_gaps_only_output_when_accepted_evidence_exists(tmp_path: Path) -> None:
    capabilities = _GapsOnlyRepairCapabilities(valid_repair=True)

    update = await NODE_SPEC.real_factory(_dependencies(tmp_path, capabilities))(_state())  # type: ignore[arg-type]

    assert len(capabilities.requests) == 2
    assert capabilities.requests[1].tools_enabled is False
    assert update[WAVE2_GATE_PREVIEW_KEY] == Wave2GatePreview(searchable_gap_ids=("gap:storage-cost",))
    artifact = tmp_path / "deep-research" / RESEARCH_ID / "synthesis" / "findings.json"
    assert len(json.loads(artifact.read_text(encoding="utf-8"))["findings"]) == 1


async def test_real_synthesis_rejects_gaps_only_repair_without_publishing(tmp_path: Path) -> None:
    capabilities = _GapsOnlyRepairCapabilities(valid_repair=False)

    with pytest.raises(ValueError, match="synthesis_findings_required"):
        await NODE_SPEC.real_factory(_dependencies(tmp_path, capabilities))(_state())  # type: ignore[arg-type]

    assert len(capabilities.requests) == 2
    assert capabilities.requests[1].tools_enabled is False
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
