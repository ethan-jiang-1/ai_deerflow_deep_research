from __future__ import annotations

import base64
import hashlib
import time
from dataclasses import replace
from datetime import UTC, datetime

import pytest

from deerflow_deep_research.domain.context import GraphContextView, NodeAgentContext
from deerflow_deep_research.domain.invocation import (
    WorkUnitControllerDependencies,
    WorkUnitWorkerDependencies,
)
from deerflow_deep_research.domain.node_spec import NodeBuildDependencies, PolicyRef
from deerflow_deep_research.domain.work_units import (
    CandidateResult,
    FixtureResultDocument,
    OutputRef,
    canonical_json_bytes,
    compute_candidate_hash,
)
from deerflow_deep_research.engine.work_units.kernel import allocate_attempt, materialize_work_spec
from deerflow_deep_research.graph.components.work_units import submit_candidate_if_active
from deerflow_deep_research.graph.nodes.wave0.subgraph import WAVE0_FIXTURE_INTENTS, run_wave0_work_units
from deerflow_deep_research.runtime.projection import RuntimeWorkUnitDependencyResolver
from deerflow_deep_research.runtime.work_unit_store import WorkUnitStore

RESEARCH_ID = "r_" + "S" * 43
NOW = datetime(2026, 7, 14, tzinfo=UTC)


def _hash(data: bytes) -> str:
    return "h_" + base64.urlsafe_b64encode(hashlib.sha256(data).digest()).decode("ascii").rstrip("=")


class ForbiddenCapabilities:
    async def run_agent(self, *, context, request):
        raise AssertionError("unused")


class BaseResolver:
    def __init__(self, graph_context: GraphContextView) -> None:
        self._graph_context = graph_context

    def resolve(self, *, logical_name, attempt_id, policy):
        return NodeBuildDependencies(
            graph_context=self._graph_context,
            agent_context=NodeAgentContext(
                research_scope_id=RESEARCH_ID,
                node_name=logical_name,
                attempt_id=attempt_id,
                workspace_root=self._graph_context.workspace_root,
                attempt_root=f"{self._graph_context.workspace_root}/attempts/{attempt_id}",
                policy_name=policy.name,
            ),
            capabilities=ForbiddenCapabilities(),
        )


def _controller(tmp_path) -> tuple[WorkUnitControllerDependencies, WorkUnitStore]:
    graph = GraphContextView(
        research_scope_id=RESEARCH_ID,
        workspace_root=f"/mnt/user-data/workspace/deep-research/{RESEARCH_ID}",
        uploads_root="/mnt/user-data/uploads",
        outputs_root=f"/mnt/user-data/outputs/deep-research/{RESEARCH_ID}",
    )
    base = BaseResolver(graph)
    store = WorkUnitStore(
        workspace_host_path=tmp_path,
        research_id=RESEARCH_ID,
        clock=lambda: NOW,
        monotonic=time.monotonic,
        lock_sleep=time.sleep,
        token_factory=lambda: "3" * 32,
        fault_hook=None,
    )
    return (
        WorkUnitControllerDependencies(
            store=store,
            resolver=RuntimeWorkUnitDependencyResolver(graph, base, store),
        ),
        store,
    )


class _OmitResultWriter:
    def __init__(self, delegate) -> None:
        self._delegate = delegate

    async def write_result(self, document) -> None:
        return None

    async def write_output(self, relative_path, content) -> None:
        await self._delegate.write_output(relative_path, content)


class _OmitResultResolver:
    def __init__(self, delegate) -> None:
        self._delegate = delegate

    async def resolve_worker(self, **kwargs) -> WorkUnitWorkerDependencies:
        resolved = await self._delegate.resolve_worker(**kwargs)
        assert resolved.artifact_writer is not None
        return replace(resolved, artifact_writer=_OmitResultWriter(resolved.artifact_writer))


async def test_worker_completion_without_result_fails_through_real_component_before_ledger(tmp_path) -> None:
    controller, store = _controller(tmp_path)
    controller = WorkUnitControllerDependencies(
        store=controller.store,
        resolver=_OmitResultResolver(controller.resolver),
    )
    state = {"research_id": RESEARCH_ID, "generation": 0}
    with pytest.raises(ValueError, match="submission_validation_failed:artifact_missing"):
        await run_wave0_work_units(state, controller=controller, clock=lambda: NOW)
    assert await store.load_records() == ()


async def _valid_boundary_fixture(controller: WorkUnitControllerDependencies):
    spec = materialize_work_spec(
        research_id=RESEARCH_ID,
        generation=0,
        phase="wave0",
        work_ordinal=0,
        intent=WAVE0_FIXTURE_INTENTS[0],
    )
    attempt = allocate_attempt(spec, attempt_ordinal=0, created_at=NOW)
    resolved = await controller.resolver.resolve_worker(
        logical_name="wave0",
        work_spec=spec,
        attempt=attempt,
        policy=PolicyRef("skeleton-wave0", "v1"),
    )
    assert resolved.artifact_writer is not None
    output = b'{"fixture":true}'
    await resolved.artifact_writer.write_output("fixture.json", output)
    document = FixtureResultDocument(
        schema_version=1,
        research_id=spec.research_id,
        generation=spec.generation,
        phase=spec.phase,
        work_id=spec.work_id,
        attempt_id=attempt.attempt_id,
        worker_role=spec.worker_role,
        spec_hash=spec.spec_hash,
        result_contract="fixture.work-unit",
        fixture_marker="non_research_fixture",
        output_paths=spec.required_outputs,
        source_ids=(),
    )
    result = canonical_json_bytes(document)
    await resolved.artifact_writer.write_result(document)
    root = f"workspace/deep-research/{RESEARCH_ID}/work/{spec.work_id}/{attempt.attempt_id}"
    payload = {
        "schema_version": 1,
        "research_id": RESEARCH_ID,
        "generation": 0,
        "phase": "wave0",
        "work_id": spec.work_id,
        "attempt_id": attempt.attempt_id,
        "worker_role": spec.worker_role,
        "spec_hash": spec.spec_hash,
        "result_contract": spec.result_contract,
        "result_ref": f"{root}/result.json",
        "result_hash": _hash(result),
        "result_schema_version": 1,
        "result_byte_count": len(result),
        "output_refs": (
            OutputRef(
                path=f"{root}/outputs/fixture.json",
                content_hash=_hash(output),
                schema_version=1,
                byte_count=len(output),
            ),
        ),
        "source_refs": (),
    }
    payload["candidate_hash"] = compute_candidate_hash(payload)
    candidate = CandidateResult.model_validate(payload)
    return spec, attempt, candidate


async def test_wrong_identity_out_of_root_and_hash_mismatch_fail_real_submit_boundary(tmp_path) -> None:
    controller, store = _controller(tmp_path)
    spec, attempt, candidate = await _valid_boundary_fixture(controller)
    payload = candidate.__dict__

    wrong_identity = CandidateResult.model_construct(**{**payload, "worker_role": "other_worker"})
    with pytest.raises(ValueError, match="submission_validation_failed:identity_mismatch"):
        await submit_candidate_if_active(
            controller,
            spec=spec,
            attempt=attempt,
            candidate=wrong_identity,
            active_attempt_id=attempt.attempt_id,
            now=NOW,
        )

    out_of_root = CandidateResult.model_construct(
        **{**payload, "result_ref": f"workspace/deep-research/{RESEARCH_ID}/evidence/result.json"}
    )
    with pytest.raises(ValueError, match="path_not_canonical"):
        await submit_candidate_if_active(
            controller,
            spec=spec,
            attempt=attempt,
            candidate=out_of_root,
            active_attempt_id=attempt.attempt_id,
            now=NOW,
        )

    bad_hash = CandidateResult.model_construct(**{**payload, "result_hash": "h_" + "Z" * 43})
    with pytest.raises(ValueError, match="content_hash_mismatch"):
        await submit_candidate_if_active(
            controller,
            spec=spec,
            attempt=attempt,
            candidate=bad_hash,
            active_attempt_id=attempt.attempt_id,
            now=NOW,
        )
    assert await store.load_records() == ()


async def test_same_hash_replays_and_different_hash_conflicts_at_real_store_boundary(tmp_path) -> None:
    controller, store = _controller(tmp_path)
    spec, attempt, candidate = await _valid_boundary_fixture(controller)
    first = await submit_candidate_if_active(
        controller,
        spec=spec,
        attempt=attempt,
        candidate=candidate,
        active_attempt_id=attempt.attempt_id,
        now=NOW,
    )
    replay = await submit_candidate_if_active(
        controller,
        spec=spec,
        attempt=attempt,
        candidate=candidate,
        active_attempt_id=attempt.attempt_id,
        now=NOW,
    )
    assert replay.record_hash == first.record_hash

    divergent_payload = candidate.model_dump(mode="python")
    divergent_payload["result_hash"] = "h_" + "Y" * 43
    divergent_payload["candidate_hash"] = compute_candidate_hash(divergent_payload)
    divergent = CandidateResult.model_validate(divergent_payload)
    with pytest.raises(ValueError, match="candidate_conflict"):
        await store.commit_candidate(divergent, scope=spec.scope)
    assert len(await store.load_records()) == 1
