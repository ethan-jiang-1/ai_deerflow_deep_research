"""Frozen Wave2 synthesis result contracts.

@impl WSN-001
"""

from __future__ import annotations

import re
from enum import StrEnum
from typing import Annotated, Any, Literal, Protocol, runtime_checkable

from pydantic import Field, model_validator

from deerflow_deep_research.domain.work_units import CONTENT_HASH_RE, _FrozenModel

FINDING_ID_RE = re.compile(r"^finding:[a-zA-Z0-9_-]{1,64}$")
MAX_FINDINGS = 128
MAX_RELATIONS = 64
MAX_SYNTHESIS_EVIDENCE_ENTRY_BYTES = 24 * 1024
MAX_SYNTHESIS_EVIDENCE_TOTAL_BYTES = 96 * 1024

SYNTHESIS_SCHEMA_VERSION = 1


def _scoped_id(value: Any, *, prefix: str) -> str:
    if not isinstance(value, str):
        raise ValueError("synthesis_id_invalid")
    raw = value.strip()
    for known in ("finding:", "rel:", "gap:"):
        if raw.lower().startswith(known):
            raw = raw[len(known) :]
            break
    slug = re.sub(r"[^a-zA-Z0-9_-]+", "_", raw).strip("_-")[:64]
    if not slug:
        raise ValueError("synthesis_id_invalid")
    return prefix + slug


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


class SynthesisEvidence(_FrozenModel):
    submission_ref: str = Field(pattern=CONTENT_HASH_RE.pattern)
    phase: str = Field(min_length=1, max_length=64)
    result_contract: str = Field(min_length=1, max_length=128)
    content: str = Field(max_length=MAX_SYNTHESIS_EVIDENCE_ENTRY_BYTES)
    truncated: bool = False


class SynthesisResult(_FrozenModel):
    schema_version: Literal[1]
    findings: Annotated[tuple[SynthesisFinding, ...], Field(max_length=MAX_FINDINGS)] = ()
    relations: Annotated[tuple[CrossTopicRelation, ...], Field(max_length=MAX_RELATIONS)] = ()
    gaps: Annotated[tuple[GapRecord, ...], Field(max_length=32)] = ()
    summary: str = Field(default="", max_length=8000)

    @model_validator(mode="before")
    @classmethod
    def normalize_provider_shape(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        payload = dict(value)
        finding_aliases: dict[str, str] = {}
        normalized_findings: list[Any] = []
        for raw_finding in payload.get("findings") or ():
            if not isinstance(raw_finding, dict):
                normalized_findings.append(raw_finding)
                continue
            finding = dict(raw_finding)
            raw_id = finding.pop(
                "id",
                finding.get("finding_id") or finding.get("statement") or finding.get("description") or "",
            )
            finding_id = _scoped_id(raw_id, prefix="finding:")
            finding["finding_id"] = finding_id
            if "statement" not in finding and isinstance(finding.get("description"), str):
                finding["statement"] = finding["description"]
            finding.pop("description", None)
            evidence_refs = finding.pop("evidence_refs", ())
            source_ids = finding.pop("source_ids", ())
            if "backing_refs" not in finding:
                combined_refs = [
                    ref
                    for refs in (evidence_refs, source_ids)
                    if isinstance(refs, (tuple, list))
                    for ref in refs
                    if isinstance(ref, str)
                ]
                finding["backing_refs"] = list(dict.fromkeys(combined_refs))
            finding.setdefault("priority", 3)
            finding.setdefault("confidence", "medium")
            if isinstance(raw_id, str):
                finding_aliases[raw_id] = finding_id
            finding_aliases[finding_id] = finding_id
            normalized_findings.append(finding)
        payload["findings"] = normalized_findings

        normalized_relations: list[Any] = []
        for raw_relation in payload.get("relations") or ():
            if not isinstance(raw_relation, dict):
                normalized_relations.append(raw_relation)
                continue
            relation = dict(raw_relation)
            source_alias = (
                relation.get("source_finding") or relation.get("finding_id_a") or relation.get("from_finding")
            )
            target_alias = relation.get("target_finding") or relation.get("finding_id_b") or relation.get("to_finding")
            relation_type = relation.get("relation_type") or relation.get("type")
            raw_relation_id = relation.get("id") or relation.get("relation_id")
            if not raw_relation_id and isinstance(source_alias, str) and isinstance(target_alias, str):
                raw_relation_id = f"{source_alias}_{relation_type or 'relates'}_{target_alias}"
            relation["relation_id"] = _scoped_id(
                raw_relation_id or "",
                prefix="rel:",
            )
            relation.pop("id", None)
            relation.pop("description", None)
            relation["relation_type"] = relation_type
            relation.pop("type", None)
            if "source_finding" not in relation:
                relation["source_finding"] = relation.pop("finding_id_a", relation.pop("from_finding", ""))
            else:
                relation.pop("finding_id_a", None)
                relation.pop("from_finding", None)
            if "target_finding" not in relation:
                relation["target_finding"] = relation.pop("finding_id_b", relation.pop("to_finding", ""))
            else:
                relation.pop("finding_id_b", None)
                relation.pop("to_finding", None)
            for field_name in ("source_finding", "target_finding"):
                raw_ref = relation.get(field_name)
                if isinstance(raw_ref, str):
                    relation[field_name] = finding_aliases.get(
                        raw_ref,
                        _scoped_id(raw_ref, prefix="finding:"),
                    )
            normalized_relations.append(relation)
        payload["relations"] = normalized_relations

        normalized_gaps: list[Any] = []
        for raw_gap in payload.get("gaps") or ():
            if isinstance(raw_gap, str):
                description = raw_gap.strip()
                if not description:
                    normalized_gaps.append(raw_gap)
                    continue
                normalized_gaps.append(
                    {
                        "gap_id": _scoped_id(description, prefix="gap:"),
                        "description": description,
                        "priority": 3,
                        "affected_topics": (),
                    }
                )
                continue
            if not isinstance(raw_gap, dict):
                normalized_gaps.append(raw_gap)
                continue
            gap = dict(raw_gap)
            raw_gap_id = gap.pop("id", gap.get("gap_id")) or gap.get("description") or gap.get("question") or ""
            gap["gap_id"] = _scoped_id(raw_gap_id, prefix="gap:")
            if "description" not in gap and isinstance(gap.get("question"), str):
                gap["description"] = gap.pop("question")
            affected_topic = gap.pop("affected_topic", None)
            if "affected_topics" not in gap and isinstance(affected_topic, str):
                gap["affected_topics"] = (affected_topic,)
            severity = gap.pop("severity", None)
            if "priority" not in gap and severity is not None:
                if isinstance(severity, int) and 1 <= severity <= 5:
                    gap["priority"] = severity
                elif isinstance(severity, str):
                    normalized_severity = severity.strip().lower().replace("-", "_").replace(" ", "_")
                    priorities = {
                        "critical": 1,
                        "high": 1,
                        "medium": 3,
                        "moderate": 3,
                        "low": 5,
                    }
                    try:
                        gap["priority"] = priorities[normalized_severity]
                    except KeyError as exc:
                        raise ValueError("gap_severity_invalid") from exc
                else:
                    raise ValueError("gap_severity_invalid")
            gap.setdefault("priority", 3)
            normalized_gaps.append(gap)
        payload["gaps"] = normalized_gaps
        return payload


@runtime_checkable
class SynthesisBundleStoreProtocol(Protocol):
    async def read_synthesis_evidence(self, accepted_refs: tuple[str, ...]) -> tuple[SynthesisEvidence, ...]: ...

    async def write_synthesis(self, result: SynthesisResult) -> None: ...
