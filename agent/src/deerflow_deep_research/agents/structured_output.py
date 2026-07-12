"""Validated, redacted node result projection.

@impl NOA-005

The bridge never returns a phase agent's raw output. Model output is validated
and normalized into a typed ``NodeExecutionResult``: the summary is bounded to
the policy's structured-result byte cap, artifact references must be well-formed
and contained by the node's virtual roots, and failure detail is redacted of
paths, identities, and secret-like tokens. Malformed output is a failure, never a
partial success.
"""

from __future__ import annotations

import re

from deerflow_deep_research.agents.policies import ExecutionPolicy, path_within_roots
from deerflow_deep_research.domain.context import ArtifactRef, NodeExecutionResult
from deerflow_deep_research.domain.enums import NodeFinishReason

_SECRET_PATTERNS = [
    re.compile(r"(?i)\b(?:sk|pk|ghp|xox[baprs])[-_][A-Za-z0-9]{8,}"),
    re.compile(r"(?i)(api[_-]?key|token|secret|password)\s*[:=]\s*\S+"),
    re.compile(r"postgres(?:ql)?://\S+"),
    re.compile(r"/(?:Users|home|srv|mnt/host)/\S+"),
]
_MAX_ERROR_CHARS = 512


def _truncate_bytes(text: str, limit: int) -> str:
    encoded = text.encode("utf-8")
    if len(encoded) <= limit:
        return text
    return encoded[:limit].decode("utf-8", "ignore")


def redact(text: str) -> str:
    """Strip secret-like tokens and host paths from model-facing failure detail."""
    redacted = text
    for pattern in _SECRET_PATTERNS:
        redacted = pattern.sub("[redacted]", redacted)
    return _truncate_bytes(redacted, _MAX_ERROR_CHARS)


def validate_artifact_refs(refs: tuple[ArtifactRef, ...], *, allowed_roots: tuple[str, ...]) -> None:
    for ref in refs:
        if not path_within_roots(ref.virtual_path, allowed_roots):
            raise ValueError(f"artifact ref escapes node roots: {ref.artifact_id}")


def project_success(
    summary: str,
    artifact_refs: tuple[ArtifactRef, ...],
    *,
    policy: ExecutionPolicy,
) -> NodeExecutionResult:
    allowed_roots = (*policy.read_roots, *policy.write_roots)
    validate_artifact_refs(artifact_refs, allowed_roots=allowed_roots)
    bounded_summary = _truncate_bytes(summary, policy.budget.structured_result_bytes)
    return NodeExecutionResult(
        finish_reason=NodeFinishReason.SUCCESS,
        summary=bounded_summary,
        artifact_refs=artifact_refs,
    )


def project_failure(finish_reason: NodeFinishReason, *, error_code: str, detail: str = "") -> NodeExecutionResult:
    return NodeExecutionResult(
        finish_reason=finish_reason,
        summary=redact(detail) if detail else "",
        error_code=error_code,
    )


__all__ = ["project_failure", "project_success", "redact", "validate_artifact_refs"]
