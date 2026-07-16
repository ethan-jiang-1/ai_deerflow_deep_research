"""Red tests for critic materializer functions.

@impl EVC-004
"""

from __future__ import annotations

from pathlib import Path

import pytest

from deerflow_deep_research.domain.critics import (
    ClaimVerifierResult,
    SourceDiagnosticResult,
)
from deerflow_deep_research.graph.nodes.targeted_evidence.materializer import (
    materialize_claim_verifier,
    materialize_source_diagnostic,
)

ATTEMPT = "g0_wave2_a01"
ALLOWED_SOURCES = {"source:1", "source:2"}


def _diag_result(**overrides) -> SourceDiagnosticResult:
    data = {
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
    data.update(overrides)
    return SourceDiagnosticResult.model_validate(data)


def _claim_result(**overrides) -> ClaimVerifierResult:
    data = {
        "schema_version": 1,
        "claims": [
            {
                "claim_id": "claim:1",
                "verdict": "supported",
                "support_refs": ["source:1"],
                "counter_refs": [],
                "reason": "Evidence supports.",
            }
        ],
    }
    data.update(overrides)
    return ClaimVerifierResult.model_validate(data)


class TestMaterializeSourceDiagnostic:
    def test_writes_canonical_json(self, tmp_path: Path) -> None:
        result = _diag_result()
        materialize_source_diagnostic(result, ATTEMPT, tmp_path, allowed_source_ids=ALLOWED_SOURCES)
        path = tmp_path / "critic" / ATTEMPT / "source-diagnostic.json"
        assert path.exists()
        raw = path.read_bytes()
        reloaded = SourceDiagnosticResult.model_validate_json(raw)
        assert reloaded == result

    def test_rejects_non_assigned_source_ref(self, tmp_path: Path) -> None:
        result = _diag_result(
            source_ids=["source:99"],
            sources=[
                {
                    "source_id": "source:99",
                    "trust_tier": "low",
                    "materiality": "peripheral",
                    "marketing_risk": False,
                    "cross_verification_need": False,
                }
            ],
        )
        with pytest.raises(ValueError, match="source_not_in_assigned"):
            materialize_source_diagnostic(result, ATTEMPT, tmp_path, allowed_source_ids={"source:1"})

    def test_overwrites_existing(self, tmp_path: Path) -> None:
        path = tmp_path / "critic" / ATTEMPT / "source-diagnostic.json"
        path.parent.mkdir(parents=True)
        path.write_text("old")
        result = _diag_result()
        materialize_source_diagnostic(result, ATTEMPT, tmp_path, allowed_source_ids=ALLOWED_SOURCES)
        reloaded = SourceDiagnosticResult.model_validate_json(path.read_bytes())
        assert reloaded == result


class TestMaterializeClaimVerifier:
    def test_writes_canonical_json(self, tmp_path: Path) -> None:
        result = _claim_result()
        materialize_claim_verifier(result, ATTEMPT, tmp_path, allowed_source_ids=ALLOWED_SOURCES)
        path = tmp_path / "critic" / ATTEMPT / "claim-verifier.json"
        assert path.exists()
        raw = path.read_bytes()
        reloaded = ClaimVerifierResult.model_validate_json(raw)
        assert reloaded == result

    def test_rejects_dangling_ref_in_support(self, tmp_path: Path) -> None:
        result = _claim_result(
            claims=[
                {
                    "claim_id": "claim:1",
                    "verdict": "supported",
                    "support_refs": ["source:99"],
                    "counter_refs": [],
                    "reason": "test",
                }
            ]
        )
        with pytest.raises(ValueError, match="source_not_in_assigned"):
            materialize_claim_verifier(result, ATTEMPT, tmp_path, allowed_source_ids={"source:1"})

    def test_rejects_dangling_ref_in_counter(self, tmp_path: Path) -> None:
        result = _claim_result(
            claims=[
                {
                    "claim_id": "claim:1",
                    "verdict": "contradicted",
                    "support_refs": [],
                    "counter_refs": ["source:99"],
                    "reason": "test",
                }
            ]
        )
        with pytest.raises(ValueError, match="source_not_in_assigned"):
            materialize_claim_verifier(result, ATTEMPT, tmp_path, allowed_source_ids={"source:1"})

    def test_rejects_invalid_json(self, tmp_path: Path) -> None:
        result = ClaimVerifierResult(schema_version=1, claims=())  # valid
        path = tmp_path / "critic" / ATTEMPT / "claim-verifier.json"
        path.parent.mkdir(parents=True)
        path.write_text("not json")
        # Materialize overwrites, so this is fine — the test checks the
        # function itself doesn't produce invalid JSON.
        materialize_claim_verifier(result, ATTEMPT, tmp_path, allowed_source_ids=ALLOWED_SOURCES)
        reloaded = ClaimVerifierResult.model_validate_json(path.read_bytes())
        assert reloaded == result
