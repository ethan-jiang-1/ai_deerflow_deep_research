"""Non-checkpointed invocation context contracts (REG-001/RUI-006)."""

from __future__ import annotations

from dataclasses import fields

import pytest

from deerflow_deep_research.domain.context import GraphContextView, NodeAgentContext
from deerflow_deep_research.domain.invocation import GraphInvocationContext, NodeDependencyResolver
from deerflow_deep_research.domain.node_spec import NodeBuildDependencies, PolicyRef
from deerflow_deep_research.domain.profile import RequestBundleStoreProtocol, ResearchProfile
from deerflow_deep_research.domain.state import ContentRef


class NoopCapabilities:
    async def run_agent(self, *, context, request):  # pragma: no cover - fake nodes never call it
        raise AssertionError("not used")


class RecordingResolver:
    def __init__(self) -> None:
        self.attempts: list[str] = []

    def resolve(self, *, logical_name: str, attempt_id: str, policy: PolicyRef) -> NodeBuildDependencies:
        self.attempts.append(attempt_id)
        graph = GraphContextView(
            research_scope_id="r_" + "A" * 43,
            workspace_root="/mnt/user-data/workspace/deep-research/r",
            uploads_root="/mnt/user-data/uploads",
            outputs_root="/mnt/user-data/outputs/deep-research/r",
        )
        return NodeBuildDependencies(
            graph_context=graph,
            agent_context=NodeAgentContext(
                research_scope_id=graph.research_scope_id,
                node_name=logical_name,
                attempt_id=attempt_id,
                workspace_root=graph.workspace_root,
                attempt_root=f"{graph.workspace_root}/{attempt_id}",
                policy_name=policy.name,
            ),
            capabilities=NoopCapabilities(),
        )


def test_invocation_context_contains_only_reduced_context_and_resolver() -> None:
    resolver = RecordingResolver()
    context = GraphInvocationContext(
        graph_context=GraphContextView(
            research_scope_id="r_" + "A" * 43,
            workspace_root="/mnt/user-data/workspace/deep-research/r",
            uploads_root="/mnt/user-data/uploads",
            outputs_root="/mnt/user-data/outputs/deep-research/r",
        ),
        dependency_resolver=resolver,
    )
    assert {item.name for item in fields(context)} == {
        "graph_context",
        "dependency_resolver",
        "work_units",
        "bootstrap_bundle",
        "request_bundle",
    }
    assert isinstance(context.dependency_resolver, NodeDependencyResolver)
    with pytest.raises(TypeError):
        GraphInvocationContext(context.graph_context, resolver, fixture_plan={})


def test_invocation_context_accepts_pure_request_bundle_protocol() -> None:
    resolver = RecordingResolver()
    graph = GraphContextView(
        research_scope_id="r_" + "A" * 43,
        workspace_root="/mnt/user-data/workspace/deep-research/r",
        uploads_root="/mnt/user-data/uploads",
        outputs_root="/mnt/user-data/outputs/deep-research/r",
    )

    class Store:
        async def write_profile(self, profile: ResearchProfile) -> ContentRef:
            return ContentRef(
                sandbox_path=f"workspace/deep-research/{graph.research_scope_id}/request/profile.json",
                content_hash="h_" + "A" * 43,
            )

    context = GraphInvocationContext(graph_context=graph, dependency_resolver=resolver, request_bundle=Store())
    assert isinstance(context.request_bundle, RequestBundleStoreProtocol)
    with pytest.raises(TypeError, match="request_bundle"):
        GraphInvocationContext(graph_context=graph, dependency_resolver=resolver, request_bundle=object())


def test_resolver_gets_stable_retry_and_next_committed_attempt_ids() -> None:
    resolver = RecordingResolver()
    policy = PolicyRef(name="fake-policy", version="v1")
    resolver.resolve(logical_name="wave0", attempt_id="g0-wave0-a1", policy=policy)
    resolver.resolve(logical_name="wave0", attempt_id="g0-wave0-a1", policy=policy)
    resolver.resolve(logical_name="wave0", attempt_id="g0-wave0-a2", policy=policy)
    assert resolver.attempts == ["g0-wave0-a1", "g0-wave0-a1", "g0-wave0-a2"]
