"""Runtime projection purity and non-leakage contract (RUI-002)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from deerflow_deep_research.domain.context import (
    GraphContextView,
    NodeAgentContext,
    NodeExecutionRequest,
    NodeExecutionResult,
)
from deerflow_deep_research.domain.enums import NodeFinishReason
from deerflow_deep_research.domain.node_spec import NodeBuildDependencies
from deerflow_deep_research.runtime.projection import (
    ProjectionError,
    build_node_dependencies,
    project_node_agent,
    project_research_scope,
)
from deerflow_deep_research.runtime.runtime_adapter import TrustedRuntimeEnvelope

HOST_MARKER = "/srv/users/alice/threads/thread-1"


class FakeCapabilities:
    async def run_agent(
        self,
        *,
        context: NodeAgentContext,
        request: NodeExecutionRequest,
    ) -> NodeExecutionResult:
        return NodeExecutionResult(finish_reason=NodeFinishReason.SUCCESS)


def _envelope() -> TrustedRuntimeEnvelope:
    from pathlib import Path

    return TrustedRuntimeEnvelope(
        effective_user_id="alice",
        outer_thread_id="thread-1",
        outer_run_id="run-1",
        app_config=object(),
        workspace_host_path=Path(HOST_MARKER) / "workspace",
        uploads_host_path=Path(HOST_MARKER) / "uploads",
        outputs_host_path=Path(HOST_MARKER) / "outputs",
        workspace_virtual_root="/mnt/user-data/workspace",
        uploads_virtual_root="/mnt/user-data/uploads",
        outputs_virtual_root="/mnt/user-data/outputs",
        parent_sandbox=object(),
        progress=None,
    )


def test_project_research_scope_emits_canonical_virtual_roots() -> None:
    view = project_research_scope(_envelope(), research_scope_id="r-abc123")
    assert isinstance(view, GraphContextView)
    assert view.workspace_root == "/mnt/user-data/workspace/deep-research/r-abc123"
    assert view.uploads_root == "/mnt/user-data/uploads"
    assert view.outputs_root == "/mnt/user-data/outputs/deep-research/r-abc123"


def test_projection_requires_trusted_envelope() -> None:
    with pytest.raises(ProjectionError) as excinfo:
        project_research_scope(object(), research_scope_id="r-abc123")  # type: ignore[arg-type]
    assert excinfo.value.code == "envelope_required"


@pytest.mark.parametrize("bad", ["", "../escape", "a/b", "has space", "x" * 129])
def test_projection_rejects_unsafe_scope_ids(bad: str) -> None:
    with pytest.raises(ProjectionError) as excinfo:
        project_research_scope(_envelope(), research_scope_id=bad)
    assert excinfo.value.code == "scope_invalid"


def test_project_node_agent_derives_attempt_root_under_scope() -> None:
    view = project_research_scope(_envelope(), research_scope_id="r-abc123")
    node = project_node_agent(view, node_name="collect_sources", attempt_id="att-1", policy_name="node-default")
    assert isinstance(node, NodeAgentContext)
    assert node.research_scope_id == "r-abc123"
    assert node.workspace_root == "/mnt/user-data/workspace/deep-research/r-abc123"
    assert node.attempt_root == "/mnt/user-data/workspace/deep-research/r-abc123/attempts/att-1"


@pytest.mark.parametrize(
    ("node_name", "attempt_id", "policy_name"),
    [
        ("BadName", "att-1", "node-default"),
        ("collect_sources", "../x", "node-default"),
        ("collect_sources", "att-1", "Bad_Policy"),
    ],
)
def test_project_node_agent_rejects_unsafe_inputs(node_name: str, attempt_id: str, policy_name: str) -> None:
    view = project_research_scope(_envelope(), research_scope_id="r-abc123")
    with pytest.raises(ProjectionError):
        project_node_agent(view, node_name=node_name, attempt_id=attempt_id, policy_name=policy_name)


def test_build_node_dependencies_requires_capabilities() -> None:
    view = project_research_scope(_envelope(), research_scope_id="r-abc123")
    node = project_node_agent(view, node_name="collect_sources", attempt_id="att-1", policy_name="node-default")
    with pytest.raises(ProjectionError) as excinfo:
        build_node_dependencies(view, node, object())  # type: ignore[arg-type]
    assert excinfo.value.code == "capabilities_required"

    deps = build_node_dependencies(view, node, FakeCapabilities())
    assert isinstance(deps, NodeBuildDependencies)


def test_model_facing_contracts_leak_no_host_identity_or_appconfig() -> None:
    view = project_research_scope(_envelope(), research_scope_id="r-abc123")
    node = project_node_agent(view, node_name="collect_sources", attempt_id="att-1", policy_name="node-default")
    serialized = f"{view.model_dump()}{node.model_dump()}"
    assert HOST_MARKER not in serialized
    assert "app_config" not in serialized
    assert "/users/" not in serialized
    assert "sandbox" not in serialized
    # Model-facing contracts have no field able to carry host paths or AppConfig.
    for model in (GraphContextView, NodeAgentContext):
        assert not {"host_path", "app_config", "sandbox", "user_id"} & set(model.model_fields)


def test_graph_context_is_frozen() -> None:
    view = project_research_scope(_envelope(), research_scope_id="r-abc123")
    with pytest.raises(ValidationError):
        view.workspace_root = "/mnt/user-data/workspace/deep-research/evil"  # type: ignore[misc]
