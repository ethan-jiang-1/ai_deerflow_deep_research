"""Wave1 fixture and real subgraph over the shared work-unit component.

@impl WOU-001
@impl WOU-002
@impl WOU-003
@impl WOU-004
@impl REG-002
@impl WON-001
@impl WON-002
"""

from __future__ import annotations

import base64
import hashlib
from collections.abc import Callable, Mapping
from datetime import datetime
from typing import Any

from deerflow_deep_research.domain.bundle import result_path, source_content_path
from deerflow_deep_research.domain.context import NodeAgentContext, NodeExecutionResult
from deerflow_deep_research.domain.enums import NodeFinishReason
from deerflow_deep_research.domain.invocation import WorkUnitControllerDependencies
from deerflow_deep_research.domain.node_spec import PolicyRef
from deerflow_deep_research.domain.wave1 import Wave1SourceIntakeResult, Wave1SourceRef
from deerflow_deep_research.domain.work_units import (
    Attempt,
    CandidateResult,
    SourceRef,
    WorkSpec,
    canonical_json_bytes,
    compute_candidate_hash,
)
from deerflow_deep_research.engine.work_units.kernel import WorkIntent
from deerflow_deep_research.graph.components.work_units import (
    WorkUnitComponentResult,
    run_fixture_work_unit_component,
)

from .prompts import build_wave1_repair_prompt, build_wave1_worker_prompt, parse_wave1_worker_output

WAVE1_REAL_POLICY = PolicyRef(name="real-wave1", version="v1")

WAVE1_FIXTURE_INTENTS = tuple(
    WorkIntent(
        worker_role="fixture_worker",
        scope=(f"wave1:fixture:{index}",),
        result_contract="fixture.work-unit",
        result_schema_version=1,
        required_outputs=("fixture.json",),
    )
    for index in range(3)
)


def _content_hash(data: bytes) -> str:
    digest = hashlib.sha256(data).digest()
    return "h_" + base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def materialize_wave1_intents(
    topic_registry: Mapping[str, Any] | tuple[Mapping[str, Any], ...] | None,
    *,
    topic_filter: tuple[str, ...] | None = None,
) -> tuple[WorkIntent, ...]:
    """Build one real evidence WorkIntent per topic for deep extraction.

    When *topic_filter* is non-empty, only topics whose ``topic_id`` is in the
    filter set get a WorkIntent. This supports scoped rerun.

    @impl WON-001
    @impl REN-004
    """
    filter_set: frozenset[str] | None = frozenset(topic_filter) if topic_filter else None
    intents: list[WorkIntent] = []
    for entry in topic_registry or ():
        if not isinstance(entry, Mapping):
            continue
        topic_id = entry.get("topic_id")
        if not isinstance(topic_id, str) or not topic_id.strip():
            continue
        if filter_set is not None and topic_id not in filter_set:
            continue
        intents.append(
            WorkIntent(
                worker_role="wave1_extraction",
                scope=(topic_id,),
                result_contract="wave1.source-intake",
                result_schema_version=1,
                required_outputs=(),
            )
        )
    if not intents:
        raise ValueError("topic_registry_empty")
    return tuple(intents)


async def _wave1_worker(
    spec: WorkSpec,
    attempt: Attempt,
    *,
    capabilities: object,
    agent_context: NodeAgentContext,
    artifact_writer: object,
    topic_registry: tuple[dict, ...] | list[dict] | None,
    wave0_urls: frozenset[str],
) -> CandidateResult:
    """Real Wave1 worker: build prompt, run agent, parse output, build candidate."""
    topic = {}
    topic_id = spec.scope[0] if spec.scope else ""
    for entry in topic_registry or ():
        if isinstance(entry, dict) and entry.get("topic_id") == topic_id:
            topic = entry
            break
    request = build_wave1_worker_prompt(topic, wave0_urls)
    result = await capabilities.run_agent(context=agent_context, request=request)  # type: ignore[union-attr]
    if not isinstance(result, NodeExecutionResult) or result.finish_reason is not NodeFinishReason.SUCCESS:
        raise ValueError("wave1_worker_failed")
    try:
        output = parse_wave1_worker_output(result.summary)
    except ValueError as parse_error:
        repaired = await capabilities.run_agent(  # type: ignore[union-attr]
            context=agent_context,
            request=build_wave1_repair_prompt(result.summary, result.untrusted_tool_results),
        )
        if not isinstance(repaired, NodeExecutionResult) or repaired.finish_reason is not NodeFinishReason.SUCCESS:
            raise ValueError("wave1_worker_repair_failed") from parse_error
        output = parse_wave1_worker_output(repaired.summary)
    normalized_sources: list[Wave1SourceRef] = []
    source_refs: list[SourceRef] = []
    for index, source in enumerate(output.sources):
        cache_name = f"source-{index}.json"
        is_new_vs_wave0 = source.canonical_url not in wave0_urls
        content = canonical_json_bytes(
            {
                "source_id": source.source_id,
                "canonical_url": source.canonical_url,
                "title": source.title,
                "is_new_vs_wave0": is_new_vs_wave0,
            }
        )
        await artifact_writer.write_source(cache_name, content)  # type: ignore[union-attr]
        content_ref = source_content_path(spec.research_id, spec.work_id, attempt.attempt_id, cache_name)
        content_hash = _content_hash(content)
        normalized_sources.append(
            Wave1SourceRef(
                source_id=source.source_id,
                canonical_url=source.canonical_url,
                title=source.title,
                content_ref=content_ref,
                content_hash=content_hash,
                byte_count=len(content),
                is_new_vs_wave0=is_new_vs_wave0,
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

    document = Wave1SourceIntakeResult(
        schema_version=1,
        research_id=spec.research_id,
        generation=spec.generation,
        phase=spec.phase,
        work_id=spec.work_id,
        attempt_id=attempt.attempt_id,
        worker_role=spec.worker_role,
        spec_hash=spec.spec_hash,
        result_contract="wave1.source-intake",
        output_paths=spec.required_outputs,
        sources=tuple(normalized_sources),
        source_ids=tuple(source.source_id for source in normalized_sources),
        claims=output.claims,
        open_questions=output.open_questions,
    )
    result_bytes = canonical_json_bytes(document)
    await artifact_writer.write_result(document)  # type: ignore[union-attr]
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


async def run_wave1_work_units(
    state: Mapping[str, Any],
    *,
    controller: WorkUnitControllerDependencies,
    clock: Callable[[], datetime],
) -> WorkUnitComponentResult:
    return await run_fixture_work_unit_component(
        state,
        logical_name="wave1",
        policy=PolicyRef(name="skeleton-wave1", version="v1"),
        controller=controller,
        intents=WAVE1_FIXTURE_INTENTS,
        clock=clock,
    )


async def run_wave1_work_units_real(
    state: Mapping[str, Any],
    *,
    controller: WorkUnitControllerDependencies,
    topic_registry: tuple[dict, ...] | list[dict] | None,
    capabilities: object,
    wave0_urls: frozenset[str],
    topic_filter: tuple[str, ...] | None = None,
    clock: Callable[[], datetime],
    fault_hook: Callable[[str], None] | None = None,
) -> WorkUnitComponentResult:
    """Run real Wave1 evidence extraction through the shared work-unit component."""
    intents = materialize_wave1_intents(topic_registry, topic_filter=topic_filter)

    async def worker(spec: WorkSpec, attempt: Attempt) -> CandidateResult:
        resolved = await controller.resolver.resolve_worker(
            logical_name="wave1",
            work_spec=spec,
            attempt=attempt,
            policy=WAVE1_REAL_POLICY,
        )
        if resolved.artifact_writer is None:
            raise ValueError("wave1_artifact_writer_missing")
        return await _wave1_worker(
            spec,
            attempt,
            capabilities=resolved.node_dependencies.capabilities,
            agent_context=resolved.node_dependencies.agent_context,
            artifact_writer=resolved.artifact_writer,
            topic_registry=topic_registry,
            wave0_urls=wave0_urls,
        )

    return await run_fixture_work_unit_component(
        state,
        logical_name="wave1",
        policy=WAVE1_REAL_POLICY,
        controller=controller,
        intents=intents,
        clock=clock,
        fault_hook=fault_hook,
        worker=worker,
    )


__all__ = [
    "WAVE1_FIXTURE_INTENTS",
    "WAVE1_REAL_POLICY",
    "materialize_wave1_intents",
    "run_wave1_work_units",
    "run_wave1_work_units_real",
]
