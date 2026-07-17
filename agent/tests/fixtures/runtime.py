"""Trusted local runtime fixtures for deterministic workflow tests.

@impl EVH-006
@impl EVH-007
"""

from __future__ import annotations

import re
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from deerflow.sandbox.local.local_sandbox import LocalSandbox, PathMapping

from deerflow_deep_research.runtime.runtime_adapter import TrustedRuntimeEnvelope


@dataclass(frozen=True)
class RunIdentity:
    user_id: str
    thread_id: str
    run_id: str
    research_id: str


def unique_run_identity() -> RunIdentity:
    token = secrets.token_urlsafe(12).replace("-", "_")
    digest = (token * 4)[:43]
    return RunIdentity("test-user", f"thread-{token}", f"run-{token}", f"r_{digest}")


def fixed_clock() -> datetime:
    return datetime(2026, 7, 17, 0, 0, tzinfo=UTC)


def fixed_token() -> str:
    return "a" * 32


def local_runtime_envelope(
    tmp_path: Path,
    *,
    identity: RunIdentity | None = None,
    app_config: Any | None = None,
) -> TrustedRuntimeEnvelope:
    identity = identity or unique_run_identity()
    workspace = tmp_path / "workspace"
    uploads = tmp_path / "uploads"
    outputs = tmp_path / "outputs"
    for path in (workspace, uploads, outputs):
        path.mkdir(parents=True, exist_ok=True)
    sandbox = LocalSandbox(
        id=f"local:{identity.user_id}:{identity.thread_id}",
        path_mappings=[
            PathMapping(container_path="/mnt/user-data/workspace", local_path=str(workspace)),
            PathMapping(container_path="/mnt/user-data/uploads", local_path=str(uploads)),
            PathMapping(container_path="/mnt/user-data/outputs", local_path=str(outputs)),
        ],
    )
    config = app_config or SimpleNamespace(models=[object()], tools=[], checkpointer=None, database=None)
    return TrustedRuntimeEnvelope(
        effective_user_id=identity.user_id,
        outer_thread_id=identity.thread_id,
        outer_run_id=identity.run_id,
        app_config=config,
        workspace_host_path=workspace,
        uploads_host_path=uploads,
        outputs_host_path=outputs,
        workspace_virtual_root="/mnt/user-data/workspace",
        uploads_virtual_root="/mnt/user-data/uploads",
        outputs_virtual_root="/mnt/user-data/outputs",
        parent_sandbox=sandbox,
        progress=None,
    )


_SECRET_RE = re.compile(r"(?i)(api[_-]?key|token|secret)=([^\s,]+)")
_HOST_PATH_RE = re.compile(r"(?:/private|/Users|/home|/tmp)/[^\s,]+")


def redact_diagnostic(value: object) -> str:
    text = str(value)
    text = _SECRET_RE.sub(r"\1=<redacted>", text)
    return _HOST_PATH_RE.sub("<host-path>", text)


__all__ = [
    "RunIdentity",
    "fixed_clock",
    "fixed_token",
    "local_runtime_envelope",
    "redact_diagnostic",
    "unique_run_identity",
]
