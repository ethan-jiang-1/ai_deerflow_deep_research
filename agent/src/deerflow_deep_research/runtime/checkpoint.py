"""Resolve the effective DeerFlow checkpoint provider and derive namespaces.

@impl RUI-005
@impl RUI-003
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Literal
from urllib.parse import parse_qs, urlsplit

ProviderKind = Literal["memory", "sqlite", "postgres"]
ProviderSource = Literal["legacy_checkpointer", "database", "default"]
Durability = Literal["same_process", "restart_durable", "unavailable"]

# Infrastructure-probe checkpoint topology/namespace. It stays distinct from any
# future fake-research graph so old probe rows can never be read as research
# state. The digest domain also separates the nested probe checkpoint identity
# from the outer lead-agent thread id.
INFRA_PROBE_GRAPH = "infra-probe"
INFRA_PROBE_GRAPH_VERSION = "v1"
INFRA_PROBE_CHECKPOINT_NS = f"{INFRA_PROBE_GRAPH}/{INFRA_PROBE_GRAPH_VERSION}"
_INFRA_PROBE_DIGEST_DOMAIN = "deep-research/infra-probe"
_INFRA_PROBE_KEY_SCHEMA = 1
SUPPORTED_PROBE_KEY_SCHEMAS = frozenset({_INFRA_PROBE_KEY_SCHEMA})
RESEARCH_CHECKPOINT_NS = "deep-research/research/v1"
_RESEARCH_DIGEST_DOMAIN = "deep-research/research"
_RESEARCH_KEY_SCHEMA = 1


class CheckpointNamespaceError(ValueError):
    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"[{code}] {detail}")
        self.code = code
        self.detail = detail


@dataclass(frozen=True)
class ProviderSelection:
    """One effective provider selection without owning its resource lifecycle."""

    kind: ProviderKind
    source: ProviderSource
    connection: str | None
    durability: Durability
    issue: str | None = None


def _sqlite_is_memory(connection: str) -> bool:
    normalized = connection.strip()
    if normalized == ":memory:":
        return True
    parsed = urlsplit(normalized)
    if parsed.scheme.lower() != "file":
        return False
    return parse_qs(parsed.query).get("mode", [""])[-1].lower() == "memory" or parsed.path == ":memory:"


def _selection(
    *,
    kind: ProviderKind,
    source: ProviderSource,
    connection: str | None,
) -> ProviderSelection:
    if kind == "memory":
        return ProviderSelection(kind, source, None, "same_process")
    if kind == "postgres":
        normalized = connection.strip() if connection else ""
        if not normalized:
            return ProviderSelection(kind, source, None, "unavailable", "postgres_connection_missing")
        return ProviderSelection(kind, source, normalized, "restart_durable")
    normalized = connection or "store.db"
    durability: Durability = "same_process" if _sqlite_is_memory(normalized) else "restart_durable"
    return ProviderSelection(kind, source, normalized, durability)


def resolve_effective_provider(app_config) -> ProviderSelection:
    """Mirror ``make_checkpointer(app_config)`` precedence without opening a provider."""

    legacy = getattr(app_config, "checkpointer", None)
    if legacy is not None:
        return _selection(
            kind=legacy.type,
            source="legacy_checkpointer",
            connection=getattr(legacy, "connection_string", None),
        )

    database = getattr(app_config, "database", None)
    if database is None:
        return ProviderSelection("memory", "default", None, "same_process")
    if database.backend == "memory":
        return ProviderSelection("memory", "database", None, "same_process")
    if database.backend == "sqlite":
        return _selection(
            kind="sqlite",
            source="database",
            connection=database.checkpointer_sqlite_path,
        )
    return _selection(
        kind="postgres",
        source="database",
        connection=database.postgres_url,
    )


def validate_probe_key_schema(schema_version: int) -> int:
    """Reject an unsupported probe checkpoint-key schema version, fail closed."""
    if schema_version not in SUPPORTED_PROBE_KEY_SCHEMAS:
        raise CheckpointNamespaceError("schema_unsupported", "unsupported probe checkpoint-key schema version")
    return schema_version


def _length_prefixed(value: str) -> bytes:
    encoded = value.encode("utf-8")
    return len(encoded).to_bytes(8, "big") + encoded


def derive_probe_thread_key(
    *,
    effective_user_id: str,
    outer_thread_id: str,
    probe_id: str,
) -> str:
    """Derive the internal probe checkpoint thread key.

    The key is a domain-prefixed full SHA-256 digest over a versioned,
    length-prefixed canonical tuple of trusted scope plus the opaque probe id.
    Length prefixing removes delimiter ambiguity so distinct scopes cannot
    collide; the digest is an internal key that is never accepted from a caller.
    """
    for label, value in (
        ("effective_user_id", effective_user_id),
        ("outer_thread_id", outer_thread_id),
        ("probe_id", probe_id),
    ):
        if not isinstance(value, str) or not value:
            raise CheckpointNamespaceError("scope_invalid", f"{label} must be a non-empty string")
    payload = b"".join(
        (
            validate_probe_key_schema(_INFRA_PROBE_KEY_SCHEMA).to_bytes(2, "big"),
            _length_prefixed(_INFRA_PROBE_DIGEST_DOMAIN),
            _length_prefixed(effective_user_id),
            _length_prefixed(outer_thread_id),
            _length_prefixed(probe_id),
        )
    )
    digest = hashlib.sha256(payload).hexdigest()
    return f"{_INFRA_PROBE_DIGEST_DOMAIN}:{digest}"


def derive_research_thread_key(
    *,
    effective_user_id: str,
    outer_thread_id: str,
    research_id: str,
) -> str:
    for label, value in (
        ("effective_user_id", effective_user_id),
        ("outer_thread_id", outer_thread_id),
        ("research_id", research_id),
    ):
        if not isinstance(value, str) or not value:
            raise CheckpointNamespaceError("scope_invalid", f"{label} must be a non-empty string")
    payload = b"".join(
        (
            _RESEARCH_KEY_SCHEMA.to_bytes(2, "big"),
            _length_prefixed(_RESEARCH_DIGEST_DOMAIN),
            _length_prefixed(effective_user_id),
            _length_prefixed(outer_thread_id),
            _length_prefixed(research_id),
        )
    )
    return f"{_RESEARCH_DIGEST_DOMAIN}:{hashlib.sha256(payload).hexdigest()}"


__all__ = [
    "INFRA_PROBE_CHECKPOINT_NS",
    "INFRA_PROBE_GRAPH",
    "INFRA_PROBE_GRAPH_VERSION",
    "SUPPORTED_PROBE_KEY_SCHEMAS",
    "CheckpointNamespaceError",
    "Durability",
    "ProviderKind",
    "ProviderSelection",
    "ProviderSource",
    "derive_probe_thread_key",
    "derive_research_thread_key",
    "resolve_effective_provider",
    "validate_probe_key_schema",
]
