"""Generic graph host: topology recipes, namespaces, and per-action providers.

@impl RUI-004

GraphHost caches only request-independent builder recipes and a generic typed
action-handler registry. Cached objects never retain a ``TrustedRuntimeEnvelope``,
reduced dependencies, namespace, checkpointer, or user/thread value. Each action
verifies the startup fingerprint, derives a fresh namespace, serializes
same-namespace mutations on a fixed process-local lock stripe, compiles the
cached builder inside the effective checkpointer's lifetime, and closes any SQL
provider on success, error, or cancellation.

Change 00 registers only a test/infrastructure-probe handler. GraphHost owns no
named research lifecycle methods, no ``InfraProbeState``, and no Gateway lifespan
hook: unregistered actions fail with typed ``action_unavailable``.
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import os
from collections.abc import AsyncIterator, Callable
from typing import Any, Protocol, runtime_checkable

from deerflow_deep_research.runtime.checkpoint import (
    ProviderSelection,
    resolve_effective_provider,
)
from deerflow_deep_research.runtime.runtime_adapter import (
    STARTUP_FINGERPRINT_ENV,
    WORKER_COUNT_ENV,
    TrustedRuntimeEnvelope,
)
from deerflow_deep_research.runtime.startup_snapshot import (
    StartupSnapshotError,
    verify_startup_fingerprint,
)

_LOCK_STRIPES = 64


class GraphHostError(RuntimeError):
    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"[{code}] {detail}")
        self.code = code
        self.detail = detail


@runtime_checkable
class ActionHandler(Protocol):
    """A request-independent recipe for one registered action."""

    action: str

    def build_graph(self) -> Any:
        """Return an uncompiled, request-independent graph builder."""

    def derive_namespace(self, envelope: TrustedRuntimeEnvelope, action_input: Any) -> str:
        """Return the internal checkpoint ``thread_id`` from trusted scope only.

        The digest already encodes domain/version separation, so the LangGraph
        ``checkpoint_ns`` stays empty (a non-empty value selects a subgraph).
        """

    async def execute(
        self,
        graph: Any,
        *,
        config: dict[str, Any],
        envelope: TrustedRuntimeEnvelope,
        action_input: Any,
    ) -> Any:
        """Invoke or inspect the compiled graph for this action."""


CheckpointerFactory = Callable[[Any], contextlib.AbstractAsyncContextManager[Any]]
MemorySaverFactory = Callable[[], Any]
FingerprintVerifier = Callable[[Any], None]


def _default_checkpointer_factory(app_config: Any) -> contextlib.AbstractAsyncContextManager[Any]:
    from deerflow.runtime.checkpointer.async_provider import make_checkpointer

    return make_checkpointer(app_config)


def _default_memory_saver_factory() -> Any:
    from langgraph.checkpoint.memory import InMemorySaver

    return InMemorySaver()


def _default_fingerprint_verifier(app_config: Any) -> None:
    expected = os.environ.get(STARTUP_FINGERPRINT_ENV)
    try:
        verify_startup_fingerprint(expected, app_config, worker_value=os.environ.get(WORKER_COUNT_ENV))
    except StartupSnapshotError as exc:
        raise GraphHostError("restart_required", exc.detail) from exc


class GraphHost:
    def __init__(
        self,
        *,
        checkpointer_factory: CheckpointerFactory = _default_checkpointer_factory,
        memory_saver_factory: MemorySaverFactory = _default_memory_saver_factory,
        fingerprint_verifier: FingerprintVerifier = _default_fingerprint_verifier,
    ) -> None:
        self._checkpointer_factory = checkpointer_factory
        self._memory_saver_factory = memory_saver_factory
        self._fingerprint_verifier = fingerprint_verifier
        self._handlers: dict[str, ActionHandler] = {}
        self._builders: dict[str, Any] = {}
        self._memory_saver: Any = None
        self._locks: list[Any] = [None] * _LOCK_STRIPES

    def register(self, handler: ActionHandler) -> None:
        if handler.action in self._handlers:
            raise GraphHostError("action_duplicate", f"action already registered: {handler.action}")
        self._handlers[handler.action] = handler

    def is_registered(self, action: str) -> bool:
        return action in self._handlers

    async def run_action(
        self,
        *,
        action: str,
        envelope: TrustedRuntimeEnvelope,
        action_input: Any = None,
    ) -> Any:
        handler = self._handlers.get(action)
        if handler is None:
            raise GraphHostError("action_unavailable", f"no registered handler for action: {action}")

        # Startup-only drift must fail before any provider or namespace access so
        # the nested runtime cannot pair with different startup singletons.
        self._fingerprint_verifier(envelope.app_config)

        thread_key = handler.derive_namespace(envelope, action_input)
        async with self._namespace_lock(thread_key):
            provider = resolve_effective_provider(envelope.app_config)
            async with self._saver_context(envelope.app_config, provider) as saver:
                graph = self._compile(handler, saver)
                config = {"configurable": {"thread_id": thread_key, "checkpoint_ns": ""}}
                return await handler.execute(
                    graph,
                    config=config,
                    envelope=envelope,
                    action_input=action_input,
                )

    def _compile(self, handler: ActionHandler, saver: Any) -> Any:
        builder = self._builders.get(handler.action)
        if builder is None:
            builder = handler.build_graph()
            self._builders[handler.action] = builder
        return builder.compile(checkpointer=saver)

    @contextlib.asynccontextmanager
    async def _saver_context(self, app_config: Any, provider: ProviderSelection) -> AsyncIterator[Any]:
        if provider.kind == "memory":
            # Reuse one process-local saver so a second same-process action can
            # observe an earlier checkpoint; memory is not restart durable.
            if self._memory_saver is None:
                self._memory_saver = self._memory_saver_factory()
            yield self._memory_saver
            return
        async with self._checkpointer_factory(app_config) as saver:
            yield saver

    def _namespace_lock(self, thread_key: str) -> Any:
        digest = hashlib.sha256(thread_key.encode("utf-8")).digest()
        index = int.from_bytes(digest[:8], "big") % _LOCK_STRIPES
        lock = self._locks[index]
        if lock is None:
            lock = asyncio.Lock()
            self._locks[index] = lock
        return lock


__all__ = ["ActionHandler", "GraphHost", "GraphHostError"]
