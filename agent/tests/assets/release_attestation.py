"""Minimal committed release-attestation contract and sensitivity scan.

@impl EVH-005
@impl EVH-010
"""

from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import Any

RELEASE_INVARIANTS = (
    "accepted_evidence_present",
    "checkpoint_isolated",
    "citation_bindings_valid",
    "cleanup_complete",
    "lifecycle_trace_complete",
    "paths_contained",
    "report_artifacts_present",
    "terminal_completed",
)
SOURCE_LOCATOR = "openspec/changes/archive/2026-07-17-evaluate-harden-deep-research-graph/tasks.md#task-6.6"
SOURCE_TARGET_SCOPE = ("agent/.reports/live", "agent/.reports/release")
MAX_ATTESTATION_BYTES = 16 * 1024
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_REVISION_RE = re.compile(r"^[0-9a-f]{40}$")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_SENSITIVE_RE = re.compile(
    r"(?i)(?:https?://|/(?:Users|home|private|tmp)/|(?:api[_-]?key|token|secret|authorization)[\"']?\s*[:=]\s*[\"']?(?!<redacted>)[^\s,}\"]+)"
)


def load_release_attestation(path: Path) -> dict[str, Any]:
    if not isinstance(path, Path):
        raise TypeError("release_attestation_path_required")
    raw = path.read_bytes()
    if not raw or len(raw) > MAX_ATTESTATION_BYTES:
        raise ValueError("release_attestation_size_invalid")
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError("release_attestation_json_invalid") from exc
    validate_release_attestation(value)
    scan_release_attestation(path)
    return value


def validate_release_attestation(value: Any) -> None:
    expected_fields = {
        "schema_version",
        "scenario_id",
        "source_observation_date",
        "source_report_sha256",
        "attestation_base_revision",
        "run_revision",
        "source_run",
        "source_archive_scan",
        "attestation_scan",
    }
    if not isinstance(value, dict) or set(value) != expected_fields:
        raise ValueError("release_attestation_fields_invalid")
    if value["schema_version"] != 1 or value["scenario_id"] != "release-full-real-acceptance":
        raise ValueError("release_attestation_identity_invalid")
    if not isinstance(value["source_observation_date"], str) or not _DATE_RE.fullmatch(
        value["source_observation_date"]
    ):
        raise ValueError("source_observation_date_invalid")
    if not isinstance(value["source_report_sha256"], str) or not _SHA256_RE.fullmatch(value["source_report_sha256"]):
        raise ValueError("source_report_sha256_invalid")
    if not isinstance(value["attestation_base_revision"], str) or not _REVISION_RE.fullmatch(
        value["attestation_base_revision"]
    ):
        raise ValueError("attestation_base_revision_invalid")
    if value["run_revision"] != "unknown" or value["run_revision"] == value["attestation_base_revision"]:
        raise ValueError("run_revision_invalid")
    _validate_source_run(value["source_run"])
    _validate_source_archive_scan(value["source_archive_scan"])
    _validate_attestation_scan(value["attestation_scan"])


def _validate_source_run(value: Any) -> None:
    fields = {
        "attempt_count",
        "retry_count",
        "hard_invariants",
        "accepted_count",
        "citation_claim_count",
        "citation_ref_count",
        "input_tokens",
        "output_tokens",
        "tool_calls",
        "wall_time_seconds",
    }
    if not isinstance(value, dict) or set(value) != fields:
        raise ValueError("source_run_fields_invalid")
    invariants = value["hard_invariants"]
    if not isinstance(invariants, dict) or tuple(sorted(invariants)) != RELEASE_INVARIANTS:
        raise ValueError("release_invariants_invalid")
    if any(result is not True for result in invariants.values()):
        raise ValueError("release_invariants_invalid")
    integer_fields = (
        "attempt_count",
        "retry_count",
        "accepted_count",
        "citation_claim_count",
        "citation_ref_count",
        "input_tokens",
        "output_tokens",
        "tool_calls",
    )
    if any(
        not isinstance(value[field], int) or isinstance(value[field], bool) or value[field] < 0
        for field in integer_fields
    ):
        raise ValueError("source_run_counts_invalid")
    if value["attempt_count"] != 1 or value["retry_count"] != 0:
        raise ValueError("source_run_attempts_invalid")
    if not isinstance(value["wall_time_seconds"], (int, float)) or not 0 < value["wall_time_seconds"] <= 1200:
        raise ValueError("source_run_duration_invalid")


def _validate_source_archive_scan(value: Any) -> None:
    fields = {"source_locator", "target_scope", "credential_values_absent", "raw_host_paths_absent"}
    if not isinstance(value, dict) or set(value) != fields:
        raise ValueError("archive_scan_fields_invalid")
    if value["source_locator"] != SOURCE_LOCATOR or value["target_scope"] != list(SOURCE_TARGET_SCOPE):
        raise ValueError("archive_scan_provenance_invalid")
    if value["credential_values_absent"] is not True or value["raw_host_paths_absent"] is not True:
        raise ValueError("archive_scan_verdict_invalid")


def _validate_attestation_scan(value: Any) -> None:
    fields = {"credential_values_absent", "raw_host_paths_absent"}
    if not isinstance(value, dict) or set(value) != fields:
        raise ValueError("attestation_scan_fields_invalid")
    if value["credential_values_absent"] is not True or value["raw_host_paths_absent"] is not True:
        raise ValueError("attestation_scan_verdict_invalid")


def scan_release_attestation(path: Path) -> dict[str, bool]:
    if not isinstance(path, Path):
        raise TypeError("release_attestation_path_required")
    raw = path.read_bytes()
    if not raw or len(raw) > MAX_ATTESTATION_BYTES:
        raise ValueError("release_attestation_size_invalid")
    text = raw.decode("utf-8", "strict")
    if _SENSITIVE_RE.search(text):
        raise ValueError("release_attestation_sensitive")
    return {"credential_values_absent": True, "raw_host_paths_absent": True}


def validate_attestation_source_run(attestation: dict[str, Any], source: dict[str, Any]) -> None:
    attempts = source.get("attempts")
    outcome = source.get("outcome_summary")
    invariants = source.get("hard_invariants")
    if not isinstance(attempts, list) or len(attempts) != 1 or not isinstance(outcome, dict):
        raise ValueError("attestation_source_run_invalid")
    attempt = attempts[0]
    expected = {
        "attempt_count": source.get("attempt_count"),
        "retry_count": source.get("retry_count"),
        "hard_invariants": invariants,
        "accepted_count": outcome.get("accepted_count"),
        "citation_claim_count": outcome.get("citation_claim_count"),
        "citation_ref_count": outcome.get("citation_ref_count"),
        "input_tokens": attempt.get("input_tokens"),
        "output_tokens": attempt.get("output_tokens"),
        "tool_calls": attempt.get("tool_calls"),
        "wall_time_seconds": attempt.get("wall_time_seconds"),
    }
    attested = attestation.get("source_run")
    if not isinstance(attested, dict):
        raise ValueError("attestation_source_run_mismatch")
    attested_duration = attested.get("wall_time_seconds")
    source_duration = expected.pop("wall_time_seconds")
    attested_without_duration = {key: value for key, value in attested.items() if key != "wall_time_seconds"}
    if attested_without_duration != expected or not (
        isinstance(attested_duration, (int, float))
        and isinstance(source_duration, (int, float))
        and math.isclose(attested_duration, source_duration, rel_tol=0, abs_tol=1e-6)
    ):
        raise ValueError("attestation_source_run_mismatch")


__all__ = [
    "RELEASE_INVARIANTS",
    "load_release_attestation",
    "scan_release_attestation",
    "validate_attestation_source_run",
    "validate_release_attestation",
]
