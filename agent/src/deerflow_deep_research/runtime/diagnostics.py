"""Reusable readiness diagnostics for the Deep Research runtime.

@impl DEC-005

Machine-readable diagnostics consumed by the doctor CLI, the local launcher
prelaunch gate, the Docker Compose pre-uvicorn prelude, and an in-process health
read. Never logs secret-bearing config content, database URLs, API tokens, user
ids, host paths, or startup fingerprints.
"""

from __future__ import annotations

import os
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal

from deerflow_deep_research.runtime.startup_snapshot import (
    FINGERPRINT_VERSION,
    StartupSnapshotError,
    capture_startup_fingerprint,
    normalize_gateway_workers,
    parse_startup_fingerprint,
)

EntryStatus = Literal["ready", "not_ready", "unknown"]

_REDACT_PATTERNS = [
    re.compile(r"(?i)\b(?:sk|pk|ghp|xox[baprs])[-_][A-Za-z0-9]{8,}"),
    re.compile(r"(?i)(api[_-]?key|token|secret|password)\s*[:=]\s*\S+"),
    re.compile(r"postgres(?:ql)?://\S+"),
    re.compile(r"sqlite:///\S+"),
    re.compile(r"(?<=[?&])(?:auth|token|secret|key)=[^&\s]+"),
    re.compile(r"/(?:Users|home|srv)/[^,\s]+"),
]
_STARTUP_FINGERPRINT_ENV = "DEER_FLOW_DEEP_RESEARCH_STARTUP_FINGERPRINT"
_WORKER_COUNT_ENV = "GATEWAY_WORKERS"


def _redact(text: str) -> str:
    redacted = text
    for pattern in _REDACT_PATTERNS:
        redacted = pattern.sub("[redacted]", redacted)
    return redacted


@dataclass(frozen=True)
class EntryState:
    status: EntryStatus
    checks: tuple[str, ...] = ()
    issues: tuple[str, ...] = ()

    @property
    def ready(self) -> bool:
        return self.status == "ready"


@dataclass
class ReadinessDiagnostic:
    """One diagnostic snapshot, never containing secret-bearing content."""

    mode: str  # prelaunch-candidate | in-process
    runtime_ready: bool
    entry: EntryState
    provider_kind: str | None = None
    durability: str | None = None
    fingerprint_version: str | None = None
    worker_count: int | None = None
    checks: list[str] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)
    redacted_provider: str | None = None


def _resolve_app_config() -> Any | None:
    try:
        from deerflow.config.app_config import AppConfig

        config_path = os.environ.get("DEER_FLOW_CONFIG_PATH")
        if config_path:
            return AppConfig.from_file(config_path)
        return AppConfig()
    except Exception:
        return None


def _fingerprint_prelaunch(app_config: Any) -> str | None:
    try:
        return capture_startup_fingerprint(app_config, worker_value=os.environ.get(_WORKER_COUNT_ENV))
    except Exception:
        return None


def _check_worker_count() -> tuple[bool, int | None, list[str]]:
    raw = os.environ.get(_WORKER_COUNT_ENV)
    try:
        selection = normalize_gateway_workers(raw)
    except StartupSnapshotError:
        return False, None, [f"GATEWAY_WORKERS is not supported: {_redact(raw or '[missing]')}"]
    if selection.normalized != 1:
        return False, selection.normalized, [f"only single-worker runtime is supported (saw {selection.normalized})"]
    return True, 1, []


def run_diagnostics(
    *,
    expected_fingerprint: str | None = None,
    app_config: Any = None,
    entry_checks: list[Callable[[], EntryState]] | None = None,
) -> ReadinessDiagnostic:
    """Return a redacted readiness diagnostic.

    ``prelaunch-candidate`` mode is used when ``expected_fingerprint`` is
    supplied: the computed fingerprint is compared to the launcher-captured
    expected value, NOT to the process environment (no Gateway is live).

    ``in-process`` mode is used when ``expected_fingerprint`` is None: the env
    fingerprint from process start is parsed and compared to the live AppConfig.

    ``entry_checks`` are stateless callables that each return an ``EntryState``;
    they represent the public skill and per-user Agent readiness probes that
    configure.py commands but that do not control runtime readiness.
    """
    diag = ReadinessDiagnostic(
        mode="in-process" if expected_fingerprint is None else "prelaunch-candidate",
        runtime_ready=False,
        entry=EntryState(status="ready"),
        fingerprint_version=FINGERPRINT_VERSION,
    )

    if app_config is None:
        app_config = _resolve_app_config()
    if app_config is None:
        diag.issues.append("AppConfig could not be resolved")
        return diag

    try:
        from deerflow_deep_research.runtime.checkpoint import resolve_effective_provider
    except Exception:
        diag.issues.append("runtime checkpoint module is unavailable")
        return diag

    provider = resolve_effective_provider(app_config)
    diag.provider_kind = provider.kind
    diag.durability = provider.durability
    diag.redacted_provider = _redact(provider.connection) if provider.connection else None
    if provider.issue:
        diag.issues.append(provider.issue)

    worker_ok, worker_value, worker_issues = _check_worker_count()
    diag.worker_count = worker_value
    diag.issues.extend(worker_issues)

    if expected_fingerprint is not None:
        # prelaunch-candidate: compare the freshly computed candidate to the
        # launcher-captured expected value, NOT the process environment.
        candidate = _fingerprint_prelaunch(app_config)
        diag.checks.append("fingerprint_candidate")
        if candidate is None:
            diag.issues.append("fingerprint candidate computation failed")
        elif expected_fingerprint != candidate:
            diag.issues.append("fingerprint candidate does not match the launcher-captured value")
        else:
            diag.checks.append("fingerprint_candidate_match")
    else:
        # in-process: verify the env fingerprint from process start against live
        # AppConfig; never silently recompute a missing value.
        env_fp = os.environ.get(_STARTUP_FINGERPRINT_ENV)
        if not env_fp:
            diag.issues.append("startup fingerprint is absent from the process environment")
        else:
            try:
                parse_startup_fingerprint(env_fp)
            except StartupSnapshotError as exc:
                diag.issues.append(f"fingerprint is malformed: {exc.detail}")
            else:
                actual = _fingerprint_prelaunch(app_config)
                if actual is not None and actual != env_fp:
                    diag.issues.append("live AppConfig fingerprint does not match the process-start fingerprint")

    diag.runtime_ready = len(diag.issues) == 0 and worker_ok

    if entry_checks:
        aggregate = "ready"
        all_issues: list[str] = []
        for check in entry_checks:
            result = check()
            if result.status == "not_ready":
                aggregate = "not_ready"
            elif result.status == "unknown" and aggregate == "ready":
                aggregate = "unknown"
            all_issues.extend(result.issues)
        diag.entry = EntryState(status=aggregate, issues=tuple(all_issues))

    return diag


__all__ = ["EntryState", "EntryStatus", "ReadinessDiagnostic", "run_diagnostics"]
