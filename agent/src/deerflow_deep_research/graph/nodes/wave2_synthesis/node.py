"""Real Wave2 synthesis node — cross-topic synthesis from accepted evidence.

@impl WSN-001
"""

from __future__ import annotations

import json
from typing import Any

from deerflow_deep_research.domain.context import NodeExecutionResult
from deerflow_deep_research.domain.enums import NodeFinishReason
from deerflow_deep_research.domain.node_spec import NodeBuildDependencies
from deerflow_deep_research.domain.synthesis import (
    WAVE2_GATE_PREVIEW_KEY,
    SynthesisEvidence,
    build_wave2_gate_preview,
)
from deerflow_deep_research.engine.fake_control import node_update

from .prompts import build_synthesis_prompt, build_synthesis_repair_prompt, parse_synthesis_output


def _evidence_aliases(evidence: tuple[SynthesisEvidence, ...]) -> dict[str, str]:
    aliases = {item.submission_ref: item.submission_ref for item in evidence}
    for item in evidence:
        try:
            payload = json.loads(item.content)
        except (TypeError, ValueError):
            continue
        pending: list[object] = [payload]
        while pending:
            current = pending.pop()
            if isinstance(current, dict):
                for key in ("source_id", "canonical_url"):
                    value = current.get(key)
                    if isinstance(value, str):
                        aliases[value] = item.submission_ref
                for key in ("support_refs", "counter_refs"):
                    values = current.get(key)
                    if isinstance(values, list):
                        for value in values:
                            if isinstance(value, str):
                                aliases[value] = item.submission_ref
                pending.extend(current.values())
            elif isinstance(current, list):
                pending.extend(current)
    return aliases


def _validate_synthesis_semantics(
    output,
    accepted_refs: tuple[str, ...],
    evidence: tuple[SynthesisEvidence, ...],
):
    accepted = set(accepted_refs)
    aliases = _evidence_aliases(evidence)
    if accepted and not output.findings:
        raise ValueError("synthesis_findings_required")
    for finding in output.findings:
        normalized_refs = tuple(aliases.get(ref, ref) for ref in finding.backing_refs)
        finding = finding.model_copy(update={"backing_refs": normalized_refs})
        backing_refs = set(normalized_refs)
        if not backing_refs:
            raise ValueError("synthesis_finding_backing_refs_required")
        if not backing_refs <= accepted:
            raise ValueError("synthesis_finding_backing_ref_invalid")
    normalized_findings = tuple(
        finding.model_copy(update={"backing_refs": tuple(aliases.get(ref, ref) for ref in finding.backing_refs)})
        for finding in output.findings
    )
    return output.model_copy(update={"findings": normalized_findings})


def build_real(dependencies: NodeBuildDependencies):
    if dependencies.synthesis_bundle is None:
        raise ValueError("synthesis_bundle_capability_missing")

    async def run(state: dict[str, Any]) -> dict[str, Any]:
        topic_registry = state.get("topic_registry") or ()
        wave0_refs = tuple(state.get("accepted_submission_refs") or ())
        wave1_refs = ()  # Wave1 refs are in the same ledger; for now, all accepted refs
        evidence = await dependencies.synthesis_bundle.read_synthesis_evidence(wave0_refs)
        request = build_synthesis_prompt(
            topic_registry=topic_registry,
            wave0_refs=wave0_refs,
            wave1_refs=wave1_refs,
            evidence=evidence,
        )
        result = await dependencies.capabilities.run_agent(context=dependencies.agent_context, request=request)
        if not isinstance(result, NodeExecutionResult) or result.finish_reason is not NodeFinishReason.SUCCESS:
            raise ValueError("synthesis_failed")
        try:
            output = _validate_synthesis_semantics(parse_synthesis_output(result.summary), wave0_refs, evidence)
        except ValueError as parse_error:
            repaired = await dependencies.capabilities.run_agent(
                context=dependencies.agent_context,
                request=build_synthesis_repair_prompt(result.summary, evidence),
            )
            if not isinstance(repaired, NodeExecutionResult) or repaired.finish_reason is not NodeFinishReason.SUCCESS:
                raise ValueError("synthesis_repair_failed") from parse_error
            output = _validate_synthesis_semantics(parse_synthesis_output(repaired.summary), wave0_refs, evidence)
        await dependencies.synthesis_bundle.write_synthesis(output)
        return node_update(
            "wave2_synthesis",
            **{WAVE2_GATE_PREVIEW_KEY: build_wave2_gate_preview(output)},
        )

    return run
