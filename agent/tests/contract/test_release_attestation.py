"""Committed release attestation schema, provenance, and sensitivity.

@impl EVH-005
@impl EVH-010
"""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest

from tests.assets.release_attestation import (
    RELEASE_INVARIANTS,
    load_release_attestation,
    scan_release_attestation,
    validate_attestation_source_run,
    validate_release_attestation,
)

ATTESTATION = Path("docs/release-attestation-2026-07-17.json")


def test_committed_release_attestation_preserves_frozen_accepted_evidence() -> None:
    attestation = load_release_attestation(ATTESTATION)

    assert attestation["source_report_sha256"] == "36f41ca7c631320d05205f26afba9fbddcc0652e8f8323a7832e7816b7828146"
    assert attestation["attestation_base_revision"] == "665ca33575b0d7eb3a408d68956d0ac7b2669d47"
    assert attestation["run_revision"] == "unknown"
    assert attestation["attestation_base_revision"] != attestation["run_revision"]
    assert attestation["source_run"]["hard_invariants"] == {name: True for name in RELEASE_INVARIANTS}
    assert attestation["source_archive_scan"]["target_scope"] == [
        "agent/.reports/live",
        "agent/.reports/release",
    ]


@pytest.mark.parametrize(
    ("mutation", "error"),
    [
        (lambda value: value.pop("run_revision"), "release_attestation_fields_invalid"),
        (lambda value: value["source_run"]["hard_invariants"].pop("cleanup_complete"), "release_invariants_invalid"),
        (lambda value: value.update(run_revision=value["attestation_base_revision"]), "run_revision_invalid"),
        (
            lambda value: value["source_archive_scan"].update(source_locator="unknown"),
            "archive_scan_provenance_invalid",
        ),
        (lambda value: value["source_run"].update(executed_at="2026-07-17T00:00:00Z"), "source_run_fields_invalid"),
    ],
)
def test_release_attestation_rejects_minimal_schema_and_provenance_violations(mutation, error) -> None:
    value = deepcopy(json.loads(ATTESTATION.read_text(encoding="utf-8")))
    mutation(value)
    with pytest.raises(ValueError, match=error):
        validate_release_attestation(value)


def test_release_attestation_scan_catches_known_sensitive_fixture(tmp_path) -> None:
    invalid = tmp_path / "known-sensitive.json"
    invalid.write_text(json.dumps({"provider_url": "https://private.example/source"}), encoding="utf-8")

    with pytest.raises(ValueError, match="release_attestation_sensitive"):
        scan_release_attestation(invalid)


def test_release_attestation_scan_passes_committed_artifact() -> None:
    assert scan_release_attestation(ATTESTATION) == {
        "credential_values_absent": True,
        "raw_host_paths_absent": True,
    }


def test_release_attestation_source_run_matches_hashed_local_source_when_present() -> None:
    source_path = Path(".reports/release/release-full-real-acceptance.json")
    if not source_path.exists():
        return
    attestation = load_release_attestation(ATTESTATION)
    source = json.loads(source_path.read_text(encoding="utf-8"))

    validate_attestation_source_run(attestation, source)


def test_release_attestation_source_run_mismatch_is_rejected() -> None:
    attestation = load_release_attestation(ATTESTATION)
    source = {
        "attempt_count": 1,
        "retry_count": 0,
        "hard_invariants": {name: True for name in RELEASE_INVARIANTS},
        "outcome_summary": {"accepted_count": 999, "citation_claim_count": 2, "citation_ref_count": 2},
        "attempts": [
            {
                "input_tokens": 37597,
                "output_tokens": 18591,
                "tool_calls": 12,
                "wall_time_seconds": 286.1884355,
            }
        ],
    }
    with pytest.raises(ValueError, match="attestation_source_run_mismatch"):
        validate_attestation_source_run(attestation, source)
