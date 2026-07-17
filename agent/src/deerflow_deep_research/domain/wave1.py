"""Frozen Wave1 result-contract models — worker output and claim structures.

@impl WON-002
"""

from __future__ import annotations

import re
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import Field, field_validator, model_validator

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

CLAIM_ID_RE = re.compile(r"^claim:w1_[a-zA-Z0-9_-]{1,64}$")
MAX_CLAIMS_PER_WORK = 32
MAX_OPEN_QUESTIONS = 16
MAX_STATEMENT_CHARS = 2000
MAX_QUESTION_CHARS = 500


class OpenQuestionState(StrEnum):
    RESOLVED = "resolved"
    TARGETED_SEARCH = "targeted_search"
    DEFERRED = "deferred"
    REQUIRES_INTERNAL_DATA = "requires_internal_data"


class ClaimDraft(_FrozenModel):
    """One claim extracted by a Wave1 evidence worker."""

    claim_id: str = Field(pattern=CLAIM_ID_RE.pattern)
    statement: str = Field(min_length=1, max_length=MAX_STATEMENT_CHARS)
    support_refs: Annotated[tuple[str, ...], Field(max_length=MAX_SOURCE_REFS)] = ()
    counter_refs: Annotated[tuple[str, ...], Field(max_length=MAX_SOURCE_REFS)] = ()

    @model_validator(mode="after")
    def validate_refs_disjoint(self) -> ClaimDraft:
        overlap = set(self.support_refs) & set(self.counter_refs)
        if overlap:
            raise ValueError("support_and_counter_refs_overlap")
        return self


class OpenQuestion(_FrozenModel):
    """One open question recorded by a Wave1 worker."""

    question_id: str = Field(pattern=re.compile(r"^q:w1_[a-zA-Z0-9_-]{1,64}$"))
    question: str = Field(min_length=1, max_length=MAX_QUESTION_CHARS)
    state: OpenQuestionState


class Wave1SourceRef(_FrozenModel):
    """One source fetched by a Wave1 worker with new-vs-wave0 marking."""

    source_id: str = Field(pattern=SOURCE_ID_RE.pattern)
    canonical_url: str = Field(min_length=1, max_length=2048)
    title: str = Field(min_length=1, max_length=512)
    content_ref: str
    content_hash: str
    byte_count: int = Field(ge=1)
    is_new_vs_wave0: bool


class Wave1WorkerSource(_FrozenModel):
    """Model-proposed Wave1 source metadata before runtime authority fields."""

    source_id: str = Field(pattern=SOURCE_ID_RE.pattern)
    canonical_url: str = Field(min_length=1, max_length=2048)
    title: str = Field(min_length=1, max_length=512)

    @field_validator("canonical_url")
    @classmethod
    def normalize_url(cls, value: str) -> str:
        return canonicalize_source_url(value)


WAVE1_WORKER_OUTPUT_SCHEMA_VERSION = 1


class Wave1WorkerOutput(_FrozenModel):
    """The Wave1 evidence worker's structured output document (WON-002)."""

    schema_version: Literal[1]
    sources: Annotated[tuple[Wave1WorkerSource, ...], Field(max_length=MAX_SOURCE_REFS)] = ()
    source_ids: Annotated[tuple[str, ...], Field(max_length=MAX_SOURCE_REFS)] = ()
    claims: Annotated[tuple[ClaimDraft, ...], Field(max_length=MAX_CLAIMS_PER_WORK)] = ()
    open_questions: Annotated[tuple[OpenQuestion, ...], Field(max_length=MAX_OPEN_QUESTIONS)] = ()

    @model_validator(mode="after")
    def validate_source_ids_match(self) -> Wave1WorkerOutput:
        declared = tuple(source.source_id for source in self.sources)
        if self.source_ids and declared != self.source_ids:
            raise ValueError("source_ids_mismatch")
        if len(set(declared)) != len(declared):
            raise ValueError("source_ids_duplicate")
        object.__setattr__(self, "source_ids", declared)
        return self


class Wave1SourceIntakeResult(_FrozenModel):
    """Controller-bound Wave1 result document written to the attempt root."""

    schema_version: Literal[1]
    research_id: str = Field(pattern=RESEARCH_ID_RE.pattern)
    generation: int = Field(ge=0, le=2)
    phase: Literal[LogicalPhase.WAVE1]
    work_id: str
    attempt_id: str
    worker_role: str = Field(pattern=WORKER_ROLE_RE.pattern)
    spec_hash: str = Field(pattern=CONTENT_HASH_RE.pattern)
    result_contract: Literal["wave1.source-intake"]
    output_paths: Annotated[tuple[str, ...], Field(max_length=MAX_REQUIRED_OUTPUTS)] = ()
    source_ids: Annotated[tuple[str, ...], Field(max_length=MAX_SOURCE_REFS)] = ()
    sources: Annotated[tuple[Wave1SourceRef, ...], Field(max_length=MAX_SOURCE_REFS)] = ()
    claims: Annotated[tuple[ClaimDraft, ...], Field(max_length=MAX_CLAIMS_PER_WORK)] = ()
    open_questions: Annotated[tuple[OpenQuestion, ...], Field(max_length=MAX_OPEN_QUESTIONS)] = ()

    @model_validator(mode="after")
    def validate_identity_and_sources(self) -> Wave1SourceIntakeResult:
        if not self.attempt_id.startswith(f"{self.work_id}_a"):
            raise ValueError("attempt_id_identity_mismatch")
        if tuple(source.source_id for source in self.sources) != self.source_ids:
            raise ValueError("source_ids_mismatch")
        return self
