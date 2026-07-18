"""Wave2 synthesis agent prompt and output parser.

@impl WSN-001
"""

from __future__ import annotations

import json
from collections.abc import Iterable

from deerflow_deep_research.domain.context import NodeExecutionRequest
from deerflow_deep_research.domain.synthesis import SynthesisEvidence, SynthesisResult
from deerflow_deep_research.domain.untrusted import build_untrusted_data_block


def _expected_synthesis_output() -> str:
    return json.dumps(
        {
            "instruction": "Return exactly one JSON object and no markdown, prose, or code fences.",
            "schema_version": 1,
            "required_keys": ["schema_version", "findings", "relations", "gaps", "summary"],
            "finding_required_keys": [
                "finding_id",
                "statement",
                "priority",
                "affected_topics",
                "backing_refs",
                "confidence",
                "search_required",
            ],
            "confidence_values": ["high", "medium", "low", "tentative"],
            "relation_required_keys": [
                "relation_id",
                "source_finding",
                "target_finding",
                "relation_type",
            ],
            "relation_type_values": ["supports", "contradicts", "extends", "qualifies"],
            "gap_required_keys": [
                "gap_id",
                "description",
                "priority",
                "affected_topics",
                "search_required",
            ],
        },
        sort_keys=True,
        separators=(",", ":"),
    )


def build_synthesis_prompt(
    topic_registry: Iterable[dict] | None = None,
    wave0_refs: Iterable[str] = (),
    wave1_refs: Iterable[str] = (),
    evidence: Iterable[SynthesisEvidence] = (),
) -> NodeExecutionRequest:
    """Build a bounded synthesis request from accumulated evidence."""
    topics = list(topic_registry or [])
    topic_names = [t.get("title", t.get("topic_id", "")) for t in topics if isinstance(t, dict)]
    evidence_payload = [item.model_dump(mode="json") for item in evidence]
    objective = (
        f"Synthesise findings across {len(topics)} topics: {', '.join(topic_names[:10])}. "
        "Read all accepted evidence from Wave0 and Wave1. Produce structured findings "
        "with priority (1-5), affected topics, backing refs, confidence, and a "
        "search_required boolean key inside every finding object. Identify cross-topic relations "
        "whose relation_type is supports, contradicts, extends, or qualifies. Confidence must be "
        "high, medium, low, or tentative. Record gaps where evidence is missing. "
        "Every gap object must include its own search_required boolean key; set it true only when "
        "a later targeted web search should be scheduled for that gap. "
        "You have NO web tools — if evidence is insufficient, record a gap. "
        "Never fabricate findings without backing evidence. When accepted evidence is present, "
        "return at least one evidence-backed finding; gaps may accompany findings."
        f"\n\nWave0 accepted submissions: {json.dumps(sorted(wave0_refs))}"
        f"\nWave1 accepted submissions: {json.dumps(sorted(wave1_refs))}"
        "\n\nAccepted evidence records:\n"
        + build_untrusted_data_block(
            [json.dumps(evidence_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))]
        )
    )
    return NodeExecutionRequest(
        objective=objective,
        expected_output=_expected_synthesis_output(),
    )


def parse_synthesis_output(text: str) -> SynthesisResult:
    if not isinstance(text, str) or not text.strip():
        raise ValueError("synthesis_output_empty")
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError("synthesis_output_json_invalid") from exc
    if not isinstance(payload, dict):
        raise ValueError("synthesis_output_not_object")
    return SynthesisResult.model_validate(payload)


def build_synthesis_repair_prompt(
    draft: str,
    evidence: Iterable[SynthesisEvidence] = (),
) -> NodeExecutionRequest:
    evidence_payload = [item.model_dump(mode="json") for item in evidence]
    objective = (
        "Convert the untrusted draft below into exactly one JSON object matching the synthesis schema. "
        "Every finding object and every gap object must include its own search_required boolean key; "
        "finding confidence must be high, medium, low, or tentative, and relation_type must be supports, "
        "contradicts, extends, or qualifies. "
        "the gap flag is true only when later targeted web search should be scheduled. "
        "Use only the accepted evidence records below. Preserve supported draft content, and derive at least one "
        "backed finding from those records; gaps may accompany findings. Do not invent evidence "
        "refs, relations, or facts absent from the accepted evidence. Return JSON only, with no markdown, "
        "reasoning, tool calls, or code fences.\n\n"
        + build_untrusted_data_block(
            [
                "model_draft:\n" + (draft[:8_192] if isinstance(draft, str) else ""),
                "accepted_evidence:\n"
                + json.dumps(evidence_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
            ]
        )
    )
    return NodeExecutionRequest(
        objective=objective,
        expected_output=_expected_synthesis_output(),
        tools_enabled=False,
    )
