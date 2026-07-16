"""Frozen Wave2 synthesis result contracts.

@impl WSN-001
"""

from __future__ import annotations

import re
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import Field

from deerflow_deep_research.domain.work_units import _FrozenModel

FINDING_ID_RE = re.compile(r"^finding:[a-zA-Z0-9_-]{1,64}$")
MAX_FINDINGS = 128
MAX_RELATIONS = 64

SYNTHESIS_SCHEMA_VERSION = 1


class Confidence(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    TENTATIVE = "tentative"


class SynthesisFinding(_FrozenModel):
    finding_id: str = Field(pattern=FINDING_ID_RE.pattern)
    statement: str = Field(min_length=1, max_length=4000)
    priority: int = Field(ge=1, le=5)
    affected_topics: Annotated[tuple[str, ...], Field(max_length=16)] = ()
    backing_refs: Annotated[tuple[str, ...], Field(max_length=32)] = ()
    confidence: Confidence
    search_required: bool = False


class CrossTopicRelation(_FrozenModel):
    relation_id: str = Field(pattern=re.compile(r"^rel:[a-zA-Z0-9_-]{1,64}$"))
    source_finding: str
    target_finding: str
    relation_type: Literal["supports", "contradicts", "extends", "qualifies"]


class GapRecord(_FrozenModel):
    gap_id: str = Field(pattern=re.compile(r"^gap:[a-zA-Z0-9_-]{1,64}$"))
    description: str = Field(min_length=1, max_length=2000)
    priority: int = Field(ge=1, le=5)
    affected_topics: Annotated[tuple[str, ...], Field(max_length=16)] = ()


class SynthesisResult(_FrozenModel):
    schema_version: Literal[1]
    findings: Annotated[tuple[SynthesisFinding, ...], Field(max_length=MAX_FINDINGS)] = ()
    relations: Annotated[tuple[CrossTopicRelation, ...], Field(max_length=MAX_RELATIONS)] = ()
    gaps: Annotated[tuple[GapRecord, ...], Field(max_length=32)] = ()
    summary: str = Field(default="", max_length=8000)
