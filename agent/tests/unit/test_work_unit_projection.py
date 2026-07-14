from __future__ import annotations

from datetime import UTC, datetime

import pytest

from deerflow_deep_research.domain.context import GraphContextView
from deerflow_deep_research.domain.work_units import Attempt, WorkSpec, compute_work_spec_hash
from deerflow_deep_research.runtime.projection import ProjectionError, project_work_unit_agent

RESEARCH_ID = "r_" + "A" * 43
WORK_ID = "g0_wave0_w0000"
ATTEMPT_ID = f"{WORK_ID}_a00"


def _spec(**overrides: object) -> WorkSpec:
    payload: dict[str, object] = {
        "schema_version": 1,
        "research_id": RESEARCH_ID,
        "generation": 0,
        "phase": "wave0",
        "work_id": WORK_ID,
        "work_ordinal": 0,
        "worker_role": "fixture_worker",
        "scope": ("alpha",),
        "result_contract": "fixture.work-unit",
        "result_schema_version": 1,
        "required_outputs": (),
    }
    payload.update(overrides)
    payload["spec_hash"] = compute_work_spec_hash(payload)
    return WorkSpec.model_validate(payload)


def _attempt(spec: WorkSpec | None = None, **overrides: object) -> Attempt:
    spec = spec or _spec()
    payload: dict[str, object] = {
        "schema_version": 1,
        "research_id": spec.research_id,
        "generation": spec.generation,
        "phase": spec.phase,
        "work_id": spec.work_id,
        "attempt_id": ATTEMPT_ID,
        "attempt_ordinal": 0,
        "spec_hash": spec.spec_hash,
        "status": "pending",
        "created_at": datetime(2026, 7, 14, tzinfo=UTC),
        "started_at": None,
        "expires_at": None,
        "terminal_at": None,
        "terminal_code": None,
    }
    payload.update(overrides)
    return Attempt.model_validate(payload)


def _graph_context(scope_id: str = RESEARCH_ID) -> GraphContextView:
    return GraphContextView(
        research_scope_id=scope_id,
        workspace_root=f"/mnt/user-data/workspace/deep-research/{scope_id}",
        uploads_root="/mnt/user-data/uploads",
        outputs_root=f"/mnt/user-data/outputs/deep-research/{scope_id}",
    )


def test_project_work_unit_agent_derives_exact_attempt_root() -> None:
    spec = _spec()
    attempt = _attempt(spec)
    context = project_work_unit_agent(
        _graph_context(),
        node_name="wave0",
        work_spec=spec,
        attempt=attempt,
        policy_name="wave0-policy",
    )
    assert context.node_name == "wave0"
    assert context.attempt_id == ATTEMPT_ID
    assert context.attempt_root == f"/mnt/user-data/workspace/deep-research/{RESEARCH_ID}/work/{WORK_ID}/{ATTEMPT_ID}"


def test_projection_rejects_graph_scope_mismatch() -> None:
    spec = _spec()
    with pytest.raises(ProjectionError, match="research_scope_mismatch"):
        project_work_unit_agent(
            _graph_context("r_" + "B" * 43),
            node_name="wave0",
            work_spec=spec,
            attempt=_attempt(spec),
            policy_name="wave0-policy",
        )


def test_projection_rejects_work_attempt_identity_or_spec_mismatch() -> None:
    spec = _spec()
    other_spec = _spec(work_id="g0_wave0_w0001", work_ordinal=1)
    with pytest.raises(ProjectionError, match="work_attempt_mismatch"):
        project_work_unit_agent(
            _graph_context(),
            node_name="wave0",
            work_spec=other_spec,
            attempt=_attempt(spec),
            policy_name="wave0-policy",
        )

    with pytest.raises(ProjectionError, match="work_attempt_mismatch"):
        project_work_unit_agent(
            _graph_context(),
            node_name="wave0",
            work_spec=spec,
            attempt=_attempt(spec, spec_hash="h_" + "Z" * 43),
            policy_name="wave0-policy",
        )


def test_projection_rejects_terminal_attempt_and_malformed_node_or_policy() -> None:
    spec = _spec()
    terminal = _attempt(
        spec,
        status="failed",
        started_at=datetime(2026, 7, 14, tzinfo=UTC),
        terminal_at=datetime(2026, 7, 14, tzinfo=UTC),
        terminal_code="worker_failed",
    )
    with pytest.raises(ProjectionError, match="attempt_not_active"):
        project_work_unit_agent(
            _graph_context(),
            node_name="wave0",
            work_spec=spec,
            attempt=terminal,
            policy_name="wave0-policy",
        )
    with pytest.raises(ProjectionError, match="node_name_invalid"):
        project_work_unit_agent(
            _graph_context(),
            node_name="Wave 0",
            work_spec=spec,
            attempt=_attempt(spec),
            policy_name="wave0-policy",
        )
    with pytest.raises(ProjectionError, match="policy_name_invalid"):
        project_work_unit_agent(
            _graph_context(),
            node_name="wave0",
            work_spec=spec,
            attempt=_attempt(spec),
            policy_name="Wave 0 Policy",
        )


def test_projection_rejects_malformed_constructed_work_or_attempt_ids() -> None:
    spec = _spec()
    malformed_spec = spec.model_copy(update={"work_id": "../work"})
    with pytest.raises(ProjectionError, match="work_id_invalid"):
        project_work_unit_agent(
            _graph_context(),
            node_name="wave0",
            work_spec=malformed_spec,
            attempt=_attempt(spec),
            policy_name="wave0-policy",
        )

    attempt = _attempt(spec)
    malformed_attempt = attempt.model_copy(update={"attempt_id": "../attempt"})
    with pytest.raises(ProjectionError, match="attempt_id_invalid"):
        project_work_unit_agent(
            _graph_context(),
            node_name="wave0",
            work_spec=spec,
            attempt=malformed_attempt,
            policy_name="wave0-policy",
        )


def test_projection_api_has_no_caller_selected_root() -> None:
    spec = _spec()
    with pytest.raises(TypeError):
        project_work_unit_agent(
            _graph_context(),
            node_name="wave0",
            work_spec=spec,
            attempt=_attempt(spec),
            policy_name="wave0-policy",
            attempt_root="/tmp/escape",  # type: ignore[call-arg]
        )
