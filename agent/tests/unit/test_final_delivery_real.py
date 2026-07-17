"""Tests for real final delivery node.

@impl FID-001..005
"""

from __future__ import annotations

import base64
import hashlib
import json
import time
from datetime import UTC, datetime

from deerflow_deep_research.domain.context import GraphContextView, NodeAgentContext
from deerflow_deep_research.domain.lifecycle import LifecycleStatus
from deerflow_deep_research.domain.node_spec import NodeBuildDependencies
from deerflow_deep_research.graph.nodes.final_delivery.node import build_real
from deerflow_deep_research.runtime.work_unit_store import WorkUnitStore


def _deps(*, publication_bundle=None):
    graph = GraphContextView(
        research_scope_id="r_" + "A" * 43,
        workspace_root="/mnt/user-data/workspace/deep-research/r",
        uploads_root="/mnt/user-data/uploads",
        outputs_root="/mnt/user-data/outputs/deep-research/r",
    )
    return NodeBuildDependencies(
        graph_context=graph,
        agent_context=NodeAgentContext(
            research_scope_id=graph.research_scope_id,
            node_name="final_delivery",
            attempt_id="g0-final-a1",
            workspace_root=graph.workspace_root,
            attempt_root=f"{graph.workspace_root}/final",
            policy_name="skeleton-final-delivery",
        ),
        capabilities=object(),
        publication_bundle=publication_bundle,
    )


class TestRealFinalDelivery:
    async def test_materializes_report_and_citation_map_with_matching_refs(self, tmp_path) -> None:
        research_id = "r_" + "A" * 43
        store = WorkUnitStore(
            workspace_host_path=tmp_path,
            research_id=research_id,
            clock=lambda: datetime(2026, 7, 17, tzinfo=UTC),
            monotonic=time.monotonic,
            lock_sleep=time.sleep,
            token_factory=lambda: "7" * 32,
            fault_hook=None,
        )
        result = await build_real(_deps(publication_bundle=store))(
            {
                "research_id": research_id,
                "generation": 0,
                "accepted_submission_refs": ("ref:accepted",),
                "readiness_report_plan": None,
            }
        )

        final_root = tmp_path / "deep-research" / research_id / "final"
        report = (final_root / "report.md").read_bytes()
        citation_map = (final_root / "claim-citation-map.json").read_bytes()
        assert report == (
            b"# Deep Research Report\n\n"
            b"*Evidence base: 1 accepted submissions*\n\n"
            b"## Findings\n\n"
            b"No readiness report plan available.\n"
        )
        assert json.loads(citation_map) == {"schema_version": 1, "claims": {}}
        refs = {ref.sandbox_path: ref for ref in result["report_refs"]}
        for name, content in (("report.md", report), ("claim-citation-map.json", citation_map)):
            path = f"workspace/deep-research/{research_id}/final/{name}"
            expected_hash = "h_" + base64.urlsafe_b64encode(hashlib.sha256(content).digest()).decode().rstrip("=")
            assert refs[path].content_hash == expected_hash

    async def test_produces_report_refs_and_completed(self, tmp_path) -> None:
        store = WorkUnitStore(
            workspace_host_path=tmp_path,
            research_id="r_" + "A" * 43,
            clock=lambda: datetime(2026, 7, 17, tzinfo=UTC),
            monotonic=time.monotonic,
            lock_sleep=time.sleep,
            token_factory=lambda: "8" * 32,
            fault_hook=None,
        )
        state = {
            "research_id": "r_" + "A" * 43,
            "generation": 0,
            "accepted_submission_refs": ("ref:1", "ref:2"),
            "readiness_report_plan": None,
        }
        result = await build_real(_deps(publication_bundle=store))(state)
        assert result["terminal_status"] == LifecycleStatus.COMPLETED.value
        assert len(result["report_refs"]) == 2
        assert result["phase"] == "final_delivery"

    async def test_handles_empty_evidence(self, tmp_path) -> None:
        store = WorkUnitStore(
            workspace_host_path=tmp_path,
            research_id="r_" + "A" * 43,
            clock=lambda: datetime(2026, 7, 17, tzinfo=UTC),
            monotonic=time.monotonic,
            lock_sleep=time.sleep,
            token_factory=lambda: "9" * 32,
            fault_hook=None,
        )
        state = {
            "research_id": "r_" + "A" * 43,
            "generation": 0,
            "accepted_submission_refs": (),
            "readiness_report_plan": None,
        }
        result = await build_real(_deps(publication_bundle=store))(state)
        assert result["terminal_status"] == LifecycleStatus.COMPLETED.value
        assert len(result["report_refs"]) == 2

    async def test_publication_replay_is_idempotent_and_conflicting_content_fails_closed(self, tmp_path) -> None:
        research_id = "r_" + "A" * 43
        store = WorkUnitStore(
            workspace_host_path=tmp_path,
            research_id=research_id,
            clock=lambda: datetime(2026, 7, 17, tzinfo=UTC),
            monotonic=time.monotonic,
            lock_sleep=time.sleep,
            token_factory=lambda: "a" * 32,
            fault_hook=None,
        )
        first = await store.publish_final(b"report\n", b'{"claims":{}}')
        replay = await store.publish_final(b"report\n", b'{"claims":{}}')
        assert replay == first

        import pytest

        with pytest.raises(ValueError, match="final_artifact_write_conflict"):
            await store.publish_final(b"changed\n", b'{"claims":{}}')
