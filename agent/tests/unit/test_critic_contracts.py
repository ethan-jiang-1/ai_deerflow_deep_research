"""Red tests for SourceDiagnosticResult and ClaimVerifierResult contracts.

@impl EVC-001
@impl EVC-002
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from deerflow_deep_research.domain.critics import (
    ClaimVerdict,
    ClaimVerifierResult,
    SourceDiagnosticResult,
    SourceMateriality,
    SourceTrustTier,
)
from deerflow_deep_research.domain.work_units import canonical_json_bytes

# ---------------------------------------------------------------------------
# SourceDiagnosticResult
# ---------------------------------------------------------------------------


class TestSourceDiagnosticResult:
    """EVC-001: frozen model, schema_version=1, per-source enums, unknown-field reject."""

    def test_valid_minimal_model(self) -> None:
        result = SourceDiagnosticResult(
            schema_version=1,
            sources=(),
            source_ids=(),
        )
        assert result.schema_version == 1
        assert result.sources == ()
        assert result.source_ids == ()

    def test_valid_with_single_source(self) -> None:
        result = SourceDiagnosticResult(
            schema_version=1,
            sources=(
                {
                    "source_id": "source:1",
                    "trust_tier": "high",
                    "materiality": "primary",
                    "marketing_risk": False,
                    "cross_verification_need": False,
                },
            ),
            source_ids=("source:1",),
        )
        assert result.sources[0].source_id == "source:1"
        assert result.sources[0].trust_tier == SourceTrustTier.HIGH
        assert result.sources[0].materiality == SourceMateriality.PRIMARY

    def test_trust_tier_enum_values(self) -> None:
        for value in ("high", "medium", "low", "untrusted"):
            result = SourceDiagnosticResult(
                schema_version=1,
                sources=(
                    {
                        "source_id": "source:1",
                        "trust_tier": value,
                        "materiality": "secondary",
                        "marketing_risk": False,
                        "cross_verification_need": False,
                    },
                ),
                source_ids=("source:1",),
            )
            assert result.sources[0].trust_tier.value == value

    def test_materiality_enum_values(self) -> None:
        for value in ("primary", "secondary", "peripheral"):
            result = SourceDiagnosticResult(
                schema_version=1,
                sources=(
                    {
                        "source_id": "source:1",
                        "trust_tier": "medium",
                        "materiality": value,
                        "marketing_risk": False,
                        "cross_verification_need": False,
                    },
                ),
                source_ids=("source:1",),
            )
            assert result.sources[0].materiality.value == value

    def test_rejects_unknown_field(self) -> None:
        with pytest.raises(ValidationError):
            SourceDiagnosticResult(
                schema_version=1,
                sources=(),
                source_ids=(),
                unknown_field="nope",  # type: ignore[call-arg]
            )

    def test_defaults_empty_sources(self) -> None:
        result = SourceDiagnosticResult(schema_version=1)
        assert result.sources == ()
        assert result.source_ids == ()

    def test_rejects_invalid_schema_version(self) -> None:
        with pytest.raises(ValidationError):
            SourceDiagnosticResult(
                schema_version=2,  # only 1 is valid
                sources=(),
                source_ids=(),
            )

    def test_rejects_invalid_trust_tier(self) -> None:
        with pytest.raises(ValidationError):
            SourceDiagnosticResult(
                schema_version=1,
                sources=(
                    {
                        "source_id": "source:1",
                        "trust_tier": "super_trusted",  # invalid
                        "materiality": "primary",
                        "marketing_risk": False,
                        "cross_verification_need": False,
                    },
                ),
                source_ids=("source:1",),
            )

    def test_rejects_invalid_materiality(self) -> None:
        with pytest.raises(ValidationError):
            SourceDiagnosticResult(
                schema_version=1,
                sources=(
                    {
                        "source_id": "source:1",
                        "trust_tier": "medium",
                        "materiality": "critical",  # invalid
                        "marketing_risk": False,
                        "cross_verification_need": False,
                    },
                ),
                source_ids=("source:1",),
            )

    def test_rejects_mismatched_source_ids(self) -> None:
        with pytest.raises(ValidationError):
            SourceDiagnosticResult(
                schema_version=1,
                sources=(
                    {
                        "source_id": "source:1",
                        "trust_tier": "high",
                        "materiality": "primary",
                        "marketing_risk": False,
                        "cross_verification_need": False,
                    },
                ),
                source_ids=("source:2",),  # doesn't match source:1
            )

    def test_canonical_json_roundtrip(self) -> None:
        result = SourceDiagnosticResult(
            schema_version=1,
            sources=(
                {
                    "source_id": "source:1",
                    "trust_tier": "low",
                    "materiality": "peripheral",
                    "marketing_risk": True,
                    "cross_verification_need": True,
                },
            ),
            source_ids=("source:1",),
        )
        raw = canonical_json_bytes(result)
        reloaded = SourceDiagnosticResult.model_validate_json(raw)
        assert reloaded == result

    def test_empty_sources_with_matching_ids(self) -> None:
        result = SourceDiagnosticResult(schema_version=1, sources=(), source_ids=())
        assert result.source_ids == ()
        raw = canonical_json_bytes(result)
        assert SourceDiagnosticResult.model_validate_json(raw) == result


# ---------------------------------------------------------------------------
# ClaimVerifierResult
# ---------------------------------------------------------------------------


class TestClaimVerifierResult:
    """EVC-002: frozen model, schema_version=1, per-claim verdict enum, support/counter refs."""

    def test_valid_minimal_model(self) -> None:
        result = ClaimVerifierResult(
            schema_version=1,
            claims=(),
        )
        assert result.schema_version == 1
        assert result.claims == ()

    def test_valid_supported_verdict(self) -> None:
        result = ClaimVerifierResult(
            schema_version=1,
            claims=(
                {
                    "claim_id": "claim:1",
                    "verdict": "supported",
                    "support_refs": ("source:1",),
                    "counter_refs": (),
                    "reason": "Source directly supports the claim.",
                },
            ),
        )
        assert result.claims[0].claim_id == "claim:1"
        assert result.claims[0].verdict == ClaimVerdict.SUPPORTED
        assert result.claims[0].support_refs == ("source:1",)
        assert result.claims[0].counter_refs == ()

    def test_verdict_enum_values(self) -> None:
        for value in ("supported", "weakened", "contradicted", "uncertain"):
            result = ClaimVerifierResult(
                schema_version=1,
                claims=(
                    {
                        "claim_id": "claim:1",
                        "verdict": value,
                        "support_refs": (),
                        "counter_refs": (),
                        "reason": "test",
                    },
                ),
            )
            assert result.claims[0].verdict.value == value

    def test_supported_with_counter_refs(self) -> None:
        result = ClaimVerifierResult(
            schema_version=1,
            claims=(
                {
                    "claim_id": "claim:1",
                    "verdict": "supported",
                    "support_refs": ("source:1",),
                    "counter_refs": ("source:2",),
                    "reason": "Mostly supported but one source disagrees.",
                },
            ),
        )
        assert result.claims[0].support_refs == ("source:1",)
        assert result.claims[0].counter_refs == ("source:2",)

    def test_uncertain_with_both_refs(self) -> None:
        result = ClaimVerifierResult(
            schema_version=1,
            claims=(
                {
                    "claim_id": "claim:1",
                    "verdict": "uncertain",
                    "support_refs": ("source:1",),
                    "counter_refs": ("source:2",),
                    "reason": "Equal evidence on both sides.",
                },
            ),
        )
        assert result.claims[0].verdict == ClaimVerdict.UNCERTAIN

    def test_rejects_unknown_field(self) -> None:
        with pytest.raises(ValidationError):
            ClaimVerifierResult(
                schema_version=1,
                claims=(),
                bogus="x",  # type: ignore[call-arg]
            )

    def test_defaults_empty_claims(self) -> None:
        result = ClaimVerifierResult(schema_version=1)
        assert result.claims == ()

    def test_rejects_invalid_schema_version(self) -> None:
        with pytest.raises(ValidationError):
            ClaimVerifierResult(
                schema_version=2,  # only 1 is valid
                claims=(),
            )

    def test_rejects_invalid_verdict(self) -> None:
        with pytest.raises(ValidationError):
            ClaimVerifierResult(
                schema_version=1,
                claims=(
                    {
                        "claim_id": "claim:1",
                        "verdict": "proven",  # invalid
                        "support_refs": (),
                        "counter_refs": (),
                        "reason": "test",
                    },
                ),
            )

    def test_rejects_invalid_claim_id(self) -> None:
        with pytest.raises(ValidationError):
            ClaimVerifierResult(
                schema_version=1,
                claims=(
                    {
                        "claim_id": "not-a-valid-id",  # doesn't match CLAIM_ID_RE
                        "verdict": "supported",
                        "support_refs": (),
                        "counter_refs": (),
                        "reason": "test",
                    },
                ),
            )

    def test_canonical_json_roundtrip(self) -> None:
        result = ClaimVerifierResult(
            schema_version=1,
            claims=(
                {
                    "claim_id": "claim:1",
                    "verdict": "contradicted",
                    "support_refs": ("source:1",),
                    "counter_refs": ("source:2", "source:3"),
                    "reason": "Multiple sources contradict.",
                },
            ),
        )
        raw = canonical_json_bytes(result)
        reloaded = ClaimVerifierResult.model_validate_json(raw)
        assert reloaded == result

    def test_empty_claims(self) -> None:
        result = ClaimVerifierResult(schema_version=1, claims=())
        raw = canonical_json_bytes(result)
        assert ClaimVerifierResult.model_validate_json(raw) == result
