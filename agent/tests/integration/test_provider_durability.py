"""Real checkpoint provider durability contract (RUI-005).

Distinguishes same-process (memory, in-memory SQLite) from restart-durable
(file-backed SQLite) providers. The file-SQLite path is proven both across
provider contexts in-process AND across a real subprocess restart -- Deep
Research is a long, intermittent task that must resume after the Gateway stops
and later restarts. Postgres is deferred (a later change adds its Compose
profile); this suite requires no database server and no Docker.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from deerflow_deep_research.runtime.checkpoint import resolve_effective_provider
from deerflow_deep_research.runtime.probe import build_probe_graph_host
from deerflow_deep_research.runtime.runtime_adapter import TrustedRuntimeEnvelope

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def _sqlite_config(db_path: str) -> object:
    return SimpleNamespace(
        checkpointer=SimpleNamespace(type="sqlite", connection_string=db_path),
        database=None,
    )


def _memory_config() -> object:
    return SimpleNamespace(checkpointer=SimpleNamespace(type="memory", connection_string=None), database=None)


def _envelope(app_config: object) -> TrustedRuntimeEnvelope:
    return TrustedRuntimeEnvelope(
        effective_user_id="alice",
        outer_thread_id="thread-1",
        outer_run_id="run-1",
        app_config=app_config,
        workspace_host_path=Path("/x/workspace"),
        uploads_host_path=Path("/x/uploads"),
        outputs_host_path=Path("/x/outputs"),
        workspace_virtual_root="/mnt/user-data/workspace",
        uploads_virtual_root="/mnt/user-data/uploads",
        outputs_virtual_root="/mnt/user-data/outputs",
        parent_sandbox=object(),
        progress=None,
    )


# ── classifier durability distinctions (RUI-005) ────────────────────────────


def test_memory_is_same_process() -> None:
    selection = resolve_effective_provider(_memory_config())
    assert selection.kind == "memory"
    assert selection.durability == "same_process"


def test_file_sqlite_is_restart_durable() -> None:
    selection = resolve_effective_provider(_sqlite_config("/tmp/store.db"))
    assert selection.kind == "sqlite"
    assert selection.durability == "restart_durable"


def test_in_memory_sqlite_is_not_restart_durable() -> None:
    selection = resolve_effective_provider(_sqlite_config(":memory:"))
    assert selection.kind == "sqlite"
    assert selection.durability == "same_process"


# ── in-process provider reopen (RUI-005) ────────────────────────────────────


async def test_file_sqlite_recovers_across_provider_contexts(tmp_path: Path) -> None:
    db = str(tmp_path / "store.db")
    host = build_probe_graph_host(fingerprint_verifier=lambda _app_config: None)
    first = await host.run_action(action="infra_probe", envelope=_envelope(_sqlite_config(db)), action_input="p1")
    # Each action opens and closes its own SQLite provider context, so the second
    # call reads the first call's checkpoint back from the file on disk.
    second = await host.run_action(action="infra_probe", envelope=_envelope(_sqlite_config(db)), action_input="p1")
    assert first["previous_visit"] is None
    assert first["current_visit"] == 1
    assert first["durability"] == "restart_durable"
    assert second["previous_visit"] == 1
    assert second["current_visit"] == 2


# ── real subprocess restart (RUI-005) ───────────────────────────────────────


def _run_probe_subprocess(db: str, probe_id: str) -> dict:
    completed = subprocess.run(
        [sys.executable, str(FIXTURES / "sqlite_probe_subprocess.py"), db, probe_id],
        capture_output=True,
        text=True,
        timeout=60,
        check=True,
    )
    return json.loads(completed.stdout.strip())


def test_file_sqlite_survives_a_real_subprocess_restart(tmp_path: Path) -> None:
    db = str(tmp_path / "store.db")
    first = _run_probe_subprocess(db, "p1")
    # The first process has fully exited; a brand-new process opens the same file.
    second = _run_probe_subprocess(db, "p1")
    assert first["previous_visit"] is None
    assert first["current_visit"] == 1
    assert first["durability"] == "restart_durable"
    assert second["previous_visit"] == 1  # recovered from the on-disk checkpoint
    assert second["current_visit"] == 2


def test_subprocess_cross_scope_isolation(tmp_path: Path) -> None:
    db = str(tmp_path / "store.db")
    _run_probe_subprocess(db, "p1")
    other = _run_probe_subprocess(db, "p2")
    assert other["previous_visit"] is None  # a different probe id is isolated
    assert other["current_visit"] == 1


@pytest.mark.postgres
def test_postgres_profile_is_deferred() -> None:
    pytest.skip("Postgres durability is deferred; SQLite is the change-00 durable store")
