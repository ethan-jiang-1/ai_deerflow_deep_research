"""Real-Gateway trust-chain contract for injected identity (RUI-002).

This is a marked real-Gateway integration test: it imports ``app.*`` (allowed
only in real-Gateway integration fixtures) to prove the end-to-end identity
chain. It runs only where the full Gateway stack is importable (backend
environment with ``deerflow_deep_research`` editable-installed); it skips
cleanly in the isolated agent environment.

It exercises the real ``inject_authenticated_user_context`` across the three
owner modes and feeds the resulting runtime context through the real
``RuntimeAdapter``, asserting the effective identity is the server-injected one
and never a client-spoofed ``body.context`` / ``body.config`` value.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

try:  # pragma: no cover - import guard, exercised by environment selection
    from app.gateway.auth_disabled import AUTH_DISABLED_USER_ID
    from app.gateway.internal_auth import INTERNAL_SYSTEM_ROLE
    from app.gateway.services import inject_authenticated_user_context

    _APP_AVAILABLE = True
except Exception:  # noqa: BLE001 - any import failure means the stack is absent
    _APP_AVAILABLE = False

pytestmark = pytest.mark.skipif(not _APP_AVAILABLE, reason="real Gateway app stack is unavailable")

if _APP_AVAILABLE:
    from deerflow_deep_research.runtime.events import make_progress_emitter
    from deerflow_deep_research.runtime.identity import TrustedIdentityError
    from deerflow_deep_research.runtime.runtime_adapter import RuntimeAdapter


class FakeUser:
    def __init__(self, user_id, system_role="user") -> None:
        self.id = user_id
        self.system_role = system_role
        self.oauth_provider = None
        self.oauth_id = None


class FakeState:
    def __init__(self, user) -> None:
        self.user = user


class FakeRequest:
    def __init__(self, user) -> None:
        self.state = FakeState(user)


class FakeRuntime:
    def __init__(self, context: dict) -> None:
        self.context = context
        self.state: dict = {}
        self.config: dict = {}


class FakePaths:
    def __init__(self, root: Path) -> None:
        self.root = root

    def thread_dir(self, thread_id, *, user_id=None):
        return self.root / "users" / str(user_id) / "threads" / thread_id

    def sandbox_work_dir(self, thread_id, *, user_id=None):
        return self.thread_dir(thread_id, user_id=user_id) / "user-data" / "workspace"

    def sandbox_uploads_dir(self, thread_id, *, user_id=None):
        return self.thread_dir(thread_id, user_id=user_id) / "user-data" / "uploads"

    def sandbox_outputs_dir(self, thread_id, *, user_id=None):
        return self.thread_dir(thread_id, user_id=user_id) / "user-data" / "outputs"


async def _fake_sandbox(_runtime):
    return object()


def _effective_user_id(context: dict, tmp_path: Path) -> str:
    runtime = FakeRuntime({**context, "thread_id": "t-1", "run_id": "r-1", "app_config": object()})
    adapter = RuntimeAdapter(
        sandbox_initializer=_fake_sandbox,
        paths_provider=lambda: FakePaths(tmp_path),
        fingerprint_verifier=lambda _app_config: None,
        emitter_factory=lambda: make_progress_emitter(sink=lambda _event: None),
    )
    return asyncio.run(adapter.adapt(runtime)).effective_user_id


def test_authenticated_request_overwrites_spoofed_body_and_config(tmp_path: Path) -> None:
    config = {
        "context": {"user_id": "attacker-body"},
        "configurable": {"user_id": "attacker-config"},
    }
    inject_authenticated_user_context(config, FakeRequest(FakeUser("alice-real")))
    assert config["context"]["user_id"] == "alice-real"
    assert _effective_user_id(config["context"], tmp_path) == "alice-real"


def test_auth_disabled_mode_injects_synthetic_default(tmp_path: Path) -> None:
    config = {"context": {"user_id": "attacker-body"}}
    inject_authenticated_user_context(config, FakeRequest(FakeUser(AUTH_DISABLED_USER_ID)))
    assert config["context"]["user_id"] == AUTH_DISABLED_USER_ID
    assert _effective_user_id(config["context"], tmp_path) == "default"


def test_internal_role_retains_owner_without_body_override(tmp_path: Path) -> None:
    # The internally authenticated path already set the trusted owner; the auth
    # injector early-returns for the internal system role and must not clobber it.
    config = {"context": {"user_id": "trusted-internal-owner"}}
    inject_authenticated_user_context(config, FakeRequest(FakeUser("scheduler", system_role=INTERNAL_SYSTEM_ROLE)))
    assert config["context"]["user_id"] == "trusted-internal-owner"
    assert _effective_user_id(config["context"], tmp_path) == "trusted-internal-owner"


def test_unauthenticated_request_leaves_identity_absent_and_adapter_fails_closed(tmp_path: Path) -> None:
    config: dict = {"context": {}}
    inject_authenticated_user_context(config, FakeRequest(None))
    assert "user_id" not in config["context"]
    with pytest.raises(TrustedIdentityError):
        _effective_user_id(config["context"], tmp_path)
