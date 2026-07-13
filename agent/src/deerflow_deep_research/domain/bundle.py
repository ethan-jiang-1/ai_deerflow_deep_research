"""Minimal research bundle layout and path-containment contract.

@impl REG-009
@impl REG-010

The research bundle is rooted at ``workspace/deep-research/<research_id>/`` and scopes
every sandbox write. A worker writes only its own
``work/<work_id>/<attempt_id>/`` directory and controlled cache regions; writes outside
the assigned research and attempt root fail closed. ``diagnostics/gate-attempts.jsonl``
is audit-only and is never a phase cursor (the checkpointed ``ResearchState`` is the sole
control authority).

This module defines the contract only; the fake graph writes no artifacts. Real worker
writes arrive with later changes and enforce containment through this contract.
"""

from __future__ import annotations

import posixpath
import re
from urllib.parse import urlsplit, urlunsplit

RESEARCH_ID_RE = re.compile(r"^r_[A-Za-z0-9_-]{43}$")
WORK_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
ATTEMPT_ID_RE = re.compile(r"^g\d+-[a-z0-9_]+-a\d+$")

BUNDLE_ROOT = "workspace/deep-research"
REQUEST_SUBTREE = "request"
WORK_SUBTREE = "work"
EVIDENCE_SUBTREE = "evidence"
SYNTHESIS_SUBTREE = "synthesis"
REVIEW_SUBTREE = "review"
FINAL_SUBTREE = "final"
DIAGNOSTICS_SUBTREE = "diagnostics"

BUNDLE_SUBTREES = (
    REQUEST_SUBTREE,
    WORK_SUBTREE,
    EVIDENCE_SUBTREE,
    SYNTHESIS_SUBTREE,
    REVIEW_SUBTREE,
    FINAL_SUBTREE,
    DIAGNOSTICS_SUBTREE,
)

DIAGNOSTICS_GATE_ATTEMPTS = "gate-attempts.jsonl"
DIAGNOSTICS_AUDIT_ONLY = frozenset({DIAGNOSTICS_GATE_ATTEMPTS})


def bundle_root(research_id: str) -> str:
    if not RESEARCH_ID_RE.fullmatch(research_id):
        raise ValueError("research_id_invalid")
    return f"{BUNDLE_ROOT}/{research_id}"


def attempt_dir(research_id: str, work_id: str, attempt_id: str) -> str:
    """Return the canonical worker write root for one work/attempt."""
    if not RESEARCH_ID_RE.fullmatch(research_id):
        raise ValueError("research_id_invalid")
    if not WORK_ID_RE.fullmatch(work_id):
        raise ValueError("work_id_invalid")
    if not ATTEMPT_ID_RE.fullmatch(attempt_id):
        raise ValueError("attempt_id_invalid")
    return f"{BUNDLE_ROOT}/{research_id}/{WORK_SUBTREE}/{work_id}/{attempt_id}"


def diagnostics_path(research_id: str, name: str = DIAGNOSTICS_GATE_ATTEMPTS) -> str:
    if name not in DIAGNOSTICS_AUDIT_ONLY:
        raise ValueError("diagnostic_unknown")
    return f"{bundle_root(research_id)}/{DIAGNOSTICS_SUBTREE}/{name}"


def is_audit_only(path: str) -> bool:
    """A diagnostics path is audit-only and is never a phase cursor."""
    normalized = _normalize(path)
    marker = f"/{DIAGNOSTICS_SUBTREE}/"
    if marker not in normalized:
        return False
    tail = normalized.split(marker, 1)[1]
    return any(tail.startswith(name) for name in DIAGNOSTICS_AUDIT_ONLY)


def _normalize(path: str) -> str:
    if not isinstance(path, str) or not path:
        raise ValueError("path_invalid")
    normalized = posixpath.normpath(path)
    # Reject absolute paths and any residual parent traversal that would escape the root.
    if posixpath.isabs(normalized) or normalized.startswith(".."):
        raise ValueError("path_not_contained")
    return normalized


def resolve_contained_path(
    write_path: str,
    *,
    research_id: str,
    work_id: str | None = None,
    attempt_id: str | None = None,
) -> str:
    """Resolve a worker write path and fail closed if it escapes the assigned root.

    With ``work_id`` and ``attempt_id`` the allowed root is the attempt directory; a
    worker may write only there (plus controlled cache regions, represented by the
    attempt root). Without them the allowed root is the research bundle root, used by
    controller-level writes. Any path that resolves outside the root via ``..`` or an
    absolute escape is rejected.
    """
    normalized = _normalize(write_path)
    if work_id is not None and attempt_id is not None:
        root = attempt_dir(research_id, work_id, attempt_id)
    else:
        root = bundle_root(research_id)
    root_prefix = root.rstrip("/") + "/"
    if normalized == root or normalized.startswith(root_prefix):
        return normalized
    raise ValueError("path_not_contained")


def canonicalize_source_url(url: str) -> str:
    """Canonicalize a source URL so duplicates collapse (REG-010).

    Strips the fragment, lower-cases the host, and drops trailing slashes from the path
    so the same source is not recorded twice under trivially different URLs.
    """
    if not isinstance(url, str) or not url:
        raise ValueError("source_url_invalid")
    parts = urlsplit(url)
    if not parts.scheme or not parts.netloc:
        raise ValueError("source_url_invalid")
    scheme = parts.scheme.lower()
    netloc = parts.netloc.lower()
    path = parts.path.rstrip("/") or "/"
    return urlunsplit((scheme, netloc, path, parts.query, ""))


def dedupe_source_urls(urls: list[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    ordered: list[str] = []
    for url in urls:
        canonical = canonicalize_source_url(url)
        if canonical in seen:
            continue
        seen.add(canonical)
        ordered.append(canonical)
    return tuple(ordered)


__all__ = [
    "ATTEMPT_ID_RE",
    "BUNDLE_ROOT",
    "BUNDLE_SUBTREES",
    "DIAGNOSTICS_AUDIT_ONLY",
    "DIAGNOSTICS_GATE_ATTEMPTS",
    "DIAGNOSTICS_SUBTREE",
    "EVIDENCE_SUBTREE",
    "FINAL_SUBTREE",
    "RESEARCH_ID_RE",
    "REQUEST_SUBTREE",
    "REVIEW_SUBTREE",
    "SYNTHESIS_SUBTREE",
    "WORK_ID_RE",
    "WORK_SUBTREE",
    "attempt_dir",
    "bundle_root",
    "canonicalize_source_url",
    "dedupe_source_urls",
    "diagnostics_path",
    "is_audit_only",
    "resolve_contained_path",
]
