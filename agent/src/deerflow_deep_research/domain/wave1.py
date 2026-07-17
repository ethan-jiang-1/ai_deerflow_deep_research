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


def _normalize_scoped_id(value: str, *, prefix: str) -> str:
    if not isinstance(value, str):
        raise ValueError("scoped_id_invalid")
    raw = value.strip()
    for known_prefix in ("claim:w1_", "q:w1_", "claim:", "question:", "q:"):
        if raw.lower().startswith(known_prefix):
            raw = raw[len(known_prefix) :]
            break
    slug = re.sub(r"[^a-zA-Z0-9_-]+", "_", raw).strip("_-")[:64]
    if not slug:
        raise ValueError("scoped_id_invalid")
    return prefix + slug


def _normalize_source_id(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError("source_id_invalid")
    raw = value.strip()
    if SOURCE_ID_RE.fullmatch(raw):
        return raw
    slug = re.sub(r"[^a-zA-Z0-9_.:-]+", "_", raw).strip("_.:-")[:64]
    if not slug:
        raise ValueError("source_id_invalid")
    return f"source:w1_{slug}"


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

    @field_validator("claim_id", mode="before")
    @classmethod
    def normalize_claim_id(cls, value: str) -> str:
        return _normalize_scoped_id(value, prefix="claim:w1_")

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

    @field_validator("question_id", mode="before")
    @classmethod
    def normalize_question_id(cls, value: str) -> str:
        return _normalize_scoped_id(value, prefix="q:w1_")

    @field_validator("state", mode="before")
    @classmethod
    def normalize_state(cls, value: str | OpenQuestionState) -> str | OpenQuestionState:
        if isinstance(value, OpenQuestionState):
            return value
        if not isinstance(value, str):
            raise ValueError("open_question_state_invalid")
        normalized = value.strip().lower().replace("-", "_").replace(" ", "_")
        aliases = {
            "resolved": OpenQuestionState.RESOLVED,
            "answered": OpenQuestionState.RESOLVED,
            "closed": OpenQuestionState.RESOLVED,
            "targeted_search": OpenQuestionState.TARGETED_SEARCH,
            "needs_more_research": OpenQuestionState.TARGETED_SEARCH,
            "needs_research": OpenQuestionState.TARGETED_SEARCH,
            "needs_evidence": OpenQuestionState.TARGETED_SEARCH,
            "open": OpenQuestionState.TARGETED_SEARCH,
            "unresolved": OpenQuestionState.TARGETED_SEARCH,
            "deferred": OpenQuestionState.DEFERRED,
            "later": OpenQuestionState.DEFERRED,
            "requires_internal_data": OpenQuestionState.REQUIRES_INTERNAL_DATA,
            "internal_data_required": OpenQuestionState.REQUIRES_INTERNAL_DATA,
        }
        try:
            return aliases[normalized]
        except KeyError as exc:
            raise ValueError("open_question_state_invalid") from exc


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

    @field_validator("source_id", mode="before")
    @classmethod
    def normalize_source_id(cls, value: str) -> str:
        return _normalize_source_id(value)

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

    @model_validator(mode="before")
    @classmethod
    def normalize_provider_source_refs(cls, value: object) -> object:
        if not isinstance(value, dict):
            return value
        payload = dict(value)
        raw_sources = payload.get("sources")
        source_mapping: dict[str, str] = {}
        used_ids: set[str] = set()
        if isinstance(raw_sources, (tuple, list)):
            normalized_sources: list[object] = []
            for raw_source in raw_sources:
                if not isinstance(raw_source, dict):
                    normalized_sources.append(raw_source)
                    continue
                source = dict(raw_source)
                raw_id = source.get("source_id")
                if not isinstance(raw_id, str):
                    normalized_sources.append(source)
                    continue
                normalized_id = _normalize_source_id(raw_id)
                base_id = normalized_id
                suffix = 2
                while normalized_id in used_ids and source_mapping.get(str(raw_id)) != normalized_id:
                    normalized_id = f"{base_id}_{suffix}"
                    suffix += 1
                used_ids.add(normalized_id)
                source_mapping[raw_id] = normalized_id
                source["source_id"] = normalized_id
                normalized_sources.append(source)
            payload["sources"] = normalized_sources
        if isinstance(payload.get("source_ids"), (tuple, list)):
            payload["source_ids"] = [source_mapping.get(item, item) for item in payload["source_ids"]]
        raw_claims = payload.get("claims")
        if isinstance(raw_claims, (tuple, list)):
            normalized_claims: list[object] = []
            for raw_claim in raw_claims:
                if not isinstance(raw_claim, dict):
                    normalized_claims.append(raw_claim)
                    continue
                claim = dict(raw_claim)
                for field_name in ("support_refs", "counter_refs"):
                    refs = claim.get(field_name)
                    if isinstance(refs, (tuple, list)):
                        claim[field_name] = [source_mapping.get(ref, ref) for ref in refs]
                normalized_claims.append(claim)
            payload["claims"] = normalized_claims
        return payload

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
