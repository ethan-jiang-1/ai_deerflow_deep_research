"""Red tests for the BOOTSTRAP_BUNDLE node capability and dependency slot.

@impl BON-001
@impl BON-002
"""

from __future__ import annotations

from dataclasses import replace

from pydantic import BaseModel

from deerflow_deep_research.domain.bootstrap import BootstrapBundleStoreProtocol, BootstrapMarker
from deerflow_deep_research.domain.context import GraphContextView, NodeAgentContext
from deerflow_deep_research.domain.enums import NodePhase
from deerflow_deep_research.domain.node_spec import (
    NodeBuildDependencies,
    NodeCapability,
    NodeContracts,
    NodeSpec,
    PolicyRef,
)
from deerflow_deep_research.domain.profile import RequestBundleStoreProtocol, ResearchProfile
from deerflow_deep_research.domain.state import ContentRef

_RID = "r_" + "a" * 43


class _Req(BaseModel):
    pass


class _Res(BaseModel):
    pass


def _factory(deps: NodeBuildDependencies) -> object:
    return None


def _context_view() -> GraphContextView:
    return GraphContextView(
        research_scope_id="r_test",
        workspace_root=f"/mnt/user-data/workspace/deep-research/{_RID}",
        uploads_root="/mnt/user-data/uploads",
        outputs_root="/mnt/user-data/outputs",
    )


def _agent_context() -> NodeAgentContext:
    return NodeAgentContext(
        research_scope_id="r_test",
        node_name="bootstrap",
        attempt_id="g0_bootstrap_a01",
        workspace_root=_context_view().workspace_root,
        attempt_root=_context_view().workspace_root,
        policy_name="skeleton-bootstrap",
    )


class _Caps:
    async def run_agent(self, *, context: object, request: object) -> object: ...


def _deps() -> NodeBuildDependencies:
    return NodeBuildDependencies(
        graph_context=_context_view(),
        agent_context=_agent_context(),
        capabilities=_Caps(),
    )


def _spec(*, capabilities: frozenset[NodeCapability]) -> NodeSpec:
    return NodeSpec(
        logical_name="bootstrap",
        phase=NodePhase.ORCHESTRATION,
        policy=PolicyRef(name="skeleton-bootstrap", version="v1"),
        contracts=NodeContracts(request_type=_Req, result_type=_Res),
        real_factory=_factory,
        fake_factory=_factory,
        capabilities=capabilities,
    )


class TestBootstrapBundleCapability:
    def test_capability_member_exists(self) -> None:
        assert NodeCapability.BOOTSTRAP_BUNDLE.value == "bootstrap_bundle"

    def test_dependency_slot_defaults_to_none(self) -> None:
        assert _deps().bootstrap_bundle is None

    def test_dependency_slot_accepts_a_store(self) -> None:
        class _Store:
            async def establish_bundle(self, marker: BootstrapMarker) -> None: ...

            async def read_marker(self) -> BootstrapMarker | None: ...

        deps = replace(_deps(), bootstrap_bundle=_Store())
        assert isinstance(deps.bootstrap_bundle, BootstrapBundleStoreProtocol)

    def test_declaring_spec_is_constructible(self) -> None:
        spec = _spec(capabilities=frozenset({NodeCapability.BOOTSTRAP_BUNDLE}))
        assert NodeCapability.BOOTSTRAP_BUNDLE in spec.capabilities

    def test_non_declaring_spec_is_constructible(self) -> None:
        spec = _spec(capabilities=frozenset())
        assert NodeCapability.BOOTSTRAP_BUNDLE not in spec.capabilities


class TestRequestBundleCapability:
    def test_capability_member_exists(self) -> None:
        assert NodeCapability.REQUEST_BUNDLE.value == "request_bundle"

    def test_dependency_slot_defaults_to_none(self) -> None:
        assert _deps().request_bundle is None

    def test_dependency_slot_accepts_a_store(self) -> None:
        class _Store:
            async def write_profile(self, profile: ResearchProfile) -> ContentRef:
                return ContentRef(
                    sandbox_path=f"workspace/deep-research/{_RID}/request/profile.json",
                    content_hash="h_" + "A" * 43,
                )

        deps = replace(_deps(), request_bundle=_Store())
        assert isinstance(deps.request_bundle, RequestBundleStoreProtocol)

    def test_declaring_spec_is_constructible(self) -> None:
        spec = _spec(capabilities=frozenset({NodeCapability.REQUEST_BUNDLE}))
        assert NodeCapability.REQUEST_BUNDLE in spec.capabilities
