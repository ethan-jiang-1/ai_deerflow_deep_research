"""Canonical research-bundle paths and containment rules.

@impl WOU-003
@impl WOU-004
@impl WOU-006
@impl REG-009
@impl REG-010
"""

from __future__ import annotations

import re
from enum import StrEnum

from deerflow_deep_research.domain.work_units import (
    ATTEMPT_ID_RE,
    RESEARCH_ID_RE,
    WORK_ID_RE,
    canonicalize_source_url,
)

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
EVIDENCE_LEDGER = "submissions.jsonl"
EVIDENCE_LOCK = ".submissions.lock"
MARKER_FILENAME = "marker.json"

_PROBE_TOKEN_RE = re.compile(r"^[0-9a-f]{32}$")
_STAGING_RE = re.compile(r"^\.submissions\.[0-9a-f]{32}\.tmp$")
_ALIAS_PROBE_RE = re.compile(r"^\.work-unit-probe-[0-9a-f]{32}$")
_FS_PROBE_RE = re.compile(r"^\.work-unit-fsprobe-[0-9a-f]{32}\.(?:lock|src|dst)$")
_DPT_CONTROL_NAMES = frozenset({"queue.json", "index.json", "status.json"})


class BundlePathKind(StrEnum):
    CONTENT = "content"
    EVIDENCE = "evidence"
    AUDIT = "audit"
    UNKNOWN = "unknown"


def _require_research_id(research_id: str) -> str:
    if not isinstance(research_id, str) or not RESEARCH_ID_RE.fullmatch(research_id):
        raise ValueError("research_id_invalid")
    return research_id


def _require_probe_token(token: str) -> str:
    if not isinstance(token, str) or not _PROBE_TOKEN_RE.fullmatch(token):
        raise ValueError("probe_token_invalid")
    return token


def _canonical_relative(path: str, *, label: str, max_length: int = 1024) -> str:
    if not isinstance(path, str) or not path or len(path) > max_length or not path.isascii():
        raise ValueError(f"{label}_invalid")
    if path.startswith("/") or path.endswith("/") or "\\" in path or "\x00" in path:
        raise ValueError(f"{label}_invalid")
    if any(part in {"", ".", ".."} for part in path.split("/")):
        raise ValueError(f"{label}_invalid")
    return path


def _require_work_attempt(work_id: str, attempt_id: str) -> tuple[str, str]:
    if not isinstance(work_id, str) or not WORK_ID_RE.fullmatch(work_id):
        raise ValueError("work_id_invalid")
    match = ATTEMPT_ID_RE.fullmatch(attempt_id) if isinstance(attempt_id, str) else None
    if match is None or match.group("work_id") != work_id:
        raise ValueError("attempt_id_invalid")
    return work_id, attempt_id


def bundle_root(research_id: str) -> str:
    return f"{BUNDLE_ROOT}/{_require_research_id(research_id)}"


def marker_path(research_id: str) -> str:
    """Canonical path of the bootstrap schema/version marker under the request subtree."""
    return f"{bundle_root(research_id)}/{REQUEST_SUBTREE}/{MARKER_FILENAME}"


def attempt_dir(research_id: str, work_id: str, attempt_id: str) -> str:
    _require_work_attempt(work_id, attempt_id)
    return f"{bundle_root(research_id)}/{WORK_SUBTREE}/{work_id}/{attempt_id}"


def work_spec_path(research_id: str, work_id: str, attempt_id: str) -> str:
    return f"{attempt_dir(research_id, work_id, attempt_id)}/work-spec.json"


def first_work_spec_path(research_id: str, work_id: str) -> str:
    if not WORK_ID_RE.fullmatch(work_id):
        raise ValueError("work_id_invalid")
    return work_spec_path(research_id, work_id, f"{work_id}_a00")


def result_path(research_id: str, work_id: str, attempt_id: str) -> str:
    return f"{attempt_dir(research_id, work_id, attempt_id)}/result.json"


def output_path(research_id: str, work_id: str, attempt_id: str, relative_output: str) -> str:
    relative = _canonical_relative(relative_output, label="output", max_length=256)
    if relative == "outputs" or relative.startswith("outputs/"):
        raise ValueError("output_must_be_relative_to_outputs")
    return f"{attempt_dir(research_id, work_id, attempt_id)}/outputs/{relative}"


def evidence_ledger_path(research_id: str) -> str:
    return f"{bundle_root(research_id)}/{EVIDENCE_SUBTREE}/{EVIDENCE_LEDGER}"


def evidence_lock_path(research_id: str) -> str:
    return f"{bundle_root(research_id)}/{EVIDENCE_SUBTREE}/{EVIDENCE_LOCK}"


def evidence_staging_path(research_id: str, token: str) -> str:
    return f"{bundle_root(research_id)}/{EVIDENCE_SUBTREE}/.submissions.{_require_probe_token(token)}.tmp"


def is_evidence_staging_name(name: str) -> bool:
    return isinstance(name, str) and _STAGING_RE.fullmatch(name) is not None


def diagnostics_path(research_id: str, name: str = DIAGNOSTICS_GATE_ATTEMPTS) -> str:
    if name != DIAGNOSTICS_GATE_ATTEMPTS:
        raise ValueError("diagnostic_unknown")
    return f"{bundle_root(research_id)}/{DIAGNOSTICS_SUBTREE}/{name}"


def runtime_alias_probe_path(research_id: str, token: str) -> str:
    return f"{bundle_root(research_id)}/{DIAGNOSTICS_SUBTREE}/.work-unit-probe-{_require_probe_token(token)}"


def runtime_fs_probe_paths(research_id: str, token: str) -> tuple[str, str, str]:
    prefix = f"{bundle_root(research_id)}/{DIAGNOSTICS_SUBTREE}/.work-unit-fsprobe-{_require_probe_token(token)}"
    return (f"{prefix}.lock", f"{prefix}.src", f"{prefix}.dst")


def prelaunch_fs_probe_names(token: str) -> tuple[str, str, str]:
    prefix = f".deep-research-work-unit-fsprobe-{_require_probe_token(token)}"
    return (f"{prefix}.lock", f"{prefix}.src", f"{prefix}.dst")


def _normalize_bundle_ref(path: str) -> str:
    canonical = _canonical_relative(path, label="bundle_ref")
    if not canonical.startswith(f"{BUNDLE_ROOT}/"):
        raise ValueError("bundle_ref_invalid")
    parts = canonical.split("/")
    if len(parts) < 4 or not RESEARCH_ID_RE.fullmatch(parts[2]):
        raise ValueError("bundle_ref_invalid")
    return canonical


def bundle_ref_to_virtual(path: str, *, virtual_user_data_root: str = "/mnt/user-data") -> str:
    ref = _normalize_bundle_ref(path)
    if virtual_user_data_root != "/mnt/user-data":
        raise ValueError("virtual_root_invalid")
    return f"{virtual_user_data_root}/{ref}"


def relative_to_workspace_path(path: str) -> str:
    ref = _normalize_bundle_ref(path)
    return ref.removeprefix("workspace/")


def resolve_contained_path(
    write_path: str,
    *,
    research_id: str,
    work_id: str | None = None,
    attempt_id: str | None = None,
) -> str:
    try:
        normalized = _normalize_bundle_ref(write_path)
    except ValueError as exc:
        raise ValueError("path_not_contained") from exc
    if (work_id is None) != (attempt_id is None):
        raise ValueError("path_not_contained")
    try:
        root = (
            attempt_dir(research_id, work_id, attempt_id)
            if work_id is not None and attempt_id is not None
            else bundle_root(research_id)
        )
    except ValueError as exc:
        raise ValueError("path_not_contained") from exc
    if normalized == root or normalized.startswith(f"{root}/"):
        return normalized
    raise ValueError("path_not_contained")


def classify_bundle_path(path: str) -> BundlePathKind:
    try:
        ref = _normalize_bundle_ref(path)
    except ValueError:
        return BundlePathKind.UNKNOWN
    parts = ref.split("/")
    tail = parts[3:]
    if not tail:
        return BundlePathKind.UNKNOWN
    subtree = tail[0]
    if subtree == DIAGNOSTICS_SUBTREE and len(tail) == 2:
        name = tail[1]
        if name == DIAGNOSTICS_GATE_ATTEMPTS or _ALIAS_PROBE_RE.fullmatch(name) or _FS_PROBE_RE.fullmatch(name):
            return BundlePathKind.AUDIT
    if subtree == EVIDENCE_SUBTREE and len(tail) == 2:
        name = tail[1]
        if name == EVIDENCE_LEDGER:
            return BundlePathKind.EVIDENCE
        if name == EVIDENCE_LOCK or _STAGING_RE.fullmatch(name):
            return BundlePathKind.AUDIT
    if subtree == WORK_SUBTREE and len(tail) >= 4:
        work_id, attempt_id = tail[1], tail[2]
        try:
            _require_work_attempt(work_id, attempt_id)
        except ValueError:
            return BundlePathKind.UNKNOWN
        artifact = "/".join(tail[3:])
        if artifact in {"work-spec.json", "result.json"} or artifact.startswith("outputs/"):
            if not any(name in _DPT_CONTROL_NAMES or name.endswith(".queue") for name in tail[3:]):
                return BundlePathKind.CONTENT
    return BundlePathKind.UNKNOWN


def is_audit_only(path: str) -> bool:
    return classify_bundle_path(path) is BundlePathKind.AUDIT


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
    "BundlePathKind",
    "DIAGNOSTICS_GATE_ATTEMPTS",
    "DIAGNOSTICS_SUBTREE",
    "EVIDENCE_LEDGER",
    "EVIDENCE_LOCK",
    "EVIDENCE_SUBTREE",
    "FINAL_SUBTREE",
    "MARKER_FILENAME",
    "RESEARCH_ID_RE",
    "REQUEST_SUBTREE",
    "REVIEW_SUBTREE",
    "SYNTHESIS_SUBTREE",
    "WORK_ID_RE",
    "WORK_SUBTREE",
    "attempt_dir",
    "bundle_ref_to_virtual",
    "bundle_root",
    "canonicalize_source_url",
    "classify_bundle_path",
    "dedupe_source_urls",
    "diagnostics_path",
    "evidence_ledger_path",
    "evidence_lock_path",
    "evidence_staging_path",
    "first_work_spec_path",
    "is_audit_only",
    "marker_path",
    "is_evidence_staging_name",
    "output_path",
    "prelaunch_fs_probe_names",
    "relative_to_workspace_path",
    "resolve_contained_path",
    "result_path",
    "runtime_alias_probe_path",
    "runtime_fs_probe_paths",
    "work_spec_path",
]
