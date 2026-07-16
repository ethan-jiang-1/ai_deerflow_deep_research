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
    compute_candidate_hash,
)
from deerflow_deep_research.engine.work_units.kernel import WorkIntent
from deerflow_deep_research.graph.components.work_units import (
    WorkUnitComponentResult,
    run_fixture_work_unit_component,
)

from .prompts import build_wave1_worker_prompt, parse_wave1_worker_output

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
) -> tuple[WorkIntent, ...]:
    """Build one real evidence WorkIntent per topic for deep extraction.

    @impl WON-001
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
    result = await capabilities.run_agent(context=capabilities, request=request)  # type: ignore[union-attr]
    if not isinstance(result, NodeExecutionResult) or result.finish_reason is not NodeFinishReason.SUCCESS:
        raise ValueError("wave1_worker_failed")
    output = parse_wave1_worker_output(result.summary)
    result_ref = result_path(spec.research_id, spec.work_id, attempt.attempt_id)
    source_refs = tuple(
        SourceRef(
            source_id=s.source_id,
            canonical_url=s.canonical_url,
            content_ref=s.content_ref,
            content_hash=s.content_hash,
            byte_count=s.byte_count,
        )
        for s in output.sources
    )
    candidate_hash = compute_candidate_hash(
        CandidateResult.model_validate(
            {
                "worker_role": spec.worker_role,
                "spec_hash": spec.spec_hash,
                "result_ref": result_ref,
                "source_refs": tuple(sr.model_dump(mode="python") for sr in source_refs),
                "output_refs": (),
                "candidate_hash": "",
            }
        )
    )
    return CandidateResult.model_validate(
        {
            "worker_role": spec.worker_role,
            "spec_hash": spec.spec_hash,
            "result_ref": result_ref,
            "source_refs": tuple(sr.model_dump(mode="python") for sr in source_refs),
            "output_refs": (),
            "candidate_hash": candidate_hash,
        }
    )


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
    clock: Callable[[], datetime],
    fault_hook: Callable[[str], None] | None = None,
) -> WorkUnitComponentResult:
    """Run real Wave1 evidence extraction through the shared work-unit component."""
    intents = materialize_wave1_intents(topic_registry)
    return await run_fixture_work_unit_component(
        state,
        logical_name="wave1",
        policy=PolicyRef(name="skeleton-wave1", version="v1"),
        controller=controller,
        intents=intents,
        clock=clock,
        fault_hook=fault_hook,
    )


__all__ = [
    "WAVE1_FIXTURE_INTENTS",
    "materialize_wave1_intents",
    "run_wave1_work_units",
    "run_wave1_work_units_real",
]
