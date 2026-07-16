"""Deterministic materializers for critic review artifacts.

Each materializer validates that all referenced source ids are present in the
assigned evidence set before writing, then writes canonical JSON to the sandbox.

@impl EVC-004
"""

from __future__ import annotations

from collections.abc import Container
from pathlib import Path

from deerflow_deep_research.domain.critics import (
    ClaimVerifierResult,
    SourceDiagnosticResult,
)
from deerflow_deep_research.domain.work_units import canonical_json_bytes


def _validate_source_refs(
    refs: tuple[str, ...],
    allowed_source_ids: Container[str],
    label: str,
) -> None:
    for ref in refs:
        if ref not in allowed_source_ids:
            raise ValueError(f"source_not_in_assigned_{label}: {ref}")


def materialize_source_diagnostic(
    result: SourceDiagnosticResult,
    node_attempt_id: str,
    workspace_root: Path,
    *,
    allowed_source_ids: Container[str],
) -> None:
    """Write ``SourceDiagnosticResult`` to the sandbox.

    Validates every source id in the result against *allowed_source_ids*
    before writing. Raises ``ValueError`` for non-assigned refs.
    """
    _validate_source_refs(result.source_ids, allowed_source_ids, "source_ids")
    for source in result.sources:
        if source.source_id not in allowed_source_ids:
            raise ValueError(f"source_not_in_assigned_sources: {source.source_id}")
    dest = workspace_root / "critic" / node_attempt_id / "source-diagnostic.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(canonical_json_bytes(result))


def materialize_claim_verifier(
    result: ClaimVerifierResult,
    node_attempt_id: str,
    workspace_root: Path,
    *,
    allowed_source_ids: Container[str],
) -> None:
    """Write ``ClaimVerifierResult`` to the sandbox.

    Validates every support_ref and counter_ref against *allowed_source_ids*.
    Raises ``ValueError`` for dangling refs.
    """
    for claim in result.claims:
        _validate_source_refs(claim.support_refs, allowed_source_ids, "support_refs")
        _validate_source_refs(claim.counter_refs, allowed_source_ids, "counter_refs")
    dest = workspace_root / "critic" / node_attempt_id / "claim-verifier.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(canonical_json_bytes(result))
