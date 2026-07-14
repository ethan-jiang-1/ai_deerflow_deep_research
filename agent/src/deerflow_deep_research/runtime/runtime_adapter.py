"""Adapt trusted DeerFlow runtime fields into a runtime-owned envelope.

@impl RUI-002

``RuntimeAdapter`` consumes DeerFlow's ``ToolRuntime`` and produces a
``TrustedRuntimeEnvelope`` that is visible only inside ``runtime/`` (integration,
GraphHost, projection, and the node-agent bridge). The envelope is never
serialized into graph state and never reads private Gateway run-journal fields.

The adapter stops at the validated envelope: it does not invent a research scope
or workspace. ``runtime/projection.py`` performs research projection only when a
registered handler supplies a validated opaque scope id.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from deerflow_deep_research.runtime.events import ProgressEmitter, make_progress_emitter
from deerflow_deep_research.runtime.identity import (
    require_context_value,
    require_trusted_user_id,
)
from deerflow_deep_research.runtime.startup_snapshot import (
    StartupSnapshotError,
    verify_startup_fingerprint,
)

WORKSPACE_VIRTUAL_ROOT = "/mnt/user-data/workspace"
UPLOADS_VIRTUAL_ROOT = "/mnt/user-data/uploads"
OUTPUTS_VIRTUAL_ROOT = "/mnt/user-data/outputs"
STARTUP_FINGERPRINT_ENV = "DEER_FLOW_DEEP_RESEARCH_STARTUP_FINGERPRINT"
WORKER_COUNT_ENV = "GATEWAY_WORKERS"


class RuntimeAdapterError(RuntimeError):
    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"[{code}] {detail}")
        self.code = code
        self.detail = detail


@dataclass(frozen=True)
class TrustedRuntimeEnvelope:
    """Runtime-only trusted binding. Never serialized into graph state."""

    effective_user_id: str
    outer_thread_id: str
    outer_run_id: str
    app_config: Any
    workspace_host_path: Path
    uploads_host_path: Path
    outputs_host_path: Path
    workspace_virtual_root: str
    uploads_virtual_root: str
    outputs_virtual_root: str
    parent_sandbox: Any | None
    progress: ProgressEmitter


SandboxInitializer = Callable[[Any], Awaitable[Any]]
PathsProvider = Callable[[], Any]
FingerprintVerifier = Callable[[Any], None]
EmitterFactory = Callable[[], ProgressEmitter]


def _default_fingerprint_verifier(app_config: Any) -> None:
    expected = os.environ.get(STARTUP_FINGERPRINT_ENV)
    try:
        verify_startup_fingerprint(expected, app_config, worker_value=os.environ.get(WORKER_COUNT_ENV))
    except StartupSnapshotError as exc:
        raise RuntimeAdapterError("restart_required", exc.detail) from exc


def _default_sandbox_initializer(runtime: Any) -> Awaitable[Any]:
    from deerflow.sandbox.tools import ensure_sandbox_initialized_async

    return ensure_sandbox_initialized_async(runtime)


def _default_paths_provider() -> Any:
    from deerflow.config.paths import get_paths

    return get_paths()


class RuntimeAdapter:
    """Turn a trusted ToolRuntime into a TrustedRuntimeEnvelope, fail-closed."""

    def __init__(
        self,
        *,
        sandbox_initializer: SandboxInitializer = _default_sandbox_initializer,
        paths_provider: PathsProvider = _default_paths_provider,
        fingerprint_verifier: FingerprintVerifier = _default_fingerprint_verifier,
        emitter_factory: EmitterFactory = make_progress_emitter,
    ) -> None:
        self._sandbox_initializer = sandbox_initializer
        self._paths_provider = paths_provider
        self._fingerprint_verifier = fingerprint_verifier
        self._emitter_factory = emitter_factory

    async def adapt(self, runtime: Any, *, initialize_parent_sandbox: bool = True) -> TrustedRuntimeEnvelope:
        user_id = require_trusted_user_id(runtime)
        thread_id = str(require_context_value(runtime, "thread_id", "thread_missing"))
        run_id = str(require_context_value(runtime, "run_id", "run_missing"))
        app_config = require_context_value(runtime, "app_config", "app_config_missing")

        # Startup-only configuration drift must be caught before any provider or
        # sandbox access so the nested runtime never pairs with different startup
        # singletons than the process was launched with.
        self._fingerprint_verifier(app_config)

        paths = self._paths_provider()
        host_paths = await asyncio.to_thread(self._resolve_host_paths, paths, thread_id, user_id)
        self._validate_thread_data(runtime, thread_id)

        parent_sandbox = None
        if initialize_parent_sandbox:
            parent_sandbox = await self._sandbox_initializer(runtime)
            if parent_sandbox is None:
                raise RuntimeAdapterError("sandbox_unavailable", "parent sandbox initialization returned nothing")

        return TrustedRuntimeEnvelope(
            effective_user_id=user_id,
            outer_thread_id=thread_id,
            outer_run_id=run_id,
            app_config=app_config,
            workspace_host_path=host_paths[0],
            uploads_host_path=host_paths[1],
            outputs_host_path=host_paths[2],
            workspace_virtual_root=WORKSPACE_VIRTUAL_ROOT,
            uploads_virtual_root=UPLOADS_VIRTUAL_ROOT,
            outputs_virtual_root=OUTPUTS_VIRTUAL_ROOT,
            parent_sandbox=parent_sandbox,
            progress=self._emitter_factory(),
        )

    @staticmethod
    def _resolve_host_paths(paths: Any, thread_id: str, user_id: str) -> tuple[Path, Path, Path]:
        try:
            thread_dir = Path(paths.thread_dir(thread_id, user_id=user_id)).resolve()
            workspace = Path(paths.sandbox_work_dir(thread_id, user_id=user_id)).resolve()
            uploads = Path(paths.sandbox_uploads_dir(thread_id, user_id=user_id)).resolve()
            outputs = Path(paths.sandbox_outputs_dir(thread_id, user_id=user_id)).resolve()
        except (OSError, AttributeError, ValueError) as exc:
            raise RuntimeAdapterError("thread_path_invalid", "trusted thread paths could not be resolved") from exc
        for candidate in (workspace, uploads, outputs):
            if candidate != thread_dir and thread_dir not in candidate.parents:
                raise RuntimeAdapterError(
                    "thread_path_escape",
                    "a resolved thread path escapes the trusted user/thread root",
                )
        return workspace, uploads, outputs

    @staticmethod
    def _validate_thread_data(runtime: Any, thread_id: str) -> None:
        state = getattr(runtime, "state", None)
        if not isinstance(state, dict):
            return
        thread_data = state.get("thread_data")
        if isinstance(thread_data, dict):
            declared = thread_data.get("thread_id")
            if declared not in (None, "") and str(declared) != thread_id:
                raise RuntimeAdapterError(
                    "thread_data_mismatch",
                    "runtime state thread data does not match the trusted outer thread",
                )


__all__ = [
    "OUTPUTS_VIRTUAL_ROOT",
    "RuntimeAdapter",
    "RuntimeAdapterError",
    "TrustedRuntimeEnvelope",
    "UPLOADS_VIRTUAL_ROOT",
    "WORKSPACE_VIRTUAL_ROOT",
]
