"""Red tests for bootstrap bundle store wiring in the research action handler.

@impl BON-001
@impl BON-003
@impl RUI-006
"""

from __future__ import annotations

import secrets
import time
from datetime import UTC, datetime
from pathlib import Path

import pytest

from deerflow_deep_research.domain.bootstrap import BootstrapBundleStoreProtocol, BootstrapMarker
from deerflow_deep_research.domain.lifecycle import WorkUnitStorageReason
from deerflow_deep_research.graph.topology import LOGICAL_NODES
from deerflow_deep_research.runtime.bootstrap_bundle import BootstrapBundleStore
from deerflow_deep_research.runtime.research import ResearchGraphRecipe, StartResearchHandler
from deerflow_deep_research.runtime.runtime_adapter import TrustedRuntimeEnvelope
from deerflow_deep_research.runtime.work_unit_storage import WorkUnitStoreError
from deerflow_deep_research.runtime.work_unit_store import WorkUnitStore

_RID = "r_" + "A" * 43
_MIXED_MODES = {name: "fake" for name in LOGICAL_NODES} | {"bootstrap": "real"}


class FakeAppConfig:
    checkpointer = None
    database = None


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
        parent_sandbox=object(),
        progress=None,
    )


class _FakeBundleStore:
    async def establish_bundle(self, marker: BootstrapMarker) -> None: ...

    async def read_marker(self) -> BootstrapMarker | None:
        return None


def _patch_work_unit_store(monkeypatch: pytest.MonkeyPatch) -> None:
    async def create(_cls, envelope, *, research_id, **_kwargs):
        return WorkUnitStore(
            workspace_host_path=Path("/tmp/users/alice/workspace"),
            research_id=research_id,
            clock=lambda: datetime(2026, 7, 14, tzinfo=UTC),
            monotonic=time.monotonic,
            lock_sleep=time.sleep,
            token_factory=lambda: secrets.token_hex(16),
            fault_hook=None,
        )

    monkeypatch.setattr(WorkUnitStore, "create", classmethod(create))


@pytest.fixture
def handler() -> StartResearchHandler:
    return StartResearchHandler(ResearchGraphRecipe.create(implementation_modes=_MIXED_MODES))


class TestContextWiring:
    async def test_start_context_attaches_bootstrap_bundle(
        self, monkeypatch: pytest.MonkeyPatch, handler: StartResearchHandler
    ) -> None:
        _patch_work_unit_store(monkeypatch)
        fake = _FakeBundleStore()

        async def bb_create(_cls, envelope, *, research_id, **_kwargs):
            return fake

        monkeypatch.setattr(BootstrapBundleStore, "create", classmethod(bb_create))
        ctx = await handler._context(_envelope(), _RID, include_work_units=True)
        assert ctx.bootstrap_bundle is fake
        assert isinstance(ctx.bootstrap_bundle, BootstrapBundleStoreProtocol)
        assert ctx.work_units is not None

    async def test_status_context_does_not_construct_stores(self, handler: StartResearchHandler) -> None:
        ctx = await handler._context(_envelope(), _RID, include_work_units=False)
        assert ctx.bootstrap_bundle is None
        assert ctx.work_units is None

    async def test_unavailable_workspace_raises_without_context(
        self, monkeypatch: pytest.MonkeyPatch, handler: StartResearchHandler
    ) -> None:
        _patch_work_unit_store(monkeypatch)

        async def bb_create(_cls, envelope, *, research_id, **_kwargs):
            raise WorkUnitStoreError(WorkUnitStorageReason.AIO_PROVISIONER_UNMOUNTED)

        monkeypatch.setattr(BootstrapBundleStore, "create", classmethod(bb_create))
        with pytest.raises(WorkUnitStoreError):
            await handler._context(_envelope(), _RID, include_work_units=True)
