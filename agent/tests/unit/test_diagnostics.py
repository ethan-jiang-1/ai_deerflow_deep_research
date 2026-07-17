"""Readiness diagnostics and credential redaction contract.

@impl DEC-005
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from deerflow_deep_research.runtime.diagnostics import EntryState, run_diagnostics
from deerflow_deep_research.runtime.startup_snapshot import capture_startup_fingerprint


class MemoryAppConfig:
    """A fake AppConfig that ``resolve_effective_provider`` classifies as memory."""

    checkpointer = None
    database = None
    sandbox = {"use": "deerflow.sandbox.local:LocalSandboxProvider"}


MEMORY_CONFIG = MemoryAppConfig()


def _configured_for(*, fingerprint: str | None, workers: str | None) -> None:
    if fingerprint is not None:
        os.environ["DEER_FLOW_DEEP_RESEARCH_STARTUP_FINGERPRINT"] = fingerprint
    if workers is not None:
        os.environ["GATEWAY_WORKERS"] = workers


@pytest.fixture(autouse=True)
def _env() -> dict:
    # isolate tests from the real environment
    saved = dict(os.environ)
    for key in ("DEER_FLOW_DEEP_RESEARCH_STARTUP_FINGERPRINT", "GATEWAY_WORKERS"):
        os.environ.pop(key, None)
    yield saved
    os.environ.clear()
    os.environ.update(saved)


# ── in-process mode ─────────────────────────────────────────────────────────


def test_in_process_no_fingerprint_is_not_ready() -> None:
    diag = run_diagnostics(app_config=MEMORY_CONFIG)
    assert diag.mode == "in-process"
    assert not diag.runtime_ready
    assert any("absent" in issue for issue in diag.issues)


def test_in_process_malformed_fingerprint_diagnosed() -> None:
    os.environ["DEER_FLOW_DEEP_RESEARCH_STARTUP_FINGERPRINT"] = "garbage"
    diag = run_diagnostics(app_config=MEMORY_CONFIG)
    assert not diag.runtime_ready
    assert any("malformed" in issue or "fingerprint" in issue for issue in diag.issues)


def test_in_process_matching_fingerprint_is_ready(tmp_path: Path) -> None:
    fp = capture_startup_fingerprint(MEMORY_CONFIG, worker_value="1")
    os.environ["DEER_FLOW_DEEP_RESEARCH_STARTUP_FINGERPRINT"] = fp
    os.environ["GATEWAY_WORKERS"] = "1"
    diag = run_diagnostics(app_config=MEMORY_CONFIG, work_unit_storage_base_dir=tmp_path)
    assert diag.runtime_ready
    assert diag.durability == "same_process"
    assert diag.work_unit_storage == "ready"


def test_in_process_fingerprint_drift_is_not_ready() -> None:
    from deerflow_deep_research.runtime.startup_snapshot import FINGERPRINT_VERSION

    # A definite non-matching fingerprint for a different config.
    os.environ["DEER_FLOW_DEEP_RESEARCH_STARTUP_FINGERPRINT"] = f"{FINGERPRINT_VERSION}:{'00' * 32}"
    os.environ["GATEWAY_WORKERS"] = "1"
    diag = run_diagnostics(app_config=MEMORY_CONFIG)
    assert not diag.runtime_ready


# ── prelaunch-candidate mode ────────────────────────────────────────────────


def test_prelaunch_matching_candidate_is_ready(tmp_path: Path) -> None:
    fp = capture_startup_fingerprint(MEMORY_CONFIG, worker_value="1")
    os.environ["GATEWAY_WORKERS"] = "1"
    diag = run_diagnostics(
        expected_fingerprint=fp,
        app_config=MEMORY_CONFIG,
        work_unit_storage_base_dir=tmp_path,
    )
    assert diag.mode == "prelaunch-candidate"
    assert diag.runtime_ready
    assert diag.work_unit_storage == "ready"
    assert "fingerprint_candidate_match" in diag.checks


def test_prelaunch_mismatched_candidate_is_not_ready() -> None:
    from deerflow_deep_research.runtime.startup_snapshot import FINGERPRINT_VERSION

    os.environ["GATEWAY_WORKERS"] = "1"
    diag = run_diagnostics(
        expected_fingerprint=f"{FINGERPRINT_VERSION}:{'00' * 32}",
        app_config=MEMORY_CONFIG,
    )
    assert not diag.runtime_ready
    assert any("does not match" in issue for issue in diag.issues)


def test_unknown_work_unit_provider_keeps_runtime_not_ready(tmp_path: Path) -> None:
    config = MemoryAppConfig()
    config.sandbox = {"use": "custom.local:LocalSandboxProvider"}
    fp = capture_startup_fingerprint(config, worker_value="1")
    os.environ["GATEWAY_WORKERS"] = "1"
    diag = run_diagnostics(
        expected_fingerprint=fp,
        app_config=config,
        work_unit_storage_base_dir=tmp_path,
    )
    assert not diag.runtime_ready
    assert diag.work_unit_storage == "unknown"
    assert any("provider_unrecognized" in issue for issue in diag.issues)


# ── worker count ────────────────────────────────────────────────────────────


@pytest.mark.parametrize("value", ["0", "-1", "2", "abc"])
def test_unsupported_worker_counts_are_not_ready(value: str) -> None:
    os.environ["GATEWAY_WORKERS"] = value
    diag = run_diagnostics(app_config=MEMORY_CONFIG)
    assert not diag.runtime_ready
    assert any("supported" in issue for issue in diag.issues)


def test_single_worker_is_accepted() -> None:
    os.environ["GATEWAY_WORKERS"] = "1"
    diag = run_diagnostics(app_config=MEMORY_CONFIG)
    assert diag.worker_count == 1


def test_missing_worker_defaults_to_one() -> None:
    # When GATEWAY_WORKERS is absent, normalize_gateway_workers defaults to 1.
    diag = run_diagnostics(app_config=MEMORY_CONFIG)
    assert diag.worker_count == 1


# ── entry readiness tri-state ───────────────────────────────────────────────


def test_entry_defaults_to_ready_with_no_checks() -> None:
    diag = run_diagnostics(
        expected_fingerprint=capture_startup_fingerprint(MEMORY_CONFIG, worker_value="1"),
        app_config=MEMORY_CONFIG,
    )
    assert diag.entry.status == "ready"


def test_entry_knows_not_ready_when_any_issue_exists() -> None:
    def _not_ready() -> EntryState:
        return EntryState(status="not_ready", issues=("entry missing",))

    os.environ["GATEWAY_WORKERS"] = "1"
    fp = capture_startup_fingerprint(MEMORY_CONFIG, worker_value="1")
    diag = run_diagnostics(expected_fingerprint=fp, app_config=MEMORY_CONFIG, entry_checks=[_not_ready])
    assert diag.entry.status == "not_ready"


def test_entry_unknown_when_only_unknown_exists() -> None:
    def _unknown() -> EntryState:
        return EntryState(status="unknown", issues=("cannot attribute",))

    os.environ["GATEWAY_WORKERS"] = "1"
    fp = capture_startup_fingerprint(MEMORY_CONFIG, worker_value="1")
    diag = run_diagnostics(expected_fingerprint=fp, app_config=MEMORY_CONFIG, entry_checks=[_unknown])
    assert diag.entry.status == "unknown"


# ── credential redaction ────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "secret",
    [
        "postgres://user:pass@host:5432/db",
        "sk-abcdef1234567890token",
        "api_key: supersecretvalue",
        "/Users/bob/secrets/keys.json,auth_token=abc123",
        "sqlite:////Users/alice/store.db",
    ],
)
def test_redacted_provider_connection_and_issues_never_expose_secrets(secret: str) -> None:
    # Even if an issue string carried a secret (unlikely in production), the
    # diagnostic output must never leak. We test that the redact helpers cover
    # known shapes.
    from deerflow_deep_research.runtime.diagnostics import _redact

    redacted = _redact(secret)
    assert "[redacted]" in redacted or secret not in redacted
    assert "pass" not in redacted
