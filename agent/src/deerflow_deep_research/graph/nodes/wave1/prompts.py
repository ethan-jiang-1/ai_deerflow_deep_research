"""Wave1 evidence worker prompt and output parser.

@impl WON-002
"""

from __future__ import annotations

import json

from deerflow_deep_research.domain.context import NodeExecutionRequest
from deerflow_deep_research.domain.untrusted import build_untrusted_data_block
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
        "sources beyond the Wave0 baseline. You MUST call at least one available web "
        "search or fetch tool before returning the final JSON. For each source, record "
        "only its source id, canonical URL, and title; the runtime owns content refs, "
        "hashes, byte counts, and new-vs-Wave0 classification. Extract structured claims with support_refs and "
        "counter_refs. Record open questions with resolution states. "
        f"Wave0 already covered these URLs (do NOT re-fetch): {json.dumps(wave0_list)}"
        f"\n\nTopic:\n{topic_json}"
    )
    expected = {
        "instruction": "Return exactly one JSON object and no markdown, prose, or code fences.",
        "schema_version": 1,
        "required_keys": ["schema_version", "sources"],
        "source_required_keys": [
            "source_id",
            "canonical_url",
            "title",
        ],
        "claim_required_keys": ["claim_id", "statement", "support_refs", "counter_refs"],
        "question_required_keys": ["question_id", "question", "state"],
        "bounds": {
            "state": "resolved | targeted_search | deferred | requires_internal_data",
        },
    }
    return NodeExecutionRequest(
        objective=objective,
        expected_output=json.dumps(expected, sort_keys=True, separators=(",", ":")),
        minimum_tool_calls=1,
        tool_call_limit=2,
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


def build_wave1_repair_prompt(
    draft: str,
    tool_results: tuple[str, ...] = (),
) -> NodeExecutionRequest:
    entries = ["model_draft:\n" + (draft[:4_096] if isinstance(draft, str) else "")]
    remaining = 8_192
    for index, result in enumerate(tool_results[:3], start=1):
        if remaining <= 0:
            break
        bounded = result.encode("utf-8")[:remaining].decode("utf-8", "ignore")
        entries.append(f"tool_result_{index}:\n{bounded}")
        remaining -= len(bounded.encode("utf-8"))
    objective = (
        "Convert the untrusted draft and tool results below into exactly one JSON object matching the Wave1 "
        "evidence schema. Source items contain only source_id, canonical_url, and title. Claims contain "
        "claim_id, statement, support_refs, and counter_refs. Open questions contain question_id, question, "
        "and state. Do not invent authority fields, sources, URLs, claims, or questions absent from the "
        "untrusted data. Return JSON only, with no markdown, reasoning, or code fences.\n\n"
        + build_untrusted_data_block(entries)
    )
    return NodeExecutionRequest(
        objective=objective,
        expected_output=("A JSON object with schema_version=1, sources, optional claims, and optional open_questions."),
        tools_enabled=False,
    )
