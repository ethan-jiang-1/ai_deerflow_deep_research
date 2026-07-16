"""Real targeted_evidence node — critic dispatch + gap worker fan-out.

@impl EVC-001, EVC-002, EVC-003
@impl TEL-001, TEL-002
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from deerflow_deep_research.domain.critics import ClaimVerifierResult, SourceDiagnosticResult
from deerflow_deep_research.domain.lifecycle import make_attempt_id
from deerflow_deep_research.domain.node_spec import NodeBuildDependencies
from deerflow_deep_research.engine.fake_control import node_update

from .materializer import materialize_claim_verifier, materialize_source_diagnostic
from .subgraph import dispatch_critic, materialize_gap_intents, run_gap_workers


def build_real(dependencies: NodeBuildDependencies):
    async def run(state: dict[str, Any]) -> dict[str, Any]:
        work_items = state.get("critic_work_items") or ()
        gaps = state.get("synthesis_gaps") or ()
        gap_intents = materialize_gap_intents(gaps)
        workspace_root = dependencies.graph_context.workspace_root
        node_attempt_id = make_attempt_id(state, "targeted_evidence")
        research_id = state["research_id"]

        if gap_intents:
            base = await run_gap_workers(state, gap_intents, dependencies)
        else:
            base = node_update("targeted_evidence")

        if work_items:
            results = await dispatch_critic(
                work_items, dependencies.capabilities, node_attempt_id, research_id, workspace_root
            )
            for entry in results:
                result = entry["result"]
                if isinstance(result, SourceDiagnosticResult):
                    allowed = set()
                    for item in work_items:
                        if item.get("type") == "source_diagnostic":
                            allowed.update(item.get("source_refs", ()))
                    materialize_source_diagnostic(
                        result, node_attempt_id, Path(workspace_root), allowed_source_ids=allowed
                    )
                elif isinstance(result, ClaimVerifierResult):
                    allowed = set()
                    for item in work_items:
                        if item.get("type") == "claim_verifier":
                            allowed.update(item.get("evidence_refs", ()))
                    materialize_claim_verifier(
                        result, node_attempt_id, Path(workspace_root), allowed_source_ids=allowed
                    )

        return {**base, "route": "next"}

    return run
