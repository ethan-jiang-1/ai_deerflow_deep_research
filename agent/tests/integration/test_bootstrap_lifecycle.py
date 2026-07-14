"""Mixed real-bootstrap lifecycle integration (BON-001/004/005).

@impl BON-001
@impl BON-004
@impl BON-005
"""

from __future__ import annotations

import json
import secrets
import time
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.types import Command

from deerflow_deep_research.domain.bootstrap import BootstrapMarker
from deerflow_deep_research.graph.topology import LOGICAL_NODES
from deerflow_deep_research.runtime.bootstrap_bundle import BootstrapBundleStore
from deerflow_deep_research.runtime.control import build_control_graph_host
from deerflow_deep_research.runtime.research import ResearchGraphRecipe, derive_research_id
from deerflow_deep_research.runtime.runtime_adapter import TrustedRuntimeEnvelope
from deerflow_deep_research.runtime.work_unit_store import WorkUnitStore
from deerflow_deep_research.tool import run_deep_research

_MIXED_MODES = {name: "fake" for name in LOGICAL_NODES} | {"bootstrap": "real"}


class FakeAppConfig:
    checkpointer = None
    database = None


def _envelope(user: str = "alice", thread: str = "thread-1") -> TrustedRuntimeEnvelope:
    return TrustedRuntimeEnvelope(
        effective_user_id=user,
        outer_thread_id=thread,
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


class FakeAdapter:
    def __init__(self, envelope: TrustedRuntimeEnvelope | None = None) -> None:
        self.envelope = envelope or _envelope()

    async def adapt(self, _runtime, *, initialize_parent_sandbox: bool = True):
        return self.envelope


def _runtime(messages, call_id: str):
    return SimpleNamespace(state={"messages": list(messages)}, context={}, tool_call_id=call_id)


def _call(action: str, call_id: str, research_id: str | None = None) -> AIMessage:
    args: dict[str, object] = {"action": action}
    if research_id is not None:
        args["research_id"] = research_id
    return AIMessage(content="", tool_calls=[{"name": "deep_research", "args": args, "id": call_id}])


def _payload(command: Command) -> dict:
    message = command.update["messages"][0]
    return json.loads(message.content)


@pytest.fixture
def stores(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    async def wu_create(_cls, envelope, *, research_id, **_kwargs):
        workspace = tmp_path / envelope.effective_user_id / envelope.outer_thread_id / "workspace"
        workspace.mkdir(parents=True, exist_ok=True)
        return WorkUnitStore(
            workspace_host_path=workspace,
            research_id=research_id,
            clock=lambda: datetime(2026, 7, 14, tzinfo=UTC),
            monotonic=time.monotonic,
            lock_sleep=time.sleep,
            token_factory=lambda: secrets.token_hex(16),
            fault_hook=None,
        )

    monkeypatch.setattr(WorkUnitStore, "create", classmethod(wu_create))

    async def bb_create(_cls, envelope, *, research_id, **_kwargs):
        workspace = tmp_path / envelope.effective_user_id / envelope.outer_thread_id / "workspace"
        workspace.mkdir(parents=True, exist_ok=True)
        return BootstrapBundleStore(workspace_host_path=workspace, research_id=research_id)

    monkeypatch.setattr(BootstrapBundleStore, "create", classmethod(bb_create))


def _host():
    return build_control_graph_host(
        research_recipe=ResearchGraphRecipe.create(implementation_modes=_MIXED_MODES),
        fingerprint_verifier=lambda _app: None,
    )


def _marker_path(tmp_path: Path, user: str, thread: str, research_id: str) -> Path:
    return tmp_path / user / thread / "workspace" / "deep-research" / research_id / "request" / "marker.json"


async def _start(host, adapter, *, user_msg_id: str = "human-start", call_id: str = "call-start"):
    start_user = HumanMessage(content="research question", id=user_msg_id)
    start_ai = _call("start", call_id)
    return await run_deep_research(
        action="start",
        probe_id=None,
        runtime=_runtime([start_user, start_ai], call_id),
        adapter=adapter,
        host_factory=lambda: host,
    )


class TestMixedRealBootstrapLifecycle:
    async def test_start_establishes_marker_and_routes_to_hitl1(self, stores: None, tmp_path: Path) -> None:
        research_id = derive_research_id(effective_user_id="alice", outer_thread_id="thread-1")
        result = await _start(_host(), FakeAdapter())
        assert isinstance(result, Command)
        control = _payload(result)
        assert control["code"] == "suspended"
        assert control["implementation_mode"] == "full_fake"
        assert control["research_id"] == research_id
        marker_file = _marker_path(tmp_path, "alice", "thread-1", research_id)
        assert marker_file.is_file()
        marker = BootstrapMarker.from_canonical_json(marker_file.read_bytes())
        assert marker.research_id == research_id
        assert marker.start_message_id == "human-start"

    async def test_research_scoped_establishment_does_not_cross_threads(self, stores: None, tmp_path: Path) -> None:
        rid_a = derive_research_id(effective_user_id="alice", outer_thread_id="thread-a")
        rid_b = derive_research_id(effective_user_id="alice", outer_thread_id="thread-b")
        assert rid_a != rid_b
        host = _host()
        for thread, rid in (("thread-a", rid_a), ("thread-b", rid_b)):
            started = await _start(host, FakeAdapter(_envelope("alice", thread)), call_id=f"call-{thread}")
            assert isinstance(started, Command)
            assert _payload(started)["research_id"] == rid
        marker_a = _marker_path(tmp_path, "alice", "thread-a", rid_a)
        marker_b = _marker_path(tmp_path, "alice", "thread-b", rid_b)
        assert marker_a.is_file() and marker_b.is_file()
        assert BootstrapMarker.from_canonical_json(marker_a.read_bytes()).research_id == rid_a
        assert BootstrapMarker.from_canonical_json(marker_b.read_bytes()).research_id == rid_b
        assert not (tmp_path / "alice" / "thread-a" / "workspace" / "deep-research" / rid_b).exists()

    async def test_partial_directory_is_recovered_on_start(self, stores: None, tmp_path: Path) -> None:
        research_id = derive_research_id(effective_user_id="alice", outer_thread_id="thread-1")
        request_dir = tmp_path / "alice" / "thread-1" / "workspace" / "deep-research" / research_id / "request"
        request_dir.mkdir(parents=True, exist_ok=True)
        started = await _start(_host(), FakeAdapter())
        assert isinstance(started, Command)
        marker_file = _marker_path(tmp_path, "alice", "thread-1", research_id)
        assert marker_file.is_file()
        assert BootstrapMarker.from_canonical_json(marker_file.read_bytes()).research_id == research_id

    async def test_duplicate_same_message_start_is_idempotent(self, stores: None, tmp_path: Path) -> None:
        research_id = derive_research_id(effective_user_id="alice", outer_thread_id="thread-1")
        host = _host()
        adapter = FakeAdapter()
        first = await _start(host, adapter, call_id="call-start")
        again = await _start(host, adapter, call_id="call-start-2")
        assert isinstance(first, Command) and isinstance(again, Command)
        assert _payload(first)["research_id"] == research_id
        assert _payload(again)["research_id"] == research_id
