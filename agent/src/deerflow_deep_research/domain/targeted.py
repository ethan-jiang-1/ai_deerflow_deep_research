"""Frozen targeted-evidence worker and result-document contracts.

@impl TEL-002
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field, model_validator

from deerflow_deep_research.domain.lifecycle import LogicalPhase
from deerflow_deep_research.domain.work_units import (
    CONTENT_HASH_RE,
    MAX_REQUIRED_OUTPUTS,
    MAX_SOURCE_REFS,
    RESEARCH_ID_RE,
    SOURCE_ID_RE,
    WORKER_ROLE_RE,
    _FrozenModel,
    canonicalize_source_url,
)


class TargetedWorkerSource(_FrozenModel):
    source_id: str = Field(pattern=SOURCE_ID_RE.pattern)
    canonical_url: str = Field(min_length=1, max_length=2048)
    title: str = Field(min_length=1, max_length=512)

    @model_validator(mode="after")
    def require_canonical_url(self) -> TargetedWorkerSource:
        if canonicalize_source_url(self.canonical_url) != self.canonical_url:
            raise ValueError("canonical_url_not_canonical")
        return self


class TargetedWorkerOutput(_FrozenModel):
    schema_version: Literal[1]
    gap_id: str = Field(min_length=1, max_length=128)
    gap_status: Literal["resolved", "deferred", "unresolved"]
    sources: Annotated[tuple[TargetedWorkerSource, ...], Field(max_length=MAX_SOURCE_REFS)] = ()
    limitations: str = Field(default="", max_length=2000)


class TargetedSourceMeta(_FrozenModel):
    source_id: str = Field(pattern=SOURCE_ID_RE.pattern)
    canonical_url: str = Field(min_length=1, max_length=2048)
    title: str = Field(min_length=1, max_length=512)
    content_ref: str


class TargetedSourceIntakeResult(_FrozenModel):
    schema_version: Literal[1]
    research_id: str = Field(pattern=RESEARCH_ID_RE.pattern)
    generation: int = Field(ge=0, le=2)
    phase: Literal[LogicalPhase.TARGETED_EVIDENCE]
    work_id: str
    attempt_id: str
    worker_role: str = Field(pattern=WORKER_ROLE_RE.pattern)
    spec_hash: str = Field(pattern=CONTENT_HASH_RE.pattern)
    result_contract: Literal["targeted.source-intake"]
    output_paths: Annotated[tuple[str, ...], Field(max_length=MAX_REQUIRED_OUTPUTS)] = ()
    source_ids: Annotated[tuple[str, ...], Field(max_length=MAX_SOURCE_REFS)] = ()
    sources: Annotated[tuple[TargetedSourceMeta, ...], Field(max_length=MAX_SOURCE_REFS)] = ()
    gap_id: str = Field(min_length=1, max_length=128)
    gap_status: Literal["resolved", "deferred", "unresolved"]
    limitations: str = Field(default="", max_length=2000)

    @model_validator(mode="after")
    def validate_identity_and_sources(self) -> TargetedSourceIntakeResult:
        if not self.attempt_id.startswith(f"{self.work_id}_a"):
            raise ValueError("attempt_id_identity_mismatch")
        if tuple(source.source_id for source in self.sources) != self.source_ids:
            raise ValueError("source_ids_mismatch")
        return self
