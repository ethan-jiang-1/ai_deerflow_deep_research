"""Canonical startup-only configuration fingerprints.

@impl DEC-001
@impl RUI-004
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from deerflow_deep_research.runtime.checkpoint import resolve_effective_provider

FINGERPRINT_VERSION = "v1"
_FINGERPRINT_PATTERN = re.compile(r"^v1:[0-9a-f]{64}$")


class StartupSnapshotError(ValueError):
    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"[{code}] {detail}")
        self.code = code
        self.detail = detail


@dataclass(frozen=True)
class WorkerSelection:
    normalized: int | None
    supported: bool
    issue: str | None = None


def normalize_gateway_workers(raw: str | None) -> WorkerSelection:
    """Normalize the same value selected by ``${GATEWAY_WORKERS:-1}``."""

    effective = "1" if raw is None or raw == "" else raw
    try:
        normalized = int(effective, 10)
    except (TypeError, ValueError):
        return WorkerSelection(None, False, "worker_count_invalid")
    if normalized != 1:
        return WorkerSelection(normalized, False, "worker_count_unsupported")
    return WorkerSelection(1, True)


def _digest_scalar(value: str) -> dict[str, str]:
    return {"sha256": hashlib.sha256(value.encode("utf-8")).hexdigest(), "type": "string"}


def _sealed(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _sealed(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_sealed(item) for item in value]
    if isinstance(value, Path):
        return _digest_scalar(str(value))
    if isinstance(value, str):
        return _digest_scalar(value)
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return _digest_scalar(repr(value))


def _model_data(value: Any) -> Any:
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        return model_dump(mode="json")
    if isinstance(value, dict):
        return value
    return vars(value)


def canonical_startup_payload(app_config, *, worker_value: str | None) -> str:
    """Return deterministic typed startup data containing no raw string values."""

    provider = resolve_effective_provider(app_config)
    workers = normalize_gateway_workers(worker_value)
    payload = {
        "schema_version": 1,
        "provider": {
            "kind": provider.kind,
            "source": provider.source,
            "durability": provider.durability,
            "issue": provider.issue,
            "connection": _sealed(provider.connection),
        },
        "sandbox": _sealed(_model_data(app_config.sandbox)),
        "workers": {
            "normalized": workers.normalized,
            "supported": workers.supported,
            "issue": workers.issue,
        },
    }
    return json.dumps(payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True)


def capture_startup_fingerprint(app_config, *, worker_value: str | None) -> str:
    payload = canonical_startup_payload(app_config, worker_value=worker_value)
    return f"{FINGERPRINT_VERSION}:{hashlib.sha256(payload.encode('utf-8')).hexdigest()}"


def parse_startup_fingerprint(value: str | None) -> str:
    if value is None or value == "":
        raise StartupSnapshotError("fingerprint_missing", "startup fingerprint is required")
    if not _FINGERPRINT_PATTERN.fullmatch(value):
        version = value.partition(":")[0]
        if version.startswith("v") and version != FINGERPRINT_VERSION:
            raise StartupSnapshotError("fingerprint_version", "startup fingerprint version is unsupported")
        raise StartupSnapshotError("fingerprint_malformed", "startup fingerprint is malformed")
    return value


def verify_startup_fingerprint(expected: str | None, app_config, *, worker_value: str | None) -> None:
    parsed = parse_startup_fingerprint(expected)
    actual = capture_startup_fingerprint(app_config, worker_value=worker_value)
    if not hmac.compare_digest(parsed, actual):
        raise StartupSnapshotError("restart_required", "startup-only configuration changed after process start")


def _emit_container_fingerprint() -> int:
    """Print the container-effective startup fingerprint for the Compose prelude.

    Reads the effective AppConfig and normalized worker count from the process
    environment the Gateway container will inherit, then writes the strict
    ``v1:<64 hex>`` fingerprint to stdout so the launch command can export it as
    ``DEER_FLOW_DEEP_RESEARCH_STARTUP_FINGERPRINT``. It never logs config content.
    """
    import os

    from deerflow.config.app_config import AppConfig

    config_path = os.environ.get("DEER_FLOW_CONFIG_PATH")
    if not config_path:
        raise StartupSnapshotError("config_target_missing", "DEER_FLOW_CONFIG_PATH is required")
    app_config = AppConfig.from_file(config_path)
    print(capture_startup_fingerprint(app_config, worker_value=os.environ.get("GATEWAY_WORKERS")))
    return 0


__all__ = [
    "FINGERPRINT_VERSION",
    "StartupSnapshotError",
    "WorkerSelection",
    "canonical_startup_payload",
    "capture_startup_fingerprint",
    "normalize_gateway_workers",
    "parse_startup_fingerprint",
    "verify_startup_fingerprint",
]


if __name__ == "__main__":
    raise SystemExit(_emit_container_fingerprint())
