"""Critic runners, dispatcher, and gap router for the targeted_evidence node.

@impl EVC-001, EVC-002, EVC-003
@impl TEL-001, TEL-002
"""

from __future__ import annotations

import base64
import hashlib
import json
from collections.abc import Iterable, Mapping
from typing import Any

from deerflow_deep_research.domain.bundle import result_path, source_content_path
from deerflow_deep_research.domain.context import NodeAgentContext, NodeExecutionResult
from deerflow_deep_research.domain.critics import (
    ClaimVerifierResult,
    SourceDiagnosticResult,
)
from deerflow_deep_research.domain.enums import NodeFinishReason
from deerflow_deep_research.domain.node_spec import PolicyRef
from deerflow_deep_research.domain.targeted import TargetedSourceIntakeResult, TargetedSourceMeta
from deerflow_deep_research.domain.work_units import (
    Attempt,
    CandidateResult,
    SourceRef,
    WorkSpec,
    canonical_json_bytes,
    compute_candidate_hash,
)
from deerflow_deep_research.engine.fake_control import node_update
from deerflow_deep_research.graph.components.work_units import run_fixture_work_unit_component

from .prompts import (
    build_claim_verifier_prompt,
    build_source_diagnostic_prompt,
    build_targeted_worker_prompt,
    parse_targeted_worker_output,
)

TARGETED_REAL_POLICY = PolicyRef(name="real-targeted-evidence", version="v1")


def _content_hash(data: bytes) -> str:
    digest = hashlib.sha256(data).digest()
    return "h_" + base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


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
    agent_context: NodeAgentContext,
    node_attempt_id: str,
    research_id: str,
    source_refs: tuple[str, ...],
    source_contents: tuple[str, ...],
    workspace_root: str,
) -> SourceDiagnosticResult:
    request = build_source_diagnostic_prompt(source_refs, source_contents)
    result = await capabilities.run_agent(context=agent_context, request=request)  # type: ignore[union-attr]
    payload = _parse_json(result.summary, "source_diagnostic")
    return SourceDiagnosticResult.model_validate(payload)


async def run_claim_verifier(
    capabilities: object,
    agent_context: NodeAgentContext,
    node_attempt_id: str,
    research_id: str,
    claims: tuple[tuple[str, str], ...],
    evidence_refs: tuple[str, ...],
    workspace_root: str,
) -> ClaimVerifierResult:
    request = build_claim_verifier_prompt(claims, evidence_refs)
    result = await capabilities.run_agent(context=agent_context, request=request)  # type: ignore[union-attr]
    payload = _parse_json(result.summary, "claim_verifier")
    return ClaimVerifierResult.model_validate(payload)


async def dispatch_critic(
    work_items: Iterable[Mapping[str, Any]],
    capabilities: object,
    agent_context: NodeAgentContext,
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
                capabilities, agent_context, node_attempt_id, research_id, source_refs, source_contents, workspace_root
            )
            results.append({"type": "source_diagnostic", "result": result})
        elif item_type == "claim_verifier":
            claims = tuple((c[0], c[1]) for c in item["claims"])
            evidence_refs = tuple(item["evidence_refs"])
            result = await run_claim_verifier(
                capabilities, agent_context, node_attempt_id, research_id, claims, evidence_refs, workspace_root
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

    controller = dependencies.work_units
    if controller is None:
        raise ValueError("work_unit_capability_missing")

    async def worker(spec: WorkSpec, attempt: Attempt) -> CandidateResult:
        resolved = await controller.resolver.resolve_worker(
            logical_name="targeted_evidence",
            work_spec=spec,
            attempt=attempt,
            policy=TARGETED_REAL_POLICY,
        )
        writer = resolved.artifact_writer
        if writer is None:
            raise ValueError("targeted_artifact_writer_missing")
        result = await resolved.node_dependencies.capabilities.run_agent(
            context=resolved.node_dependencies.agent_context,
            request=build_targeted_worker_prompt(spec.scope[0]),
        )
        if not isinstance(result, NodeExecutionResult) or result.finish_reason is not NodeFinishReason.SUCCESS:
            raise ValueError("targeted_worker_failed")
        output = parse_targeted_worker_output(result.summary)
        if output.gap_id != spec.scope[0]:
            raise ValueError("targeted_gap_identity_mismatch")

        metas: list[TargetedSourceMeta] = []
        source_refs: list[SourceRef] = []
        for index, source in enumerate(output.sources):
            cache_name = f"source-{index}.json"
            content = canonical_json_bytes(source)
            await writer.write_source(cache_name, content)
            content_ref = source_content_path(spec.research_id, spec.work_id, attempt.attempt_id, cache_name)
            content_hash = _content_hash(content)
            metas.append(
                TargetedSourceMeta(
                    source_id=source.source_id,
                    canonical_url=source.canonical_url,
                    title=source.title,
                    content_ref=content_ref,
                )
            )
            source_refs.append(
                SourceRef(
                    source_id=source.source_id,
                    canonical_url=source.canonical_url,
                    content_ref=content_ref,
                    content_hash=content_hash,
                    byte_count=len(content),
                )
            )
        document = TargetedSourceIntakeResult(
            schema_version=1,
            research_id=spec.research_id,
            generation=spec.generation,
            phase=spec.phase,
            work_id=spec.work_id,
            attempt_id=attempt.attempt_id,
            worker_role=spec.worker_role,
            spec_hash=spec.spec_hash,
            result_contract="targeted.source-intake",
            output_paths=spec.required_outputs,
            source_ids=tuple(meta.source_id for meta in metas),
            sources=tuple(metas),
            gap_id=output.gap_id,
            gap_status=output.gap_status,
            limitations=output.limitations,
        )
        result_bytes = canonical_json_bytes(document)
        await writer.write_result(document)
        payload: dict[str, Any] = {
            "schema_version": 1,
            "research_id": spec.research_id,
            "generation": spec.generation,
            "phase": spec.phase,
            "work_id": spec.work_id,
            "attempt_id": attempt.attempt_id,
            "worker_role": spec.worker_role,
            "spec_hash": spec.spec_hash,
            "result_contract": spec.result_contract,
            "result_ref": result_path(spec.research_id, spec.work_id, attempt.attempt_id),
            "result_hash": _content_hash(result_bytes),
            "result_schema_version": spec.result_schema_version,
            "result_byte_count": len(result_bytes),
            "output_refs": (),
            "source_refs": tuple(source_refs),
        }
        payload["candidate_hash"] = compute_candidate_hash(payload)
        return CandidateResult.model_validate(payload)

    result = await run_fixture_work_unit_component(
        state,
        logical_name="targeted_evidence",
        policy=TARGETED_REAL_POLICY,
        controller=controller,
        intents=gap_intents,
        clock=lambda: datetime.now(UTC),
        worker=worker,
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
