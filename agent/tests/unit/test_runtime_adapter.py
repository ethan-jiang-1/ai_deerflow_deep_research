"""RuntimeAdapter trusted-context and fail-closed contract (RUI-002)."""

from __future__ import annotations

from pathlib import Path

import pytest
from deerflow.runtime.user_context import resolve_runtime_user_id

from deerflow_deep_research.runtime.events import make_progress_emitter
from deerflow_deep_research.runtime.identity import TrustedIdentityError
from deerflow_deep_research.runtime.runtime_adapter import (
    RuntimeAdapter,
    RuntimeAdapterError,
    TrustedRuntimeEnvelope,
)

SANDBOX = object()
APP_CONFIG = object()


class FakeRuntime:
    def __init__(self, context: dict, state: dict | None = None, config: dict | None = None) -> None:
        self.context = context
        self.state = {} if state is None else state
        self.config = {} if config is None else config


class FakePaths:
    def __init__(self, root: Path, *, escape: bool = False) -> None:
        self.root = root
        self.escape = escape

    def thread_dir(self, thread_id: str, *, user_id: str | None = None) -> Path:
        return self.root / "users" / str(user_id) / "threads" / thread_id

    def sandbox_work_dir(self, thread_id: str, *, user_id: str | None = None) -> Path:
        if self.escape:
            return self.root / "outside" / "workspace"
        return self.thread_dir(thread_id, user_id=user_id) / "user-data" / "workspace"

    def sandbox_uploads_dir(self, thread_id: str, *, user_id: str | None = None) -> Path:
        return self.thread_dir(thread_id, user_id=user_id) / "user-data" / "uploads"

    def sandbox_outputs_dir(self, thread_id: str, *, user_id: str | None = None) -> Path:
        return self.thread_dir(thread_id, user_id=user_id) / "user-data" / "outputs"


class FakeSandboxInitializer:
    def __init__(self, *, fail: bool = False) -> None:
        self.calls = 0
        self.acquired = 0
        self.reused = 0
        self.fail = fail

    async def __call__(self, runtime: FakeRuntime) -> object:
        self.calls += 1
        if self.fail:
            raise RuntimeError("sandbox acquisition failed")
        if runtime.state.get("sandbox"):
            self.reused += 1
            return SANDBOX
        self.acquired += 1
        runtime.state["sandbox"] = {"sandbox_id": "sb-1"}
        return SANDBOX


def _context(**overrides) -> dict:
    base = {
        "user_id": "alice",
        "thread_id": "thread-1",
        "run_id": "run-1",
        "app_config": APP_CONFIG,
    }
    base.update(overrides)
    return base


def _adapter(
    paths: FakePaths,
    initializer: FakeSandboxInitializer,
    *,
    fingerprint_verifier=lambda _app_config: None,
) -> RuntimeAdapter:
    return RuntimeAdapter(
        sandbox_initializer=initializer,
        paths_provider=lambda: paths,
        fingerprint_verifier=fingerprint_verifier,
        emitter_factory=lambda: make_progress_emitter(sink=lambda _event: None),
    )


@pytest.fixture()
def paths(tmp_path: Path) -> FakePaths:
    return FakePaths(tmp_path)


async def test_adapt_emits_trusted_envelope_without_research_scope(paths: FakePaths) -> None:
    initializer = FakeSandboxInitializer()
    envelope = await _adapter(paths, initializer).adapt(FakeRuntime(_context()))

    assert isinstance(envelope, TrustedRuntimeEnvelope)
    assert envelope.effective_user_id == "alice"
    assert envelope.outer_thread_id == "thread-1"
    assert envelope.outer_run_id == "run-1"
    assert envelope.app_config is APP_CONFIG
    assert envelope.parent_sandbox is SANDBOX
    # RuntimeAdapter stops at the envelope: no research root / node-agent scope.
    assert not any("research" in field for field in type(envelope).__dataclass_fields__)
    assert initializer.calls == 1


async def test_missing_user_id_fails_even_though_default_fallback_exists(paths: FakePaths) -> None:
    runtime = FakeRuntime(_context())
    del runtime.context["user_id"]
    # DeerFlow's generic helper would happily return the synthetic default user...
    assert resolve_runtime_user_id(runtime) == "default"
    # ...but the authority boundary refuses it.
    with pytest.raises(TrustedIdentityError) as excinfo:
        await _adapter(paths, FakeSandboxInitializer()).adapt(runtime)
    assert excinfo.value.code == "identity_missing"


@pytest.mark.parametrize("value", ["", "   "])
async def test_blank_user_id_fails(paths: FakePaths, value: str) -> None:
    with pytest.raises(TrustedIdentityError):
        await _adapter(paths, FakeSandboxInitializer()).adapt(FakeRuntime(_context(user_id=value)))


@pytest.mark.parametrize("missing", ["thread_id", "run_id", "app_config"])
async def test_missing_trusted_context_field_fails(paths: FakePaths, missing: str) -> None:
    runtime = FakeRuntime(_context())
    del runtime.context[missing]
    with pytest.raises((TrustedIdentityError, RuntimeAdapterError)):
        await _adapter(paths, FakeSandboxInitializer()).adapt(runtime)


async def test_startup_fingerprint_drift_fails_before_sandbox(paths: FakePaths) -> None:
    def drift(_app_config) -> None:
        raise RuntimeAdapterError("restart_required", "startup-only configuration changed")

    initializer = FakeSandboxInitializer()
    with pytest.raises(RuntimeAdapterError) as excinfo:
        await _adapter(paths, initializer, fingerprint_verifier=drift).adapt(FakeRuntime(_context()))
    assert excinfo.value.code == "restart_required"
    assert initializer.calls == 0  # never reaches sandbox initialization


async def test_thread_path_escape_is_denied(tmp_path: Path) -> None:
    escaping = FakePaths(tmp_path, escape=True)
    with pytest.raises(RuntimeAdapterError) as excinfo:
        await _adapter(escaping, FakeSandboxInitializer()).adapt(FakeRuntime(_context()))
    assert excinfo.value.code == "thread_path_escape"


async def test_symlink_thread_path_escape_is_denied(tmp_path: Path) -> None:
    paths = FakePaths(tmp_path)
    thread_dir = paths.thread_dir("thread-1", user_id="alice")
    (thread_dir / "user-data").mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    (thread_dir / "user-data" / "workspace").symlink_to(outside)
    with pytest.raises(RuntimeAdapterError) as excinfo:
        await _adapter(paths, FakeSandboxInitializer()).adapt(FakeRuntime(_context()))
    assert excinfo.value.code == "thread_path_escape"


async def test_thread_data_mismatch_is_denied(paths: FakePaths) -> None:
    runtime = FakeRuntime(_context(), state={"thread_data": {"thread_id": "other-thread"}})
    with pytest.raises(RuntimeAdapterError) as excinfo:
        await _adapter(paths, FakeSandboxInitializer()).adapt(runtime)
    assert excinfo.value.code == "thread_data_mismatch"


async def test_fresh_thread_initializes_parent_sandbox_once(paths: FakePaths) -> None:
    initializer = FakeSandboxInitializer()
    runtime = FakeRuntime(_context())  # no "sandbox" in state
    envelope = await _adapter(paths, initializer).adapt(runtime)
    assert initializer.acquired == 1
    assert initializer.reused == 0
    assert envelope.parent_sandbox is SANDBOX


async def test_preinitialized_sandbox_is_reused_without_new_lifecycle(paths: FakePaths) -> None:
    initializer = FakeSandboxInitializer()
    runtime = FakeRuntime(_context(), state={"sandbox": {"sandbox_id": "sb-existing"}})
    await _adapter(paths, initializer).adapt(runtime)
    assert initializer.reused == 1
    assert initializer.acquired == 0


async def test_sandbox_initializer_failure_fails_closed(paths: FakePaths) -> None:
    with pytest.raises(RuntimeError):
        await _adapter(paths, FakeSandboxInitializer(fail=True)).adapt(FakeRuntime(_context()))


async def test_checkpoint_only_adaptation_skips_parent_sandbox(paths: FakePaths) -> None:
    initializer = FakeSandboxInitializer(fail=True)
    envelope = await _adapter(paths, initializer).adapt(
        FakeRuntime(_context()),
        initialize_parent_sandbox=False,
    )
    assert initializer.calls == 0
    assert envelope.parent_sandbox is None
