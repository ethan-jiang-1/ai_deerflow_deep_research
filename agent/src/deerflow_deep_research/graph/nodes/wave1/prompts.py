"""Wave1 evidence worker prompt and output parser.

@impl WON-002
"""

from __future__ import annotations

import json

from deerflow_deep_research.domain.context import NodeExecutionRequest
from deerflow_deep_research.domain.wave1 import Wave1WorkerOutput


def build_wave1_worker_prompt(
    topic: dict,
    wave0_urls: frozenset[str],
) -> NodeExecutionRequest:
    """Build a bounded Wave1 evidence worker request for one topic."""
    bindings = topic.get("must_answer_bindings") or ()
    topic_json = json.dumps(
        {
            "topic_id": topic.get("topic_id", ""),
            "title": topic.get("title", ""),
            "scope": topic.get("scope", ""),
            "must_answer_bindings": list(bindings) if isinstance(bindings, (tuple, list)) else [],
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    wave0_list = sorted(wave0_urls) if wave0_urls else []
    objective = (
        "Perform deep evidence extraction for this research topic. Search for new "
        "sources beyond the Wave0 baseline. For each new source, record its "
        "canonical URL, title, content ref/hash/byte_count, and set "
        "is_new_vs_wave0=true. Extract structured claims with support_refs and "
        "counter_refs. Record open questions with resolution states. "
        f"Wave0 already covered these URLs (do NOT re-fetch): {json.dumps(wave0_list)}"
        f"\n\nTopic:\n{topic_json}"
    )
    expected = {
        "instruction": "Return exactly one JSON object and no markdown, prose, or code fences.",
        "schema_version": 1,
        "required_keys": ["schema_version", "sources", "source_ids"],
        "source_required_keys": [
            "source_id",
            "canonical_url",
            "title",
            "content_ref",
            "content_hash",
            "byte_count",
            "is_new_vs_wave0",
        ],
        "claim_required_keys": ["claim_id", "statement", "support_refs", "counter_refs"],
        "question_required_keys": ["question_id", "question", "state"],
        "bounds": {
            "is_new_vs_wave0": "boolean — false if URL is in the Wave0 list above",
            "state": "resolved | targeted_search | deferred | requires_internal_data",
        },
    }
    return NodeExecutionRequest(
        objective=objective,
        expected_output=json.dumps(expected, sort_keys=True, separators=(",", ":")),
    )


def parse_wave1_worker_output(text: str) -> Wave1WorkerOutput:
    """Parse the worker run_agent summary into a validated Wave1WorkerOutput."""
    if not isinstance(text, str) or not text.strip():
        raise ValueError("wave1_worker_output_empty")
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError("wave1_worker_output_json_invalid") from exc
    if not isinstance(payload, dict):
        raise ValueError("wave1_worker_output_not_object")
    return Wave1WorkerOutput.model_validate(payload)
