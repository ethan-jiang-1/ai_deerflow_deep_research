"""Provider-selection and startup-snapshot contracts."""

from __future__ import annotations

import importlib
import re
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest
from deerflow.config.app_config import AppConfig
from deerflow.config.checkpointer_config import CheckpointerConfig
from deerflow.config.database_config import DatabaseConfig
from deerflow.config.sandbox_config import SandboxConfig


def _checkpoint_module():
    return importlib.import_module("deerflow_deep_research.runtime.checkpoint")


def _snapshot_module():
    return importlib.import_module("deerflow_deep_research.runtime.startup_snapshot")


def _config(
    *,
    database: DatabaseConfig | None = None,
    checkpointer: CheckpointerConfig | None = None,
    sandbox: SandboxConfig | None = None,
):
    return SimpleNamespace(
        database=database if database is not None else DatabaseConfig(),
        checkpointer=checkpointer,
        sandbox=sandbox or SandboxConfig(use="deerflow.sandbox.local:LocalSandboxProvider"),
    )


def test_direct_app_config_default_is_memory() -> None:
    config = AppConfig(sandbox={"use": "deerflow.sandbox.local:LocalSandboxProvider"})

    selection = _checkpoint_module().resolve_effective_provider(config)

    assert (selection.kind, selection.source, selection.connection, selection.durability, selection.issue) == (
        "memory",
        "database",
        None,
        "same_process",
        None,
    )


def test_file_loaded_database_omission_uses_current_sqlite_defaults(tmp_path: Path, monkeypatch) -> None:
    config_path = tmp_path / "config.yaml"
    extensions_path = tmp_path / "extensions_config.json"
    config_path.write_text("sandbox:\n  use: deerflow.sandbox.local:LocalSandboxProvider\n", encoding="utf-8")
    extensions_path.write_text('{"mcpServers": {}, "skills": {}}\n', encoding="utf-8")
    monkeypatch.setenv("DEER_FLOW_EXTENSIONS_CONFIG_PATH", str(extensions_path))

    config = AppConfig.from_file(str(config_path))
    selection = _checkpoint_module().resolve_effective_provider(config)

    assert config.database.backend == "sqlite"
    assert config.database.sqlite_dir == ".deer-flow/data"
    assert selection.kind == "sqlite"
    assert selection.source == "database"
    assert selection.connection.endswith("/.deer-flow/data/deerflow.db")
    assert selection.durability == "restart_durable"


@pytest.mark.parametrize(
    ("database", "expected"),
    [
        (DatabaseConfig(backend="memory"), ("memory", None, "same_process", None)),
        (
            DatabaseConfig(backend="sqlite", sqlite_dir="relative-db"),
            ("sqlite", "relative-db/deerflow.db", "restart_durable", None),
        ),
        (
            DatabaseConfig(backend="postgres", postgres_url="postgresql://user:secret@db/research"),
            ("postgres", "postgresql://user:secret@db/research", "restart_durable", None),
        ),
        (
            DatabaseConfig(backend="postgres", postgres_url=""),
            ("postgres", None, "unavailable", "postgres_connection_missing"),
        ),
    ],
)
def test_unified_database_provider_matrix(
    database: DatabaseConfig, expected: tuple[str, str | None, str, str | None]
) -> None:
    selection = _checkpoint_module().resolve_effective_provider(_config(database=database))

    expected_kind, expected_connection_suffix, expected_durability, expected_issue = expected
    assert selection.kind == expected_kind
    if expected_connection_suffix is None:
        assert selection.connection is None
    elif expected_kind == "sqlite":
        assert selection.connection.endswith(expected_connection_suffix)
    else:
        assert selection.connection == expected_connection_suffix
    assert selection.durability == expected_durability
    assert selection.issue == expected_issue


@pytest.mark.parametrize(
    ("checkpointer", "expected"),
    [
        (CheckpointerConfig(type="memory"), ("memory", None, "same_process", None)),
        (CheckpointerConfig(type="sqlite", connection_string=None), ("sqlite", "store.db", "restart_durable", None)),
        (
            CheckpointerConfig(type="sqlite", connection_string=":memory:"),
            ("sqlite", ":memory:", "same_process", None),
        ),
        (
            CheckpointerConfig(type="sqlite", connection_string="file:memdb?mode=memory&cache=shared"),
            ("sqlite", "file:memdb?mode=memory&cache=shared", "same_process", None),
        ),
        (
            CheckpointerConfig(type="postgres", connection_string="postgresql://user:secret@db/research"),
            ("postgres", "postgresql://user:secret@db/research", "restart_durable", None),
        ),
        (
            CheckpointerConfig(type="postgres", connection_string=None),
            ("postgres", None, "unavailable", "postgres_connection_missing"),
        ),
    ],
)
def test_legacy_checkpointer_provider_matrix(
    checkpointer: CheckpointerConfig,
    expected: tuple[str, str | None, str, str | None],
) -> None:
    selection = _checkpoint_module().resolve_effective_provider(_config(checkpointer=checkpointer))

    assert selection.source == "legacy_checkpointer"
    assert (selection.kind, selection.connection, selection.durability, selection.issue) == expected


LEGACY_CASES = [
    CheckpointerConfig(type="memory"),
    CheckpointerConfig(type="sqlite", connection_string="legacy.db"),
    CheckpointerConfig(type="postgres", connection_string="postgresql://legacy:secret@db/research"),
]
DATABASE_CASES = [
    DatabaseConfig(backend="memory"),
    DatabaseConfig(backend="sqlite", sqlite_dir="unified-db"),
    DatabaseConfig(backend="postgres", postgres_url="postgresql://unified:secret@db/research"),
]


@pytest.mark.parametrize("legacy", LEGACY_CASES, ids=lambda value: value.type)
@pytest.mark.parametrize("database", DATABASE_CASES, ids=lambda value: value.backend)
def test_every_legacy_database_conflict_selects_legacy(
    legacy: CheckpointerConfig,
    database: DatabaseConfig,
) -> None:
    selection = _checkpoint_module().resolve_effective_provider(_config(database=database, checkpointer=legacy))

    assert selection.source == "legacy_checkpointer"
    assert selection.kind == legacy.type


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "config",
    [
        _config(database=DatabaseConfig(backend="memory")),
        _config(database=DatabaseConfig(backend="sqlite", sqlite_dir="db")),
        _config(database=DatabaseConfig(backend="postgres", postgres_url="postgresql://db/research")),
        _config(
            database=DatabaseConfig(backend="postgres", postgres_url="postgresql://ignored/db"),
            checkpointer=CheckpointerConfig(type="memory"),
        ),
        _config(
            database=DatabaseConfig(backend="memory"),
            checkpointer=CheckpointerConfig(type="sqlite", connection_string="legacy.db"),
        ),
        _config(
            database=DatabaseConfig(backend="sqlite", sqlite_dir="ignored"),
            checkpointer=CheckpointerConfig(type="postgres", connection_string="postgresql://legacy/db"),
        ),
    ],
    ids=[
        "database-memory",
        "database-sqlite",
        "database-postgres",
        "legacy-memory",
        "legacy-sqlite",
        "legacy-postgres",
    ],
)
async def test_classifier_matches_actual_make_checkpointer_branch(config, monkeypatch) -> None:
    from deerflow.runtime.checkpointer import async_provider
    from langgraph.checkpoint.memory import InMemorySaver

    observed: list[tuple[str, str]] = []

    @asynccontextmanager
    async def fake_legacy(selected):
        observed.append(("legacy_checkpointer", selected.type))
        yield object()

    @asynccontextmanager
    async def fake_database(selected):
        observed.append(("database", selected.backend))
        yield object()

    monkeypatch.setattr(async_provider, "_async_checkpointer", fake_legacy)
    monkeypatch.setattr(async_provider, "_async_checkpointer_from_database", fake_database)
    selection = _checkpoint_module().resolve_effective_provider(config)

    async with async_provider.make_checkpointer(config) as saver:
        if observed:
            actual_source, actual_kind = observed[0]
        else:
            assert isinstance(saver, InMemorySaver)
            actual_source, actual_kind = "database", "memory"

    assert (selection.source, selection.kind) == (actual_source, actual_kind)


@pytest.mark.parametrize(
    ("raw", "normalized", "supported", "issue"),
    [
        (None, 1, True, None),
        ("", 1, True, None),
        ("1", 1, True, None),
        ("01", 1, True, None),
        ("0", 0, False, "worker_count_unsupported"),
        ("-1", -1, False, "worker_count_unsupported"),
        ("many", None, False, "worker_count_invalid"),
        ("2", 2, False, "worker_count_unsupported"),
    ],
)
def test_gateway_worker_normalization(
    raw: str | None, normalized: int | None, supported: bool, issue: str | None
) -> None:
    result = _snapshot_module().normalize_gateway_workers(raw)

    assert (result.normalized, result.supported, result.issue) == (normalized, supported, issue)


def test_snapshot_hash_is_deterministic_versioned_and_secret_free() -> None:
    first = _config(
        database=DatabaseConfig(backend="postgres", postgres_url="postgresql://user:db-secret@host/research"),
        sandbox=SandboxConfig(
            use="example.sandbox:Provider",
            environment={"Z_TOKEN": "sandbox-secret", "A_MODE": "test"},
            api_key="provider-secret",
        ),
    )
    reordered = _config(
        database=DatabaseConfig(backend="postgres", postgres_url="postgresql://user:db-secret@host/research"),
        sandbox=SandboxConfig(
            use="example.sandbox:Provider",
            api_key="provider-secret",
            environment={"A_MODE": "test", "Z_TOKEN": "sandbox-secret"},
        ),
    )
    module = _snapshot_module()

    first_payload = module.canonical_startup_payload(first, worker_value="01")
    second_payload = module.canonical_startup_payload(reordered, worker_value="1")
    first_fingerprint = module.capture_startup_fingerprint(first, worker_value="01")
    second_fingerprint = module.capture_startup_fingerprint(reordered, worker_value="1")

    assert first_payload == second_payload
    assert first_fingerprint == second_fingerprint
    assert re.fullmatch(r"v1:[0-9a-f]{64}", first_fingerprint)
    combined = first_payload + first_fingerprint
    assert "db-secret" not in combined
    assert "sandbox-secret" not in combined
    assert "provider-secret" not in combined


@pytest.mark.parametrize(
    "value",
    [
        None,
        "",
        "0" * 64,
        "v1:abc",
        f"v1:{'A' * 64}",
        f"v2:{'0' * 64}",
        f"v1:{'0' * 64}:extra",
    ],
)
def test_fingerprint_parser_rejects_missing_malformed_and_unknown_versions(value: str | None) -> None:
    module = _snapshot_module()

    with pytest.raises(module.StartupSnapshotError):
        module.parse_startup_fingerprint(value)


def test_fingerprint_verification_detects_post_start_drift() -> None:
    module = _snapshot_module()
    started = _config(database=DatabaseConfig(backend="sqlite", sqlite_dir="started-db"))
    changed = _config(database=DatabaseConfig(backend="sqlite", sqlite_dir="changed-db"))
    expected = module.capture_startup_fingerprint(started, worker_value="1")

    module.verify_startup_fingerprint(expected, started, worker_value="01")
    with pytest.raises(module.StartupSnapshotError, match="restart_required"):
        module.verify_startup_fingerprint(expected, changed, worker_value="1")
