"""Runtime capability wiring for real HITL1.

@impl HIN-001
@impl HIN-004
@impl HIN-005
@impl NOA-001
@impl NOA-002
"""

from __future__ import annotations

import secrets
import time
from datetime import UTC, datetime
from pathlib import Path

import pytest

from deerflow_deep_research.domain.bootstrap import BootstrapMarker
from deerflow_deep_research.domain.lifecycle import WorkUnitStorageReason
from deerflow_deep_research.domain.profile import RequestBundleStoreProtocol, ResearchProfile
from deerflow_deep_research.domain.state import ContentRef
from deerflow_deep_research.graph.topology import LOGICAL_NODES
from deerflow_deep_research.runtime.bootstrap_bundle import BootstrapBundleStore
from deerflow_deep_research.runtime.node_agent_bridge import RuntimeNodeAgentBridge
from deerflow_deep_research.runtime.request_bundle import RequestBundleStore
from deerflow_deep_research.runtime.research import (
    FakeUnavailableCapabilities,
    ResearchGraphRecipe,
    StartResearchHandler,
)
from deerflow_deep_research.runtime.runtime_adapter import TrustedRuntimeEnvelope
from deerflow_deep_research.runtime.work_unit_storage import WorkUnitStoreError
from deerflow_deep_research.runtime.work_unit_store import WorkUnitStore

_RID = "r_" + "A" * 43
_FULL_FAKE = {name: "fake" for name in LOGICAL_NODES}
_MIXED_HITL1 = _FULL_FAKE | {"bootstrap": "real", "hitl1": "real"}
_MIXED_TOPIC = _FULL_FAKE | {"bootstrap": "real", "hitl1": "real", "topic_planning": "real"}


class FakeAppConfig:
    checkpointer = None
    database = None


class _Sandbox:
    id = "sandbox-1"
    sandbox_id = "sandbox-1"


def _envelope() -> TrustedRuntimeEnvelope:
    return TrustedRuntimeEnvelope(
        effective_user_id="alice",
        outer_thread_id="thread-1",
        outer_run_id="run-1",
        app_config=FakeAppConfig(),
        workspace_host_path=Path("/tmp/users/alice/workspace"),
        uploads_host_path=Path("/tmp/users/alice/uploads"),
        outputs_host_path=Path("/tmp/users/alice/outputs"),
        workspace_virtual_root="/mnt/user-data/workspace",
        uploads_virtual_root="/mnt/user-data/uploads",
        outputs_virtual_root="/mnt/user-data/outputs",
        parent_sandbox=_Sandbox(),
        progress=None,
    )


class _FakeBootstrapStore:
    async def establish_bundle(self, marker: BootstrapMarker) -> None: ...

    async def read_marker(self) -> BootstrapMarker | None:
        return None


class _FakeRequestStore:
    async def write_profile(self, profile: ResearchProfile) -> ContentRef:
        return ContentRef(
            sandbox_path=f"workspace/deep-research/{_RID}/request/profile.json",
            content_hash="h_" + "A" * 43,
        )


def _patch_stores(monkeypatch: pytest.MonkeyPatch, *, request_store: _FakeRequestStore | None = None) -> None:
    async def wu_create(_cls, envelope, *, research_id, **_kwargs):
        return WorkUnitStore(
            workspace_host_path=Path("/tmp/users/alice/workspace"),
            research_id=research_id,
            clock=lambda: datetime(2026, 7, 14, tzinfo=UTC),
            monotonic=time.monotonic,
            lock_sleep=time.sleep,
            token_factory=lambda: secrets.token_hex(16),
            fault_hook=None,
        )

    async def bb_create(_cls, envelope, *, research_id, **_kwargs):
        return _FakeBootstrapStore()

    async def rb_create(_cls, envelope, *, research_id, **_kwargs):
        return request_store or _FakeRequestStore()

    monkeypatch.setattr(WorkUnitStore, "create", classmethod(wu_create))
    monkeypatch.setattr(BootstrapBundleStore, "create", classmethod(bb_create))
    monkeypatch.setattr(RequestBundleStore, "create", classmethod(rb_create))


def test_recipe_detects_real_hitl1_and_requires_real_bootstrap() -> None:
    recipe = ResearchGraphRecipe.create(implementation_modes=_MIXED_HITL1)
    assert recipe.requires_bootstrap_bundle is True
    assert recipe.requires_request_bundle is True
    assert recipe.requires_node_agent_bridge is True

    with pytest.raises(ValueError, match="hitl1_real_requires_bootstrap_real"):
        ResearchGraphRecipe.create(implementation_modes=_FULL_FAKE | {"hitl1": "real"})


def test_recipe_detects_real_topic_planning_and_requires_real_hitl1() -> None:
    recipe = ResearchGraphRecipe.create(implementation_modes=_MIXED_TOPIC)
    assert recipe.requires_bootstrap_bundle is True
    assert recipe.requires_request_bundle is True  # from real hitl1, not topic planning
    assert recipe.requires_node_agent_bridge is True

    with pytest.raises(ValueError, match="topic_planning_real_requires_hitl1_real"):
        ResearchGraphRecipe.create(implementation_modes=_FULL_FAKE | {"topic_planning": "real"})
    with pytest.raises(ValueError, match="topic_planning_real_requires_hitl1_real"):
        ResearchGraphRecipe.create(implementation_modes=_FULL_FAKE | {"bootstrap": "real", "topic_planning": "real"})


async def test_real_topic_planning_context_constructs_zero_tool_bridge(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_stores(monkeypatch)
    handler = StartResearchHandler(ResearchGraphRecipe.create(implementation_modes=_MIXED_TOPIC))
    ctx = await handler._context(_envelope(), _RID, include_work_units=True)
    deps = ctx.dependency_resolver.resolve(
        logical_name="topic_planning", attempt_id="g0-tp-a1", policy=ctx_builder_policy()
    )
    assert isinstance(deps.capabilities, RuntimeNodeAgentBridge)
    assert deps.capabilities.policy.allowed_tool_names == frozenset()
    assert deps.capabilities.policy.budget.max_model_calls == 1
    assert tuple(deps.capabilities.tools_resolver(_envelope(), deps.capabilities.policy)) == ()


async def test_real_hitl1_context_constructs_zero_tool_one_model_bridge_and_request_writer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request_store = _FakeRequestStore()
    _patch_stores(monkeypatch, request_store=request_store)
    handler = StartResearchHandler(ResearchGraphRecipe.create(implementation_modes=_MIXED_HITL1))

    ctx = await handler._context(_envelope(), _RID, include_work_units=True)
    deps = ctx.dependency_resolver.resolve(logical_name="hitl1", attempt_id="g0-hitl1-a1", policy=ctx_builder_policy())

    assert isinstance(deps.capabilities, RuntimeNodeAgentBridge)
    assert deps.capabilities.policy.allowed_tool_names == frozenset()
    assert deps.capabilities.policy.budget.max_model_calls == 1
    assert tuple(deps.capabilities.tools_resolver(_envelope(), deps.capabilities.policy)) == ()
    assert ctx.request_bundle is request_store
    assert isinstance(ctx.request_bundle, RequestBundleStoreProtocol)
    assert ctx.bootstrap_bundle is not None
    assert ctx.work_units is not None


async def test_status_context_does_not_construct_hitl1_runtime_capabilities(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_stores(monkeypatch)
    handler = StartResearchHandler(ResearchGraphRecipe.create(implementation_modes=_MIXED_HITL1))

    ctx = await handler._context(_envelope(), _RID, include_work_units=False)
    assert ctx.request_bundle is None
    assert ctx.bootstrap_bundle is None
    assert ctx.work_units is None
    deps = ctx.dependency_resolver.resolve(logical_name="hitl1", attempt_id="g0-hitl1-a1", policy=ctx_builder_policy())
    assert isinstance(deps.capabilities, FakeUnavailableCapabilities)


async def test_full_fake_recipe_keeps_unavailable_capabilities_and_no_request_writer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_stores(monkeypatch)
    handler = StartResearchHandler(ResearchGraphRecipe.create(implementation_modes=_FULL_FAKE))
    ctx = await handler._context(_envelope(), _RID, include_work_units=True)
    deps = ctx.dependency_resolver.resolve(logical_name="hitl1", attempt_id="g0-hitl1-a1", policy=ctx_builder_policy())

    assert isinstance(deps.capabilities, FakeUnavailableCapabilities)
    assert ctx.request_bundle is None
    with pytest.raises(RuntimeError, match="full_fake_agent_capability_unavailable"):
        await deps.capabilities.run_agent(context=deps.agent_context, request=object())


async def test_request_bundle_create_error_surfaces_without_graph_invocation(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_stores(monkeypatch)

    async def rb_create(_cls, envelope, *, research_id, **_kwargs):
        raise WorkUnitStoreError(WorkUnitStorageReason.WORKSPACE_ALIAS_MISMATCH)

    monkeypatch.setattr(RequestBundleStore, "create", classmethod(rb_create))
    handler = StartResearchHandler(ResearchGraphRecipe.create(implementation_modes=_MIXED_HITL1))
    with pytest.raises(WorkUnitStoreError):
        await handler._context(_envelope(), _RID, include_work_units=True)


def ctx_builder_policy():
    from deerflow_deep_research.domain.node_spec import PolicyRef

    return PolicyRef(name="hitl1-profile", version="v1")
