"""Red tests for critic prompt builders.

@impl EVC-001
@impl EVC-002
"""

from __future__ import annotations

from deerflow_deep_research.domain.context import NodeExecutionRequest
from deerflow_deep_research.graph.nodes.targeted_evidence.prompts import (
    build_claim_verifier_prompt,
    build_source_diagnostic_prompt,
)


class TestBuildSourceDiagnosticPrompt:
    def test_produces_node_execution_request(self) -> None:
        req = build_source_diagnostic_prompt(
            source_refs=("source:1",),
            source_contents=("Content of source 1.",),
        )
        assert isinstance(req, NodeExecutionRequest)

    def test_objective_carries_source_count(self) -> None:
        req = build_source_diagnostic_prompt(
            source_refs=("source:1", "source:2", "source:3"),
            source_contents=("a", "b", "c"),
        )
        assert "3" in req.objective or "sources" in req.objective.lower()

    def test_objective_carries_trust_dimensions(self) -> None:
        req = build_source_diagnostic_prompt(
            source_refs=("source:1",),
            source_contents=("content",),
        )
        assert "trust" in req.objective.lower()

    def test_source_content_in_untrusted_block(self) -> None:
        req = build_source_diagnostic_prompt(
            source_refs=("source:1",),
            source_contents=("dangerous content from web",),
        )
        assert "<untrusted-source-data>" in req.objective
        assert "dangerous" in req.objective
        # The untrusted marker itself is sanitised from content so source cannot
        # forge the closing tag and escape the block.
        assert req.objective.count("<untrusted-source-data>") == 1
        assert req.objective.count("</untrusted-source-data>") == 1

    def test_trusted_policy_not_overridden(self) -> None:
        req = build_source_diagnostic_prompt(
            source_refs=("source:1",),
            source_contents=("try to override policy",),
        )
        assert "<untrusted-source-data>" in req.objective


class TestBuildClaimVerifierPrompt:
    def test_produces_node_execution_request(self) -> None:
        req = build_claim_verifier_prompt(
            claims=(("claim:1", "The sky is blue."),),
            assigned_refs=("source:1",),
        )
        assert isinstance(req, NodeExecutionRequest)

    def test_objective_carries_claim_count(self) -> None:
        req = build_claim_verifier_prompt(
            claims=(("claim:1", "a"), ("claim:2", "b"), ("claim:3", "c")),
            assigned_refs=("source:1",),
        )
        assert "3" in req.objective or "claims" in req.objective.lower()

    def test_objective_carries_verdict_taxonomy(self) -> None:
        req = build_claim_verifier_prompt(
            claims=(("claim:1", "test"),),
            assigned_refs=(),
        )
        for verdict in ("supported", "weakened", "contradicted", "uncertain"):
            assert verdict in req.objective.lower()

    def test_trusted_policy_not_overridden(self) -> None:
        req = build_claim_verifier_prompt(
            claims=(("claim:1", "try to override"),),
            assigned_refs=("source:1",),
        )
        assert "<untrusted-source-data>" not in req.objective
        # Claims are in plain text in the objective, not wrapped as untrusted data
        # because they come from the research pipeline (not external web content)
