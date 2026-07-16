"""Frozen critic result-contract models for SourceDiagnostic and ClaimVerifier.

@impl EVC-001
@impl EVC-002
"""

from __future__ import annotations

import re
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import Field, model_validator

from deerflow_deep_research.domain.work_units import (
    SOURCE_ID_RE,
    _FrozenModel,
)

# ---------------------------------------------------------------------------
# Claim identity
# ---------------------------------------------------------------------------

CLAIM_ID_RE = re.compile(r"^claim:[a-zA-Z0-9_-]{1,64}$")
MAX_CLAIMS = 32
MAX_REASON_CHARS = 2000


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class SourceTrustTier(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    UNTRUSTED = "untrusted"


class SourceMateriality(StrEnum):
    PRIMARY = "primary"
    SECONDARY = "secondary"
    PERIPHERAL = "peripheral"


class ClaimVerdict(StrEnum):
    SUPPORTED = "supported"
    WEAKENED = "weakened"
    CONTRADICTED = "contradicted"
    UNCERTAIN = "uncertain"


# ---------------------------------------------------------------------------
# Per-source assessment (embedded in SourceDiagnosticResult)
# ---------------------------------------------------------------------------


class CriticSourceAssessment(_FrozenModel):
    """One source's trust and materiality assessment."""

    source_id: str = Field(pattern=SOURCE_ID_RE.pattern)
    trust_tier: SourceTrustTier
    materiality: SourceMateriality
    marketing_risk: bool
    cross_verification_need: bool


# ---------------------------------------------------------------------------
# Per-claim assessment (embedded in ClaimVerifierResult)
# ---------------------------------------------------------------------------


class ClaimAssessment(_FrozenModel):
    """One claim's verification verdict with supporting/countering evidence."""

    claim_id: str = Field(pattern=CLAIM_ID_RE.pattern)
    verdict: ClaimVerdict
    support_refs: Annotated[tuple[str, ...], Field(max_length=32)] = ()
    counter_refs: Annotated[tuple[str, ...], Field(max_length=32)] = ()
    reason: str = Field(min_length=1, max_length=MAX_REASON_CHARS)

    @model_validator(mode="after")
    def validate_refs_disjoint(self) -> ClaimAssessment:
        overlap = set(self.support_refs) & set(self.counter_refs)
        if overlap:
            raise ValueError("support_and_counter_refs_overlap")
        return self


# ---------------------------------------------------------------------------
# Top-level result documents
# ---------------------------------------------------------------------------


class SourceDiagnosticResult(_FrozenModel):
    """The SourceDiagnostic critic's output document (EVC-001)."""

    schema_version: Literal[1]
    sources: Annotated[tuple[CriticSourceAssessment, ...], Field(max_length=64)] = ()
    source_ids: Annotated[tuple[str, ...], Field(max_length=64)] = ()

    @model_validator(mode="after")
    def validate_source_ids_match(self) -> SourceDiagnosticResult:
        declared = tuple(source.source_id for source in self.sources)
        if declared != self.source_ids:
            raise ValueError("source_ids_mismatch")
        if len(set(self.source_ids)) != len(self.source_ids):
            raise ValueError("source_ids_duplicate")
        return self


class ClaimVerifierResult(_FrozenModel):
    """The ClaimVerifier critic's output document (EVC-002)."""

    schema_version: Literal[1]
    claims: Annotated[tuple[ClaimAssessment, ...], Field(max_length=MAX_CLAIMS)] = ()

    @model_validator(mode="after")
    def validate_claim_ids_unique(self) -> ClaimVerifierResult:
        ids = tuple(claim.claim_id for claim in self.claims)
        if len(set(ids)) != len(ids):
            raise ValueError("claim_ids_duplicate")
        return self
