"""Reflected infrastructure-probe tool contract (RUI-001/002/003)."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from deerflow_deep_research.runtime.control import reset_default_graph_host
from deerflow_deep_research.runtime.probe import build_probe_graph_host
from deerflow_deep_research.runtime.runtime_adapter import RuntimeAdapterError, TrustedRuntimeEnvelope
from deerflow_deep_research.tool import (
    DeepResearchArgs,
    generate_probe_id,
    normalize_validation_error,
    run_deep_research,
)


def _envelope(user: str = "alice", thread: str = "thread-1") -> TrustedRuntimeEnvelope:
    return TrustedRuntimeEnvelope(
        effective_user_id=user,
        outer_thread_id=thread,
        outer_run_id="run-1",
        app_config=object(),
        workspace_host_path=Path("/srv/host/users/alice/workspace"),
        uploads_host_path=Path("/srv/host/users/alice/uploads"),
        outputs_host_path=Path("/srv/host/users/alice/outputs"),
        workspace_virtual_root="/mnt/user-data/workspace",
        uploads_virtual_root="/mnt/user-data/uploads",
        outputs_virtual_root="/mnt/user-data/outputs",
        parent_sandbox=object(),
        progress=None,
    )


class FakeAdapter:
    def __init__(self, envelope: TrustedRuntimeEnvelope | None = None, *, error: Exception | None = None) -> None:
        self._envelope = envelope or _envelope()
        self._error = error
        self.adapted = 0

    async def adapt(self, _runtime, *, initialize_parent_sandbox: bool = True):
        self.adapted += 1
        if self._error is not None:
            raise self._error
        return self._envelope


def _host():
    return build_probe_graph_host(fingerprint_verifier=lambda _app_config: None)


# ── schema strictness (RUI-001/002) ─────────────────────────────────────────


def test_valid_args_accepted() -> None:
    assert DeepResearchArgs(action="infra_probe").probe_id is None
    assert DeepResearchArgs(action="infra_probe", probe_id="abc-123_XYZ").probe_id == "abc-123_XYZ"


@pytest.mark.parametrize("field", ["user_id", "thread_id", "path", "sandbox", "checkpoint_ns", "run_id"])
def test_authority_and_unknown_fields_are_rejected(field: str) -> None:
    with pytest.raises(ValidationError):
        DeepResearchArgs(action="infra_probe", **{field: "x"})


@pytest.mark.parametrize("bad", ["has/slash", "with space", "x" * 65, ""])
def test_malformed_probe_id_is_rejected(bad: str) -> None:
    with pytest.raises(ValidationError):
        DeepResearchArgs(action="infra_probe", probe_id=bad)


def test_normalized_error_exposes_fields_and_codes_only() -> None:
    try:
        DeepResearchArgs(action="infra_probe", user_id="attacker", probe_id="bad/id")
    except ValidationError as exc:
        normalized = normalize_validation_error(exc)
    assert set(normalized) == {"code", "fields", "violations"}
    serialized = str(normalized)
    assert "attacker" not in serialized  # never echoes the rejected input value
    assert "bad/id" not in serialized


def test_generated_probe_id_is_opaque_and_high_entropy() -> None:
    a, b = generate_probe_id(), generate_probe_id()
    assert a != b
    assert len(a) >= 22  # token_urlsafe(16) -> >=128 bits
    assert all(ch.isalnum() or ch in "-_" for ch in a)


# ── dispatch: action availability (RUI-001) ─────────────────────────────────


@pytest.mark.parametrize("action", ["start", "resume", "status", "cancel", "teleport"])
async def test_unavailable_action_returns_before_adapter_without_echo(action: str) -> None:
    adapter = FakeAdapter()
    result = await run_deep_research(action=action, probe_id=None, runtime=None, adapter=adapter, host_factory=_host)
    assert result == {"code": "action_unavailable", "supported": ["infra_probe"]}
    assert adapter.adapted == 0  # never reached RuntimeAdapter/sandbox
    assert action not in str(result)


# ── probe behaviour (RUI-001/002/003) ───────────────────────────────────────


async def test_first_probe_initializes_and_writes_checkpoint() -> None:
    host = _host()
    result = await run_deep_research(
        action="infra_probe", probe_id="p1", runtime=None, adapter=FakeAdapter(), host_factory=lambda: host
    )
    assert result["previous_visit"] is None
    assert result["current_visit"] == 1
    assert result["provider_kind"] == "memory"
    assert result["durability"] == "same_process"


async def test_same_probe_id_revisits_prior_marker() -> None:
    host = _host()
    await run_deep_research(
        action="infra_probe", probe_id="p1", runtime=None, adapter=FakeAdapter(), host_factory=lambda: host
    )
    second = await run_deep_research(
        action="infra_probe", probe_id="p1", runtime=None, adapter=FakeAdapter(), host_factory=lambda: host
    )
    assert second["previous_visit"] == 1
    assert second["current_visit"] == 2  # revisit, not "resume"


async def test_default_dispatch_reuses_process_local_host_but_injected_hosts_are_independent() -> None:
    reset_default_graph_host(_host())
    try:
        first = await run_deep_research(
            action="infra_probe",
            probe_id="default-p1",
            runtime=None,
            adapter=FakeAdapter(),
        )
        second = await run_deep_research(
            action="infra_probe",
            probe_id="default-p1",
            runtime=None,
            adapter=FakeAdapter(),
        )
        assert first["previous_visit"] is None
        assert second["previous_visit"] == 1
        assert second["current_visit"] == 2

        left = _host()
        right = _host()
        left_result = await run_deep_research(
            action="infra_probe", probe_id="injected-p1", runtime=None, adapter=FakeAdapter(), host_factory=lambda: left
        )
        right_result = await run_deep_research(
            action="infra_probe",
            probe_id="injected-p1",
            runtime=None,
            adapter=FakeAdapter(),
            host_factory=lambda: right,
        )
        assert left_result["previous_visit"] is None
        assert right_result["previous_visit"] is None
    finally:
        reset_default_graph_host()


async def test_cross_scope_probe_is_isolated() -> None:
    host = _host()
    await run_deep_research(
        action="infra_probe",
        probe_id="p1",
        runtime=None,
        adapter=FakeAdapter(_envelope(user="alice")),
        host_factory=lambda: host,
    )
    other = await run_deep_research(
        action="infra_probe",
        probe_id="p1",
        runtime=None,
        adapter=FakeAdapter(_envelope(user="bob")),
        host_factory=lambda: host,
    )
    assert other["previous_visit"] is None  # bob cannot see alice's probe checkpoint


async def test_result_exposes_only_opaque_fields() -> None:
    host = _host()
    result = await run_deep_research(
        action="infra_probe",
        probe_id="p1",
        runtime=None,
        adapter=FakeAdapter(_envelope(user="alice", thread="thread-secret")),
        host_factory=lambda: host,
    )
    serialized = str(result)
    assert "alice" not in serialized
    assert "thread-secret" not in serialized
    assert "/srv/host" not in serialized
    assert set(result) == {"probe_id", "previous_visit", "current_visit", "last_marker", "provider_kind", "durability"}


async def test_adapter_failure_returns_code_and_writes_no_checkpoint() -> None:
    host = _host()
    failing = FakeAdapter(error=RuntimeAdapterError("restart_required", "drift"))
    result = await run_deep_research(
        action="infra_probe", probe_id="p1", runtime=None, adapter=failing, host_factory=lambda: host
    )
    assert result == {"code": "restart_required"}
    # No checkpoint was written, so a later successful probe still starts at 1.
    ok = await run_deep_research(
        action="infra_probe", probe_id="p1", runtime=None, adapter=FakeAdapter(), host_factory=lambda: host
    )
    assert ok["previous_visit"] is None
    assert ok["current_visit"] == 1
