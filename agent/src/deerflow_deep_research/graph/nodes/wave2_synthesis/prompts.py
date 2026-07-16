"""Wave2 synthesis agent prompt and output parser.

@impl WSN-001
"""

from __future__ import annotations

import json
from collections.abc import Iterable

from deerflow_deep_research.domain.context import NodeExecutionRequest
from deerflow_deep_research.domain.synthesis import SynthesisResult


def build_synthesis_prompt(
    topic_registry: Iterable[dict] | None = None,
    wave0_refs: Iterable[str] = (),
    wave1_refs: Iterable[str] = (),
) -> NodeExecutionRequest:
    """Build a bounded synthesis request from accumulated evidence."""
    topics = list(topic_registry or [])
    topic_names = [t.get("title", t.get("topic_id", "")) for t in topics if isinstance(t, dict)]
    objective = (
        f"Synthesise findings across {len(topics)} topics: {', '.join(topic_names[:10])}. "
        "Read all accepted evidence from Wave0 and Wave1. Produce structured findings "
        "with priority (1-5), affected topics, backing refs, confidence, and "
        "search_required flag. Identify cross-topic relations (supports, contradicts, "
        "extends, qualifies). Record gaps where evidence is missing. "
        "You have NO web tools — if evidence is insufficient, record a gap. "
        "Never fabricate findings without backing evidence."
        f"\n\nWave0 accepted submissions: {json.dumps(sorted(wave0_refs))}"
        f"\nWave1 accepted submissions: {json.dumps(sorted(wave1_refs))}"
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
