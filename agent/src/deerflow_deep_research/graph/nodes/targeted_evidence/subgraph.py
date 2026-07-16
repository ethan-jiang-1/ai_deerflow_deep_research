"""Critic runners, dispatcher, and gap router for the targeted_evidence node.

@impl EVC-001, EVC-002, EVC-003
@impl TEL-001, TEL-002
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from typing import Any

from deerflow_deep_research.domain.critics import (
    ClaimVerifierResult,
    SourceDiagnosticResult,
)
from deerflow_deep_research.engine.fake_control import node_update
from deerflow_deep_research.graph.components.work_units import run_fixture_work_unit_component

from .prompts import build_claim_verifier_prompt, build_source_diagnostic_prompt


def _parse_json(text: str, label: str) -> dict[str, Any]:
    if not isinstance(text, str) or not text.strip():
        raise ValueError(f"{label}_empty")
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{label}_json_invalid") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"{label}_not_object")
    return payload


async def run_source_diagnostic(
    capabilities: object,
    node_attempt_id: str,
    research_id: str,
    source_refs: tuple[str, ...],
    source_contents: tuple[str, ...],
    workspace_root: str,
) -> SourceDiagnosticResult:
    request = build_source_diagnostic_prompt(source_refs, source_contents)
    result = await capabilities.run_agent(context=capabilities, request=request)  # type: ignore[union-attr]
    payload = _parse_json(result.summary, "source_diagnostic")
    return SourceDiagnosticResult.model_validate(payload)


async def run_claim_verifier(
    capabilities: object,
    node_attempt_id: str,
    research_id: str,
    claims: tuple[tuple[str, str], ...],
    evidence_refs: tuple[str, ...],
    workspace_root: str,
) -> ClaimVerifierResult:
    request = build_claim_verifier_prompt(claims, evidence_refs)
    result = await capabilities.run_agent(context=capabilities, request=request)  # type: ignore[union-attr]
    payload = _parse_json(result.summary, "claim_verifier")
    return ClaimVerifierResult.model_validate(payload)


async def dispatch_critic(
    work_items: Iterable[Mapping[str, Any]],
    capabilities: object,
    node_attempt_id: str,
    research_id: str,
    workspace_root: str,
) -> list[Mapping[str, Any]]:
    results: list[Mapping[str, Any]] = []
    for item in work_items:
        item_type = item.get("type")
        if item_type == "source_diagnostic":
            source_refs = tuple(item["source_refs"])
            source_contents = tuple(item.get("source_contents", ()))
            result = await run_source_diagnostic(
                capabilities, node_attempt_id, research_id, source_refs, source_contents, workspace_root
            )
            results.append({"type": "source_diagnostic", "result": result})
        elif item_type == "claim_verifier":
            claims = tuple((c[0], c[1]) for c in item["claims"])
            evidence_refs = tuple(item["evidence_refs"])
            result = await run_claim_verifier(
                capabilities, node_attempt_id, research_id, claims, evidence_refs, workspace_root
            )
            results.append({"type": "claim_verifier", "result": result})
        else:
            raise ValueError(f"unknown_critic_work_type: {item_type}")
    return results


async def run_gap_workers(state: dict, gap_intents: tuple, dependencies: Any) -> dict:
    """Run gap workers through the shared work-unit component.

    @impl TEL-001
    """
    from datetime import UTC, datetime

    from deerflow_deep_research.domain.node_spec import PolicyRef

    result = await run_fixture_work_unit_component(
        state,
        logical_name="targeted_evidence",
        policy=PolicyRef(name="skeleton-targeted-evidence", version="v1"),
        controller=dependencies.work_units,
        intents=gap_intents,
        clock=lambda: datetime.now(UTC),
    )
    return {**node_update("targeted_evidence"), **result.parent_update}


def materialize_gap_intents(
    gaps: tuple[dict, ...] | list[dict] | None,
) -> tuple:
    """Build one WorkIntent per search_required gap.

    @impl TEL-001
    """
    from deerflow_deep_research.engine.work_units.kernel import WorkIntent

    intents: list = []
    for gap in gaps or ():
        if not isinstance(gap, dict):
            continue
        if not gap.get("search_required", False):
            continue
        gap_id = gap.get("gap_id", "")
        if not gap_id:
            continue
        intents.append(
            WorkIntent(
                worker_role="targeted_worker",
                scope=(gap_id,),
                result_contract="targeted.source-intake",
                result_schema_version=1,
                required_outputs=(),
            )
        )
    return tuple(intents)
