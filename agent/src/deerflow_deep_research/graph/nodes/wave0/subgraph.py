"""Wave0 fixture recipe over the shared work-unit component.

@impl WOU-001
@impl WOU-002
@impl WOU-003
@impl WOU-004
@impl REG-002
"""

from __future__ import annotations

import base64
import hashlib
from collections.abc import Callable, Mapping
from datetime import datetime
from typing import Any

from deerflow_deep_research.domain.bundle import result_path
from deerflow_deep_research.domain.context import NodeExecutionResult
from deerflow_deep_research.domain.enums import NodeFinishReason
from deerflow_deep_research.domain.invocation import WorkUnitControllerDependencies
from deerflow_deep_research.domain.node_spec import PolicyRef
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

from .prompts import (
    build_wave0_result_document,
    build_wave0_worker_prompt,
    parse_wave0_worker_output,
)

WAVE0_REAL_POLICY = PolicyRef(name="real-wave0", version="v1")


def _content_hash(data: bytes) -> str:
    digest = hashlib.sha256(data).digest()
    return "h_" + base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")

WAVE0_FIXTURE_INTENTS = tuple(
    WorkIntent(
        worker_role="fixture_worker",
        scope=(f"wave0:fixture:{index}",),
        result_contract="fixture.work-unit",
        result_schema_version=1,
        required_outputs=("fixture.json",),
    )
    for index in range(3)
)


def materialize_wave0_intents(
    topic_registry: Mapping[str, Any] | tuple[Mapping[str, Any], ...] | None,
) -> tuple[WorkIntent, ...]:
    """Build one real source-intake ``WorkIntent`` per topic in the planner registry.

    @impl WAN-001
    """
    intents: list[WorkIntent] = []
    for entry in topic_registry or ():
        if not isinstance(entry, Mapping):
            continue
        topic_id = entry.get("topic_id")
        if not isinstance(topic_id, str) or not topic_id.strip():
            continue
        intents.append(
            WorkIntent(
                worker_role="wave0_intake",
                scope=(topic_id,),
                result_contract="wave0.source-intake",
                result_schema_version=1,
                required_outputs=(),
            )
        )
    if not intents:
        raise ValueError("topic_registry_empty")
    return tuple(intents)


async def run_wave0_work_units(
    state: Mapping[str, Any],
    *,
    controller: WorkUnitControllerDependencies,
    clock: Callable[[], datetime],
    fault_hook: Callable[[str], None] | None = None,
) -> WorkUnitComponentResult:
    return await run_fixture_work_unit_component(
        state,
        logical_name="wave0",
        policy=PolicyRef(name="skeleton-wave0", version="v1"),
        controller=controller,
        intents=WAVE0_FIXTURE_INTENTS,
        clock=clock,
        fault_hook=fault_hook,
    )


async def run_wave0_work_units_real(
    state: Mapping[str, Any],
    *,
    controller: WorkUnitControllerDependencies,
    topic_registry: Mapping[str, Any] | tuple[Mapping[str, Any], ...] | None,
    clock: Callable[[], datetime],
    fault_hook: Callable[[str], None] | None = None,
) -> WorkUnitComponentResult:
    """Run real Wave0 source intake: one worker per topic through the bridge.

    @impl WAN-001
    @impl WAN-002
    """
    intents = materialize_wave0_intents(topic_registry)

    async def worker(spec: WorkSpec, attempt: Attempt) -> CandidateResult:
        resolved = await controller.resolver.resolve_worker(
            logical_name="wave0",
            work_spec=spec,
            attempt=attempt,
            policy=WAVE0_REAL_POLICY,
        )
        writer = resolved.artifact_writer
        if writer is None:
            raise ValueError("wave0_artifact_writer_missing")
        capabilities = resolved.node_dependencies.capabilities
        result = await capabilities.run_agent(
            context=resolved.node_dependencies.agent_context,
            request=build_wave0_worker_prompt(spec, topic_registry),
        )
        if not isinstance(result, NodeExecutionResult) or result.finish_reason is not NodeFinishReason.SUCCESS:
            raise ValueError("wave0_worker_failed")
        output = parse_wave0_worker_output(result.summary)
        document = build_wave0_result_document(spec, attempt, output)
        result_bytes = canonical_json_bytes(document)
        await writer.write_result(document)
        source_refs = tuple(
            SourceRef(
                source_id=source.source_id,
                canonical_url=source.canonical_url,
                content_ref=source.content_ref,
                content_hash=source.content_hash,
                byte_count=source.byte_count,
            )
            for source in output.sources
        )
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
            "source_refs": source_refs,
        }
        payload["candidate_hash"] = compute_candidate_hash(payload)
        return CandidateResult.model_validate(payload)

    return await run_fixture_work_unit_component(
        state,
        logical_name="wave0",
        policy=WAVE0_REAL_POLICY,
        controller=controller,
        intents=intents,
        clock=clock,
        fault_hook=fault_hook,
        worker=worker,
    )


__all__ = [
    "WAVE0_FIXTURE_INTENTS",
    "WAVE0_REAL_POLICY",
    "materialize_wave0_intents",
    "run_wave0_work_units",
    "run_wave0_work_units_real",
]
