"""Pure bootstrap marker contract, store protocol, and binding validation.

@impl BON-001
@impl BON-002

The bootstrap node establishes a minimal research bundle directory and a schema/version
marker bound to the checkpointed control state; this module owns the frozen marker contract,
the runtime-checkable store protocol the node consumes, and the pure binding validation that
reuses gate-kernel ``FailureCode`` values. It performs no I/O and no mutation (GAK-006 style).
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from typing import Any, Literal, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

from deerflow_deep_research.domain.failure_codes import FailureCode
from deerflow_deep_research.domain.gate import Failure
from deerflow_deep_research.domain.lifecycle import RESEARCH_ID_PATTERN

BOOTSTRAP_MARKER_SCHEMA_VERSION = 1

_RESEARCH_ID_RE = re.compile(RESEARCH_ID_PATTERN)
_REQUEST_DIGEST_RE = re.compile(r"^d_[A-Za-z0-9_-]{43}$")


class _FrozenModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class BootstrapMarker(_FrozenModel):
    """Versioned on-disk marker binding a research bundle to its checkpoint.

    ``schema_version`` is the marker format version (independent of the checkpoint's
    ``schema_version``); ``state_schema_version`` records the checkpoint schema version the
    bundle was established under, so a stale marker from an incompatible state version is
    detected at binding validation.
    """

    schema_version: Literal[BOOTSTRAP_MARKER_SCHEMA_VERSION] = BOOTSTRAP_MARKER_SCHEMA_VERSION
    research_id: str = Field(pattern=RESEARCH_ID_PATTERN)
    start_message_id: str = Field(min_length=1, max_length=256)
    request_digest: str = Field(pattern=r"^d_[A-Za-z0-9_-]{43}$")
    state_schema_version: int = Field(ge=1, le=99)

    def canonical_json(self) -> bytes:
        return json.dumps(
            self.model_dump(mode="json"),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")

    @classmethod
    def from_canonical_json(cls, data: bytes | str) -> BootstrapMarker:
        if isinstance(data, str):
            raw = data
        elif isinstance(data, (bytes, bytearray)):
            raw = data.decode("utf-8")
        else:
            raise ValueError("marker_json_invalid")
        try:
            payload = json.loads(raw)
        except ValueError as exc:
            raise ValueError("marker_json_invalid") from exc
        if not isinstance(payload, dict):
            raise ValueError("marker_json_invalid")
        return cls.model_validate(payload)


@runtime_checkable
class BootstrapBundleStoreProtocol(Protocol):
    """Runtime-owned capability that establishes and reads the bootstrap bundle marker."""

    async def establish_bundle(self, marker: BootstrapMarker) -> None: ...

    async def read_marker(self) -> BootstrapMarker | None: ...


def validate_bootstrap_binding(
    marker: BootstrapMarker,
    checkpoint: Mapping[str, Any],
) -> Failure | None:
    """Return a typed ``Failure`` if *marker* is not bound to *checkpoint*, else ``None``.

    Pure: performs no I/O and no mutation. Compares the marker's bound identity to the
    checkpoint's ``research_id`` / ``start_message_id`` / ``request_digest`` and the marker's
    ``state_schema_version`` to the checkpoint's ``schema_version``.
    """
    if not isinstance(marker, BootstrapMarker):
        raise TypeError("marker_required")
    if marker.research_id != checkpoint.get("research_id"):
        return Failure(
            code=FailureCode.IDENTITY_MISMATCH,
            rule_name="bootstrap_binding",
            description="research_id mismatch",
        )
    if marker.start_message_id != checkpoint.get("start_message_id"):
        return Failure(
            code=FailureCode.IDENTITY_MISMATCH,
            rule_name="bootstrap_binding",
            description="start_message_id mismatch",
        )
    if marker.request_digest != checkpoint.get("request_digest"):
        return Failure(
            code=FailureCode.IDENTITY_MISMATCH,
            rule_name="bootstrap_binding",
            description="request_digest mismatch",
        )
    if marker.state_schema_version != checkpoint.get("schema_version"):
        return Failure(
            code=FailureCode.SCHEMA_VERSION_UNSUPPORTED,
            rule_name="bootstrap_binding",
            description="state_schema_version mismatch",
        )
    return None


__all__ = [
    "BOOTSTRAP_MARKER_SCHEMA_VERSION",
    "BootstrapBundleStoreProtocol",
    "BootstrapMarker",
    "validate_bootstrap_binding",
]
