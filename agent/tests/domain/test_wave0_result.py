"""Wave0 source-intake result-contract model.

@impl WAN-003
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from deerflow_deep_research.domain.work_units import Wave0SourceIntakeResult, Wave0SourceMeta

RESEARCH_ID = "r_" + "A" * 43
WORK_ID = "g0_wave0_w0000"
ATTEMPT_ID = "g0_wave0_w0000_a00"
SPEC_HASH = "h_" + "B" * 43
CONTENT_REF = f"workspace/deep-research/{RESEARCH_ID}/evidence/source.json"


def _source(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "source_id": "source:1",
        "canonical_url": "https://example.com/path",
        "title": "Example source",
        "content_ref": CONTENT_REF,
        "fetch_status": "fetched",
    }
    payload.update(overrides)
    return payload


def _result(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema_version": 1,
        "research_id": RESEARCH_ID,
        "generation": 0,
        "phase": "wave0",
        "work_id": WORK_ID,
        "attempt_id": ATTEMPT_ID,
        "worker_role": "wave0_intake",
        "spec_hash": SPEC_HASH,
        "result_contract": "wave0.source-intake",
        "output_paths": ("claims.json",),
        "source_ids": ("source:1",),
        "sources": [_source()],
        "baseline_facts": ("Lithium grid batteries are dispatchable.",),
        "limitations": "",
    }
    payload.update(overrides)
    return payload


def test_wave0_result_is_frozen_extra_forbid_with_schema_version_one() -> None:
    doc = Wave0SourceIntakeResult.model_validate(_result())
    assert doc.schema_version == 1
    assert doc.result_contract == "wave0.source-intake"
    assert doc.sources[0].fetch_status == "fetched"
    with pytest.raises(ValidationError):
        Wave0SourceIntakeResult.model_validate(_result(unexpected=True))
    with pytest.raises(ValidationError):
        doc.limitations = "changed"  # type: ignore[misc]


def test_wave0_result_rejects_non_canonical_url_and_bad_content_ref() -> None:
    with pytest.raises(ValidationError, match="canonical_url"):
        Wave0SourceMeta.model_validate(_source(canonical_url="HTTPS://Example.com:443/path/#frag"))
    with pytest.raises(ValidationError):
        Wave0SourceMeta.model_validate(_source(content_ref="/etc/passwd"))


def test_wave0_result_source_ids_must_match_sources() -> None:
    with pytest.raises(ValidationError, match="source_ids_mismatch"):
        Wave0SourceIntakeResult.model_validate(_result(source_ids=("source:1", "source:2")))


def test_wave0_result_attempt_id_identity_is_enforced() -> None:
    with pytest.raises(ValidationError, match="attempt_id_identity_mismatch"):
        Wave0SourceIntakeResult.model_validate(_result(work_id="g0_wave0_w0001"))


def test_wave0_result_bounds_are_enforced() -> None:
    with pytest.raises(ValidationError):
        Wave0SourceIntakeResult.model_validate(_result(baseline_facts=["x" * 513]))
    with pytest.raises(ValidationError):
        Wave0SourceIntakeResult.model_validate(_result(limitations="y" * 2049))
    with pytest.raises(ValidationError):
        Wave0SourceMeta.model_validate(_source(title="z" * 257))


def test_wave0_result_output_paths_are_canonical_sorted() -> None:
    with pytest.raises(ValidationError, match="output_paths"):
        Wave0SourceIntakeResult.model_validate(_result(output_paths=("b.json", "a.json")))
