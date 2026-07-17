"""Wave2 synthesis agent prompt and output parser.

@impl WSN-001
"""

from __future__ import annotations

import json
from collections.abc import Iterable

from deerflow_deep_research.domain.context import NodeExecutionRequest
from deerflow_deep_research.domain.synthesis import SynthesisEvidence, SynthesisResult
from deerflow_deep_research.domain.untrusted import build_untrusted_data_block


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
        "with priority (1-5), affected topics, backing refs, confidence, and "
        "search_required flag. Identify cross-topic relations (supports, contradicts, "
        "extends, qualifies). Record gaps where evidence is missing. "
        "You have NO web tools — if evidence is insufficient, record a gap. "
        "Never fabricate findings without backing evidence. When accepted evidence is present, "
        "return at least one evidence-backed finding or one explicit gap."
        f"\n\nWave0 accepted submissions: {json.dumps(sorted(wave0_refs))}"
        f"\nWave1 accepted submissions: {json.dumps(sorted(wave1_refs))}"
        "\n\nAccepted evidence records:\n"
        + build_untrusted_data_block(
            [json.dumps(evidence_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))]
        )
    )
    expected = {
        "instruction": "Return exactly one JSON object and no markdown, prose, or code fences.",
        "schema_version": 1,
        "required_keys": ["schema_version", "findings", "relations", "gaps", "summary"],
    }
    return NodeExecutionRequest(
        objective=objective,
        expected_output=json.dumps(expected, sort_keys=True, separators=(",", ":")),
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
        "Use only the accepted evidence records below. Preserve supported draft content, and derive a finding "
        "or explicit gap from those records when the draft is empty or tool/path-shaped. Do not invent evidence "
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
        expected_output=("A JSON object with schema_version=1, findings, relations, gaps, and summary."),
        tools_enabled=False,
    )
