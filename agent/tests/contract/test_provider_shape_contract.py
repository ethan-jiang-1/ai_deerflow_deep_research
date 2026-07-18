"""Provider-shape case and discovery-disposition contracts.

@impl EVH-010
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from tests.assets.evidence import EVIDENCE_CLAIMS, claim_index
from tests.assets.provider_shapes import (
    LIVE_DISCOVERY_DISPOSITIONS,
    RELEASE_DISCOVERY_DISPOSITIONS_01_14,
    RELEASE_DISCOVERY_DISPOSITIONS_15_25,
    DiscoveryDisposition,
    DiscoveryDispositionKind,
    ProviderShapeCase,
    ProviderShapeExpectedKind,
    ProviderShapeSensitivity,
    load_provider_shape_archive,
    load_provider_shape_cases,
    validate_discovery_dispositions,
    validate_provider_shape_catalog,
)
from tests.scenarios.canaries import LIVE_CANARIES


def _shape_case(**overrides: object) -> ProviderShapeCase:
    values: dict[str, object] = {
        "case_id": "shape-wave0-url-alias",
        "discovery_ids": ("RELEASE-20260717-03",),
        "focused_node": "wave0",
        "input_schema_version": 1,
        "payload": (("schema_version", 1), ("url", "https://example.invalid/source")),
        "expected_kind": ProviderShapeExpectedKind.NORMALIZED,
        "expected_payload": (("canonical_url", "https://example.invalid/source"),),
        "expected_error_code": None,
        "sensitivity": ProviderShapeSensitivity(
            synthetic_domain="example.invalid",
            minimized_reviewed=True,
            contains_free_text=False,
        ),
    }
    values.update(overrides)
    return ProviderShapeCase(**values)


def test_shape_case_loader_freezes_bounded_structured_json(tmp_path) -> None:
    source = tmp_path / "provider-shapes.json"
    source.write_text(
        json.dumps(
            [
                {
                    "case_id": "shape-wave0-url-alias",
                    "discovery_ids": ["RELEASE-20260717-03"],
                    "focused_node": "wave0",
                    "input_schema_version": 1,
                    "payload": {"schema_version": 1, "url": "https://example.invalid/source"},
                    "expected": {
                        "kind": "normalized",
                        "payload": {"canonical_url": "https://example.invalid/source"},
                    },
                    "sensitivity": {
                        "synthetic_domain": "example.invalid",
                        "minimized_reviewed": True,
                        "contains_free_text": False,
                    },
                }
            ]
        ),
        encoding="utf-8",
    )

    assert load_provider_shape_cases(source) == (_shape_case(),)


@pytest.mark.parametrize("focused_node", ["hitl1", "wave-0", "unknown"])
def test_shape_case_rejects_unknown_focused_node(focused_node: str) -> None:
    with pytest.raises(ValueError, match="shape_focused_node_invalid"):
        _shape_case(focused_node=focused_node)


def test_shape_case_rejects_unbounded_or_unreviewed_payload() -> None:
    with pytest.raises(ValueError, match="shape_input_schema_version_invalid"):
        _shape_case(input_schema_version=0)
    with pytest.raises(ValueError, match="shape_payload_oversize"):
        _shape_case(payload=(("body", "x" * 20_000),))
    with pytest.raises(ValueError, match="shape_payload_object_required"):
        _shape_case(payload="string-pseudo-payload")
    with pytest.raises(ValueError, match="shape_sensitivity_review_required"):
        _shape_case(
            sensitivity=ProviderShapeSensitivity(
                synthetic_domain="example.invalid",
                minimized_reviewed=False,
                contains_free_text=True,
            )
        )


def test_shape_expected_result_is_exactly_normalized_or_fail_closed() -> None:
    with pytest.raises(ValueError, match="shape_expected_normalized_invalid"):
        _shape_case(expected_error_code="parse_failed")
    with pytest.raises(ValueError, match="shape_expected_normalized_invalid"):
        _shape_case(expected_payload="normalized-string")
    with pytest.raises(ValueError, match="shape_expected_fail_closed_invalid"):
        _shape_case(
            expected_kind=ProviderShapeExpectedKind.FAIL_CLOSED,
            expected_payload=(("unexpected", True),),
            expected_error_code="parse_failed",
        )
    assert (
        _shape_case(
            expected_kind=ProviderShapeExpectedKind.FAIL_CLOSED,
            expected_payload=None,
            expected_error_code="parse_failed",
        ).expected_error_code
        == "parse_failed"
    )


def test_loader_rejects_unknown_or_malformed_fields(tmp_path) -> None:
    source = tmp_path / "provider-shapes.json"
    source.write_text('[{"case_id":"shape-one","unknown":true}]', encoding="utf-8")
    with pytest.raises(ValueError, match="shape_case_fields_invalid"):
        load_provider_shape_cases(source)


@pytest.mark.parametrize(
    "disposition",
    [
        DiscoveryDisposition(
            discovery_id="RELEASE-20260717-03",
            kind=DiscoveryDispositionKind.UNIFORM_SHAPE,
            intended_case_id="shape-wave0-url-alias",
        ),
        DiscoveryDisposition(
            discovery_id="LIVE-20260717-01",
            kind=DiscoveryDispositionKind.EXISTING_REGRESSION,
            claim_id="workspace-cleanup",
        ),
        DiscoveryDisposition(
            discovery_id="LIVE-20260717-05",
            kind=DiscoveryDispositionKind.PROVIDER_ONLY,
            live_case_id="live-one-topic-wave0",
            rationale="Provider tool-selection distribution cannot be represented by a deterministic payload.",
        ),
    ],
)
def test_each_discovery_disposition_has_one_closed_shape(disposition: DiscoveryDisposition) -> None:
    assert disposition.discovery_id


def test_discovery_disposition_rejects_mixed_or_missing_branch_fields() -> None:
    valid = DiscoveryDisposition(
        discovery_id="RELEASE-20260717-03",
        kind=DiscoveryDispositionKind.UNIFORM_SHAPE,
        intended_case_id="shape-wave0-url-alias",
    )
    with pytest.raises(ValueError, match="disposition_fields_invalid"):
        replace(valid, claim_id="other-claim")
    with pytest.raises(ValueError, match="disposition_fields_invalid"):
        replace(valid, intended_case_id=None)
    with pytest.raises(ValueError, match="disposition_rationale_invalid"):
        DiscoveryDisposition(
            discovery_id="LIVE-20260717-05",
            kind=DiscoveryDispositionKind.PROVIDER_ONLY,
            live_case_id="live-one-topic-wave0",
            rationale="too short",
        )
    with pytest.raises(ValueError, match="disposition_claim_id_invalid"):
        DiscoveryDisposition(
            discovery_id="LIVE-20260717-01",
            kind=DiscoveryDispositionKind.EXISTING_REGRESSION,
            claim_id="Bad Claim",
        )


def test_live_discoveries_have_exact_bound_dispositions() -> None:
    expected = {f"LIVE-20260717-{index:02d}" for index in range(1, 7)}
    validate_discovery_dispositions(
        LIVE_DISCOVERY_DISPOSITIONS,
        required_discovery_ids=expected,
        claims=claim_index(EVIDENCE_CLAIMS),
        live_case_ids={case.scenario_id for case in LIVE_CANARIES},
    )
    assert {item.discovery_id for item in LIVE_DISCOVERY_DISPOSITIONS} == expected
    assert {item.discovery_id: item.kind for item in LIVE_DISCOVERY_DISPOSITIONS}[
        "LIVE-20260717-05"
    ] is DiscoveryDispositionKind.PROVIDER_ONLY


def test_disposition_join_rejects_missing_claim_provenance_or_unknown_live_case() -> None:
    claims = claim_index(EVIDENCE_CLAIMS)
    existing = next(
        item for item in LIVE_DISCOVERY_DISPOSITIONS if item.kind is DiscoveryDispositionKind.EXISTING_REGRESSION
    )
    with pytest.raises(ValueError, match="disposition_claim_provenance_missing"):
        validate_discovery_dispositions(
            (replace(existing, discovery_id="RELEASE-20260717-25"),),
            required_discovery_ids={"RELEASE-20260717-25"},
            claims=claims,
            live_case_ids=set(),
        )
    provider_only = next(
        item for item in LIVE_DISCOVERY_DISPOSITIONS if item.kind is DiscoveryDispositionKind.PROVIDER_ONLY
    )
    with pytest.raises(ValueError, match="disposition_live_case_unknown"):
        validate_discovery_dispositions(
            (provider_only,),
            required_discovery_ids={provider_only.discovery_id},
            claims=claims,
            live_case_ids=set(),
        )


def test_release_discoveries_01_14_have_exact_classifications_and_intended_cases() -> None:
    expected = {f"RELEASE-20260717-{index:02d}" for index in range(1, 15)}
    validate_discovery_dispositions(
        RELEASE_DISCOVERY_DISPOSITIONS_01_14,
        required_discovery_ids=expected,
        claims=claim_index(EVIDENCE_CLAIMS),
        live_case_ids=set(),
    )
    uniform = {
        item.discovery_id: item.intended_case_id
        for item in RELEASE_DISCOVERY_DISPOSITIONS_01_14
        if item.kind is DiscoveryDispositionKind.UNIFORM_SHAPE
    }
    assert uniform == {
        "RELEASE-20260717-03": "shape-wave0-url-canonicalization",
        "RELEASE-20260717-04": "shape-wave0-fetch-status-alias",
        "RELEASE-20260717-05": "shape-wave0-limitations-list",
        "RELEASE-20260717-07": "shape-wave1-provider-identifiers",
        "RELEASE-20260717-09": "shape-wave2-provider-field-aliases",
        "RELEASE-20260717-11": "shape-wave2-gap-priority-alias",
        "RELEASE-20260717-12": "shape-wave0-partial-source-degradation",
    }


def test_release_discoveries_15_25_have_exact_classifications_and_intended_cases() -> None:
    expected = {f"RELEASE-20260717-{index:02d}" for index in range(15, 26)}
    validate_discovery_dispositions(
        RELEASE_DISCOVERY_DISPOSITIONS_15_25,
        required_discovery_ids=expected,
        claims=claim_index(EVIDENCE_CLAIMS),
        live_case_ids=set(),
    )
    uniform = {
        item.discovery_id: item.intended_case_id
        for item in RELEASE_DISCOVERY_DISPOSITIONS_15_25
        if item.kind is DiscoveryDispositionKind.UNIFORM_SHAPE
    }
    assert uniform == {
        "RELEASE-20260717-18": "shape-wave1-source-id-ref-rewrites",
        "RELEASE-20260717-19": "shape-wave2-description-string-gaps",
        "RELEASE-20260717-20": "shape-wave2-sparse-findings",
        "RELEASE-20260717-21": "shape-wave1-source-order",
        "RELEASE-20260717-22": "shape-wave2-relation-endpoints",
        "RELEASE-20260717-23": "shape-wave2-singular-affected-topic",
        "RELEASE-20260717-24": "shape-wave2-alternate-relation",
        "RELEASE-20260717-25": "shape-wave2-missing-gap-identity",
    }


PROVIDER_SHAPE_ROOT = Path(__file__).parents[1] / "fixtures/provider_shapes"
ALL_DISPOSITIONS = (
    *LIVE_DISCOVERY_DISPOSITIONS,
    *RELEASE_DISCOVERY_DISPOSITIONS_01_14,
    *RELEASE_DISCOVERY_DISPOSITIONS_15_25,
)
ALL_DISCOVERY_IDS = {
    *(f"LIVE-20260717-{index:02d}" for index in range(1, 7)),
    *(f"RELEASE-20260717-{index:02d}" for index in range(1, 26)),
}


def _real_catalog():
    cases = load_provider_shape_archive(PROVIDER_SHAPE_ROOT)
    claims = claim_index(EVIDENCE_CLAIMS)
    selectors = {claim.selector for claim in claims.values()}
    live_case_ids = {case.scenario_id for case in LIVE_CANARIES}
    return cases, claims, selectors, live_case_ids


def test_real_provider_shape_catalog_closes_every_discovery_and_case() -> None:
    cases, claims, selectors, live_case_ids = _real_catalog()
    validate_provider_shape_catalog(
        ALL_DISPOSITIONS,
        cases=cases,
        required_discovery_ids=ALL_DISCOVERY_IDS,
        claims=claims,
        collected_selectors=selectors,
        live_case_ids=live_case_ids,
    )


def test_provider_shape_catalog_rejects_unknown_discovery_and_unresolved_intended_case() -> None:
    cases, claims, selectors, live_case_ids = _real_catalog()
    with pytest.raises(ValueError, match="shape_case_discovery_unknown"):
        validate_provider_shape_catalog(
            ALL_DISPOSITIONS,
            cases=(replace(cases[0], discovery_ids=("RELEASE-20260717-99",)), *cases[1:]),
            required_discovery_ids=ALL_DISCOVERY_IDS,
            claims=claims,
            collected_selectors=selectors,
            live_case_ids=live_case_ids,
        )
    uniform = next(item for item in ALL_DISPOSITIONS if item.kind is DiscoveryDispositionKind.UNIFORM_SHAPE)
    with pytest.raises(ValueError, match="shape_intended_case_unresolved"):
        validate_provider_shape_catalog(
            tuple(
                replace(item, intended_case_id="shape-wave0-missing") if item == uniform else item
                for item in ALL_DISPOSITIONS
            ),
            cases=cases,
            required_discovery_ids=ALL_DISCOVERY_IDS,
            claims=claims,
            collected_selectors=selectors,
            live_case_ids=live_case_ids,
        )


def test_provider_shape_catalog_rejects_duplicate_unowned_or_uncollected_cases() -> None:
    cases, claims, selectors, live_case_ids = _real_catalog()
    with pytest.raises(ValueError, match="shape_case_id_duplicate"):
        validate_provider_shape_catalog(
            ALL_DISPOSITIONS,
            cases=(*cases, cases[0]),
            required_discovery_ids=ALL_DISCOVERY_IDS,
            claims=claims,
            collected_selectors=selectors,
            live_case_ids=live_case_ids,
        )
    with pytest.raises(ValueError, match="shape_case_claim_missing"):
        owned_claim = next(claim for claim in claims.values() if f"[{cases[0].case_id}]" in claim.selector)
        validate_provider_shape_catalog(
            ALL_DISPOSITIONS,
            cases=cases,
            required_discovery_ids=ALL_DISCOVERY_IDS,
            claims={key: value for key, value in claims.items() if key != owned_claim.claim_id},
            collected_selectors=selectors,
            live_case_ids=live_case_ids,
        )
    with pytest.raises(ValueError, match="shape_case_selector_uncollected"):
        validate_provider_shape_catalog(
            ALL_DISPOSITIONS,
            cases=cases,
            required_discovery_ids=ALL_DISCOVERY_IDS,
            claims=claims,
            collected_selectors=selectors - {owned_claim.selector},
            live_case_ids=live_case_ids,
        )


def test_provider_shape_catalog_rejects_missing_reverse_provenance() -> None:
    cases, claims, selectors, live_case_ids = _real_catalog()
    case = cases[0]
    owned_claim = next(claim for claim in claims.values() if f"[{case.case_id}]" in claim.selector)
    broken_claims = dict(claims)
    broken_claims[owned_claim.claim_id] = replace(owned_claim, discovery_ids=())
    with pytest.raises(ValueError, match="shape_case_claim_provenance_mismatch"):
        validate_provider_shape_catalog(
            ALL_DISPOSITIONS,
            cases=cases,
            required_discovery_ids=ALL_DISCOVERY_IDS,
            claims=broken_claims,
            collected_selectors=selectors,
            live_case_ids=live_case_ids,
        )


def test_provider_shape_catalog_requires_collected_existing_and_exact_provider_live_claims() -> None:
    cases, claims, selectors, live_case_ids = _real_catalog()
    existing = next(item for item in ALL_DISPOSITIONS if item.kind is DiscoveryDispositionKind.EXISTING_REGRESSION)
    existing_claim = claims[existing.claim_id]
    with pytest.raises(ValueError, match="disposition_claim_selector_uncollected"):
        validate_provider_shape_catalog(
            ALL_DISPOSITIONS,
            cases=cases,
            required_discovery_ids=ALL_DISCOVERY_IDS,
            claims=claims,
            collected_selectors=selectors - {existing_claim.selector},
            live_case_ids=live_case_ids,
        )

    provider_only = next(item for item in ALL_DISPOSITIONS if item.kind is DiscoveryDispositionKind.PROVIDER_ONLY)
    live_claim = next(claim for claim in claims.values() if provider_only.discovery_id in claim.discovery_ids)
    broken_claims = dict(claims)
    broken_claims[live_claim.claim_id] = replace(
        live_claim,
        selector="tests/live/test_canaries.py::test_live_prefix_canary[live-start-to-hitl1]",
    )
    with pytest.raises(ValueError, match="disposition_live_claim_case_mismatch"):
        validate_provider_shape_catalog(
            ALL_DISPOSITIONS,
            cases=cases,
            required_discovery_ids=ALL_DISCOVERY_IDS,
            claims=broken_claims,
            collected_selectors=selectors,
            live_case_ids=live_case_ids,
        )


def _write_shape_document(path: Path, payload: dict[str, object]) -> None:
    path.write_text(
        json.dumps(
            [
                {
                    "case_id": "shape-wave0-sensitive-smoke",
                    "discovery_ids": ["RELEASE-20260717-03"],
                    "focused_node": "wave0",
                    "input_schema_version": 1,
                    "payload": {"schema_version": 1, **payload},
                    "expected": {"kind": "normalized", "payload": {"accepted": True}},
                    "sensitivity": {
                        "synthetic_domain": "example.invalid",
                        "minimized_reviewed": True,
                        "contains_free_text": True,
                    },
                }
            ]
        ),
        encoding="utf-8",
    )


@pytest.mark.parametrize(
    ("payload", "error"),
    [
        ({"api_key": "sk-synthetic-secret"}, "shape_credential_forbidden"),
        ({"diagnostic": "/Users/operator/private/result.json"}, "shape_raw_host_path_forbidden"),
        ({"url": "https://external.example/source"}, "shape_external_url_forbidden"),
    ],
)
def test_provider_shape_loader_rejects_sensitive_or_non_synthetic_values(tmp_path, payload, error) -> None:
    source = tmp_path / "provider-shapes.json"
    _write_shape_document(source, payload)
    with pytest.raises(ValueError, match=error):
        load_provider_shape_cases(source)


def test_provider_shape_archive_scan_rejects_empty_or_known_violating_archive(tmp_path) -> None:
    with pytest.raises(ValueError, match="shape_archive_empty"):
        load_provider_shape_archive(tmp_path)
    _write_shape_document(tmp_path / "known-violation.json", {"url": "https://external.example/source"})
    with pytest.raises(ValueError, match="shape_external_url_forbidden"):
        load_provider_shape_archive(tmp_path)
