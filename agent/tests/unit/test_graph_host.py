"""Generic GraphHost lifecycle and isolation contract.

@impl RUI-004
"""

from __future__ import annotations

import asyncio
import hashlib
from dataclasses import dataclass, field
from typing import Any, TypedDict

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph

from deerflow_deep_research.runtime.checkpoint import derive_probe_thread_key
from deerflow_deep_research.runtime.graph_host import GraphHost, GraphHostError
from deerflow_deep_research.runtime.runtime_adapter import TrustedRuntimeEnvelope


class ProbeState(TypedDict):
    visits: int
    tick: int


def _bump(state: ProbeState) -> dict:
    return {"visits": (state.get("visits") or 0) + 1}


@dataclass
class MemoryDatabase:
    backend: str
    checkpointer_sqlite_path: str | None = None
    postgres_url: str | None = None


class FakeAppConfig:
    """Resolves through the effective-provider classifier without real config."""

    def __init__(self, database: MemoryDatabase | None = None) -> None:
        self.checkpointer = None
        self.database = database


def _envelope(user: str = "alice", thread: str = "thread-1", app_config: Any = None) -> TrustedRuntimeEnvelope:
    from pathlib import Path

    return TrustedRuntimeEnvelope(
        effective_user_id=user,
        outer_thread_id=thread,
        outer_run_id="run-1",
        app_config=app_config if app_config is not None else FakeAppConfig(),
        workspace_host_path=Path("/tmp/x/workspace"),
        uploads_host_path=Path("/tmp/x/uploads"),
        outputs_host_path=Path("/tmp/x/outputs"),
        workspace_virtual_root="/mnt/user-data/workspace",
        uploads_virtual_root="/mnt/user-data/uploads",
        outputs_virtual_root="/mnt/user-data/outputs",
        parent_sandbox=object(),
        progress=None,
    )


@dataclass
class CounterHandler:
    """A request-independent one-node counter recipe for probe checkpoints."""

    action: str = "test_probe"
    builds: int = 0
    executed: int = 0

    def build_graph(self) -> Any:
        self.builds += 1
        builder = StateGraph(ProbeState)
        builder.add_node("bump", _bump)
        builder.add_edge(START, "bump")
        builder.add_edge("bump", END)
        return builder

    def derive_namespace(self, envelope: TrustedRuntimeEnvelope, action_input: Any) -> str:
        return derive_probe_thread_key(
            effective_user_id=envelope.effective_user_id,
            outer_thread_id=envelope.outer_thread_id,
            probe_id=str(action_input),
        )

    async def execute(self, graph: Any, *, config: dict, envelope: TrustedRuntimeEnvelope, action_input: Any) -> Any:
        self.executed += 1
        return await graph.ainvoke({"tick": 1}, config=config)


@dataclass
class RecordingCheckpointer:
    """Async CM wrapping a real saver, recording enter/exit for SQL providers."""

    log: list[str]
    saver: Any = field(default_factory=InMemorySaver)

    async def __aenter__(self) -> Any:
        self.log.append("enter")
        return self.saver

    async def __aexit__(self, *exc: object) -> bool:
        self.log.append("exit")
        return False


def _make_host(fingerprint_verifier=lambda _app_config: None, checkpointer_factory=None) -> GraphHost:
    kwargs: dict[str, Any] = {"fingerprint_verifier": fingerprint_verifier}
    if checkpointer_factory is not None:
        kwargs["checkpointer_factory"] = checkpointer_factory
    return GraphHost(**kwargs)


async def test_unregistered_action_is_refused() -> None:
    host = _make_host()
    with pytest.raises(GraphHostError) as excinfo:
        await host.run_action(action="start", envelope=_envelope(), action_input="p1")
    assert excinfo.value.code == "action_unavailable"


async def test_registered_memory_action_runs() -> None:
    host = _make_host()
    handler = CounterHandler()
    host.register(handler)
    result = await host.run_action(action="test_probe", envelope=_envelope(), action_input="p1")
    assert result["visits"] == 1


async def test_same_probe_reuses_memory_checkpoint() -> None:
    host = _make_host()
    host.register(CounterHandler())
    env = _envelope()
    first = await host.run_action(action="test_probe", envelope=env, action_input="p1")
    second = await host.run_action(action="test_probe", envelope=env, action_input="p1")
    assert first["visits"] == 1
    assert second["visits"] == 2  # the earlier same-process checkpoint is observed


async def test_distinct_probe_and_user_are_isolated() -> None:
    host = _make_host()
    host.register(CounterHandler())
    await host.run_action(action="test_probe", envelope=_envelope(), action_input="p1")
    other_probe = await host.run_action(action="test_probe", envelope=_envelope(), action_input="p2")
    other_user = await host.run_action(action="test_probe", envelope=_envelope(user="bob"), action_input="p1")
    assert other_probe["visits"] == 1
    assert other_user["visits"] == 1


async def test_builder_recipe_is_cached_and_envelope_independent() -> None:
    host = _make_host()
    handler = CounterHandler()
    host.register(handler)
    await host.run_action(action="test_probe", envelope=_envelope(user="alice"), action_input="p1")
    await host.run_action(action="test_probe", envelope=_envelope(user="bob"), action_input="p1")
    # The recipe is built once and reused across different users/threads.
    assert handler.builds == 1
    assert handler.executed == 2


async def test_fingerprint_drift_refused_before_graph_work() -> None:
    def drift(_app_config: Any) -> None:
        raise GraphHostError("restart_required", "startup-only configuration changed")

    host = _make_host(fingerprint_verifier=drift)
    handler = CounterHandler()
    host.register(handler)
    with pytest.raises(GraphHostError) as excinfo:
        await host.run_action(action="test_probe", envelope=_envelope(), action_input="p1")
    assert excinfo.value.code == "restart_required"
    assert handler.executed == 0  # never reached provider/compile/execute


async def test_sql_provider_enters_and_exits_per_action() -> None:
    log: list[str] = []
    host = _make_host(checkpointer_factory=lambda _app_config: RecordingCheckpointer(log))
    host.register(CounterHandler())
    sqlite_config = FakeAppConfig(MemoryDatabase(backend="sqlite", checkpointer_sqlite_path="probe.db"))
    await host.run_action(action="test_probe", envelope=_envelope(app_config=sqlite_config), action_input="p1")
    await host.run_action(action="test_probe", envelope=_envelope(app_config=sqlite_config), action_input="p2")
    assert log == ["enter", "exit", "enter", "exit"]


async def test_sql_provider_closed_on_execute_exception() -> None:
    log: list[str] = []

    @dataclass
    class ExplodingHandler(CounterHandler):
        async def execute(self, graph: Any, *, config: dict, envelope: Any, action_input: Any) -> Any:
            raise RuntimeError("boom")

    host = _make_host(checkpointer_factory=lambda _app_config: RecordingCheckpointer(log))
    host.register(ExplodingHandler())
    sqlite_config = FakeAppConfig(MemoryDatabase(backend="sqlite", checkpointer_sqlite_path="probe.db"))
    with pytest.raises(RuntimeError):
        await host.run_action(action="test_probe", envelope=_envelope(app_config=sqlite_config), action_input="p1")
    assert log == ["enter", "exit"]  # provider context closed despite the error


async def test_same_namespace_actions_are_serialized() -> None:
    host = _make_host()

    @dataclass
    class BarrierHandler(CounterHandler):
        active: int = 0
        max_active: int = 0

        async def execute(self, graph: Any, *, config: dict, envelope: Any, action_input: Any) -> Any:
            self.active += 1
            self.max_active = max(self.max_active, self.active)
            await asyncio.sleep(0.02)
            self.active -= 1
            return await graph.ainvoke({"tick": 1}, config=config)

    handler = BarrierHandler()
    host.register(handler)
    env = _envelope()
    await asyncio.gather(
        host.run_action(action="test_probe", envelope=env, action_input="same"),
        host.run_action(action="test_probe", envelope=env, action_input="same"),
    )
    assert handler.max_active == 1


async def test_cancellation_closes_provider_and_releases_lock() -> None:
    log: list[str] = []
    host = _make_host(checkpointer_factory=lambda _app_config: RecordingCheckpointer(log))

    @dataclass
    class BlockingHandler(CounterHandler):
        async def execute(self, graph: Any, *, config: dict, envelope: Any, action_input: Any) -> Any:
            await asyncio.Event().wait()  # blocks until cancelled

    host.register(BlockingHandler())
    sqlite_config = FakeAppConfig(MemoryDatabase(backend="sqlite", checkpointer_sqlite_path="probe.db"))
    task = asyncio.create_task(
        host.run_action(action="test_probe", envelope=_envelope(app_config=sqlite_config), action_input="p1")
    )
    await asyncio.sleep(0.05)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    # The provider context is closed during cancellation cleanup, not leaked.
    assert log == ["enter", "exit"]


async def test_distinct_namespace_actions_run_concurrently() -> None:
    host = _make_host()
    # Choose two probe ids whose derived keys fall on different lock stripes.
    env = _envelope()

    def stripe(probe_id: str) -> int:
        key = derive_probe_thread_key(
            effective_user_id=env.effective_user_id,
            outer_thread_id=env.outer_thread_id,
            probe_id=probe_id,
        )
        return int.from_bytes(hashlib.sha256(key.encode()).digest()[:8], "big") % 64

    ids: list[str] = []
    seen: set[int] = set()
    counter = 0
    while len(ids) < 2:
        candidate = f"p{counter}"
        index = stripe(candidate)
        if index not in seen:
            seen.add(index)
            ids.append(candidate)
        counter += 1

    barrier = asyncio.Barrier(2)

    @dataclass
    class BarrierHandler(CounterHandler):
        async def execute(self, graph: Any, *, config: dict, envelope: Any, action_input: Any) -> Any:
            await barrier.wait()  # only completes if both actions run concurrently
            return await graph.ainvoke({"tick": 1}, config=config)

    host.register(BarrierHandler())
    await asyncio.wait_for(
        asyncio.gather(
            host.run_action(action="test_probe", envelope=env, action_input=ids[0]),
            host.run_action(action="test_probe", envelope=env, action_input=ids[1]),
        ),
        timeout=2,
    )
