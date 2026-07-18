"""Real checkpoint provider durability contract.

@impl RUI-005

Distinguishes same-process (memory, in-memory SQLite) from restart-durable
(file-backed SQLite) providers. The file-SQLite path is proven both across
provider contexts in-process AND across a real subprocess restart -- Deep
Research is a long, intermittent task that must resume after the Gateway stops
and later restarts. Postgres is deferred (a later change adds its Compose
profile); this suite requires no database server and no Docker.
"""

from __future__ import annotations

import json
import secrets
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from deerflow_deep_research.domain.lifecycle import LifecycleAction
from deerflow_deep_research.runtime.checkpoint import resolve_effective_provider
from deerflow_deep_research.runtime.control import build_control_graph_host
from deerflow_deep_research.runtime.human_input import SelectedStartMessage
from deerflow_deep_research.runtime.probe import build_probe_graph_host
from deerflow_deep_research.runtime.research import ResearchActionInput, derive_research_id
from deerflow_deep_research.runtime.runtime_adapter import TrustedRuntimeEnvelope
from deerflow_deep_research.runtime.work_unit_store import WorkUnitStore
from tests.scenarios.assertions import assert_scenario
from tests.scenarios.observation import (
    CheckpointFacts,
    LedgerFacts,
    LifecycleFacts,
    SandboxFacts,
    ScenarioObservation,
)
from tests.scenarios.replays import CHECKPOINT_CONTROL_CASE, CHECKPOINT_CONTROL_FAMILY

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


@pytest.fixture(autouse=True)
def _verified_work_unit_store(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    async def create(_cls, _envelope, *, research_id, **_kwargs):
        return WorkUnitStore(
            workspace_host_path=workspace,
            research_id=research_id,
            clock=lambda: datetime(2026, 7, 14, tzinfo=UTC),
            monotonic=time.monotonic,
            lock_sleep=time.sleep,
            token_factory=lambda: secrets.token_hex(16),
            fault_hook=None,
        )

    monkeypatch.setattr(WorkUnitStore, "create", classmethod(create))


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


async def test_file_sqlite_probe_visits_are_isolated_from_research_lifecycle(tmp_path: Path) -> None:
    db = str(tmp_path / "isolated.db")
    config = _sqlite_config(db)
    envelope = _envelope(config)
    host = build_control_graph_host(fingerprint_verifier=lambda _app_config: None)

    before = await host.run_action(action="infra_probe", envelope=envelope, action_input="p1")
    research_id = derive_research_id(
        effective_user_id=envelope.effective_user_id,
        outer_thread_id=envelope.outer_thread_id,
    )
    started = await host.run_action(
        action="start",
        envelope=envelope,
        action_input=ResearchActionInput(
            action=LifecycleAction.START,
            research_id=research_id,
            tool_call_id="call-start",
            messages=(),
            start_message=SelectedStartMessage(message_id="human-start", text="research question"),
        ),
    )
    after = await host.run_action(action="infra_probe", envelope=envelope, action_input="p1")

    assert started.update["messages"][0].artifact["human_input"]["source"] == "deep_research"
    assert before["previous_visit"] is None and before["current_visit"] == 1
    assert after["previous_visit"] == 1 and after["current_visit"] == 2
    assert before["durability"] == after["durability"] == "restart_durable"


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


def _run_research_subprocess(db: str, mode: str, request_id: str | None = None) -> dict:
    args = [sys.executable, str(FIXTURES / "sqlite_research_subprocess.py"), db, mode]
    if request_id is not None:
        args.append(request_id)
    completed = subprocess.run(
        args,
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


def test_file_sqlite_research_resumes_after_real_subprocess_restart(tmp_path: Path) -> None:
    db = str(tmp_path / "research.db")
    first = _run_research_subprocess(db, "start")
    second = _run_research_subprocess(db, "resume", first["request_id"])

    assert first["code"] == second["code"] == "suspended"
    assert first["research_id"] == second["research_id"]
    assert first["request_id"] != second["request_id"]
    assert first["durability"] == second["durability"] == "restart_durable"
    assert first["implementation_mode"] == second["implementation_mode"] == "full_fake"

    # Research checkpoints use a separate digest domain; opening the probe
    # namespace afterwards still observes a brand-new probe lifecycle.
    probe = _run_probe_subprocess(db, "p1")
    assert probe["previous_visit"] is None
    assert probe["current_visit"] == 1


@pytest.mark.workflow
@pytest.mark.parametrize(
    "case",
    [pytest.param(CHECKPOINT_CONTROL_CASE, id=CHECKPOINT_CONTROL_CASE.case_id)],
)
def test_checkpoint_control_survives_process_restarts(tmp_path: Path, case) -> None:
    db = str(tmp_path / "checkpoint-control.db")
    started = _run_research_subprocess(db, "start")
    resumed = _run_research_subprocess(db, "resume", started["request_id"])
    duplicate_resume = _run_research_subprocess(db, "resume", started["request_id"])
    cancelled = _run_research_subprocess(db, "cancel")
    duplicate_cancel = _run_research_subprocess(db, "cancel")
    terminal_resume = _run_research_subprocess(db, "resume", resumed["request_id"])
    status = _run_research_subprocess(db, "status")
    results = (started, resumed, duplicate_resume, cancelled, duplicate_cancel, terminal_resume, status)

    observation = ScenarioObservation(
        checkpoint=CheckpointFacts(route=None, terminal=status["status"], identity_isolated=True, attempt_count=7),
        ledger=LedgerFacts((), False, True),
        sandbox=SandboxFacts(True, (), ()),
        lifecycle=LifecycleFacts(
            research_ids=tuple(result["research_id"] for result in results),
            resume_request_ids=(resumed["request_id"], duplicate_resume["request_id"]),
            cancel_statuses=(cancelled["status"], duplicate_cancel["status"]),
            post_terminal_resume_code=terminal_resume["code"],
            final_status=status["status"],
            durabilities=tuple(result["durability"] for result in results),
        ),
    )

    assert started["code"] == resumed["code"] == duplicate_resume["code"] == "suspended"
    assert cancelled["code"] == duplicate_cancel["code"] == "cancelled"
    assert status["code"] == "status_ok"
    assert_scenario(CHECKPOINT_CONTROL_FAMILY, case, observation)


@pytest.mark.postgres
def test_postgres_profile_is_deferred() -> None:
    pytest.skip("Postgres durability is deferred; SQLite is the change-00 durable store")
