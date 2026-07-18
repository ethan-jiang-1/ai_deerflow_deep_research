"""Central test-evidence claim contract and synthetic registry validation.

@impl EVH-006
@impl EVH-007
@impl EVH-008
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from tests.assets.evidence import (
    AssetClass,
    AuthenticityLevel,
    EvidenceClaimError,
    FocusedSelection,
    StableSeam,
    TestEvidenceClaim,
    validate_evidence_claims,
    validate_inventory_claim_references,
)

SELECTOR = "tests/integration/test_example.py::test_example[case-quick-factual]"


def _claim(**overrides: object) -> TestEvidenceClaim:
    values: dict[str, object] = {
        "claim_id": "claim-quick-factual",
        "selector": SELECTOR,
        "expected_selection": FocusedSelection.WORKFLOW,
        "requirement_ids": ("EVH-001", "EVH-008"),
        "asset_class": AssetClass.DETERMINISTIC_WORKFLOW_CONFORMANCE,
        "seam": StableSeam.RUNTIME_INTEGRATION,
        "authenticity": AuthenticityLevel.SCRIPTED_REAL_WORKFLOW,
        "scenario_case_id": "case-quick-factual",
        "discovery_ids": ("LIVE-20260717-01",),
    }
    values.update(overrides)
    return TestEvidenceClaim(**values)


def test_valid_claim_and_synthetic_case_registry_pass() -> None:
    claim = _claim()

    validate_evidence_claims(
        (claim,),
        supplied_case_ids={"case-quick-factual"},
        collected_selectors={SELECTOR},
    )

    assert claim.asset_class is AssetClass.DETERMINISTIC_WORKFLOW_CONFORMANCE
    assert claim.seam is StableSeam.RUNTIME_INTEGRATION


@pytest.mark.parametrize(
    ("field", "value", "code"),
    [
        ("expected_selection", "workflow", "claim_expected_selection_invalid"),
        ("asset_class", "workflow", "claim_asset_class_invalid"),
        ("seam", "runtime-store", "claim_seam_invalid"),
        ("authenticity", "scripted-real-workflow", "claim_authenticity_invalid"),
    ],
)
def test_string_aliases_are_rejected(field: str, value: str, code: str) -> None:
    with pytest.raises(ValueError, match=code):
        _claim(**{field: value})


@pytest.mark.parametrize(
    ("overrides", "code"),
    [
        ({"claim_id": "Bad Claim"}, "claim_id_invalid"),
        ({"claim_id": "c" * 65}, "claim_id_invalid"),
        ({"selector": "tests/**/test_example.py::test_example"}, "claim_selector_pattern_forbidden"),
        ({"selector": "tests/integration/test_example.py"}, "claim_selector_not_exact"),
        ({"selector": "tests/integration/test_example.py::test_"}, "claim_selector_not_exact"),
        ({"selector": "x" * 513}, "claim_selector_invalid"),
        ({"requirement_ids": ()}, "claim_requirement_ids_invalid"),
        ({"requirement_ids": ["EVH-001"]}, "claim_requirement_ids_invalid"),
        ({"requirement_ids": ("EVH-001", "EVH-001")}, "claim_requirement_ids_duplicate"),
        ({"requirement_ids": ("evh-001",)}, "claim_requirement_ids_invalid"),
        ({"requirement_ids": tuple(f"EVH-{value:03d}" for value in range(1, 34))}, "claim_requirement_ids_oversize"),
        ({"scenario_case_id": "Bad Case"}, "claim_scenario_case_id_invalid"),
        ({"discovery_ids": ("LIVE-1",)}, "claim_discovery_ids_invalid"),
        ({"discovery_ids": ["LIVE-20260717-01"]}, "claim_discovery_ids_invalid"),
        ({"discovery_ids": ("LIVE-20260717-01", "LIVE-20260717-01")}, "claim_discovery_ids_duplicate"),
        (
            {"discovery_ids": tuple(f"RELEASE-20260717-{value:02d}" for value in range(1, 66))},
            "claim_discovery_ids_oversize",
        ),
    ],
)
def test_claim_bounds_and_identifiers_fail_closed(overrides: dict[str, object], code: str) -> None:
    with pytest.raises(ValueError, match=code):
        _claim(**overrides)


def test_optional_authenticity_and_case_are_valid_for_correctness_claim() -> None:
    claim = _claim(
        claim_id="claim-pure-metric",
        selector="tests/eval/test_quality_metrics.py::test_pure_metric",
        expected_selection=FocusedSelection.FAST,
        requirement_ids=("EVH-002",),
        asset_class=AssetClass.CODE_CORRECTNESS,
        seam=StableSeam.DOMAIN_ENGINE,
        authenticity=None,
        scenario_case_id=None,
        discovery_ids=(),
    )

    validate_evidence_claims((claim,), supplied_case_ids=set(), collected_selectors={claim.selector})


@pytest.mark.parametrize(
    ("asset_class", "selection"),
    [
        (AssetClass.CODE_CORRECTNESS, FocusedSelection.WORKFLOW),
        (AssetClass.DETERMINISTIC_WORKFLOW_CONFORMANCE, FocusedSelection.INTEGRATION),
        (AssetClass.LIVE_BEHAVIORAL_EVALUATION, FocusedSelection.FAST),
        (AssetClass.RELEASE_ACCEPTANCE, FocusedSelection.LIVE),
    ],
)
def test_asset_class_and_selection_cannot_contradict(
    asset_class: AssetClass,
    selection: FocusedSelection,
) -> None:
    with pytest.raises(ValueError, match="claim_asset_selection_conflict"):
        _claim(asset_class=asset_class, expected_selection=selection)


def test_canonical_vocabularies_remain_closed() -> None:
    assert len(AssetClass) == 4
    assert len(StableSeam) == 5
    assert len(AuthenticityLevel) == 5
    assert len(FocusedSelection) == 5


@pytest.mark.parametrize(
    ("claims", "cases", "collected", "message"),
    [
        ((_claim(), _claim()), {"case-quick-factual"}, {SELECTOR}, "duplicate claim id"),
        (
            (_claim(claim_id="claim-other"), _claim(claim_id="claim-third")),
            {"case-quick-factual"},
            {SELECTOR},
            "resolves to 2 claims",
        ),
        ((_claim(scenario_case_id=None),), {"case-quick-factual"}, {SELECTOR}, "resolves to 0 claims"),
        ((_claim(),), set(), {SELECTOR}, "unknown scenario case"),
        (
            (_claim(selector="tests/integration/test_example.py::test_example[case-other]"),),
            {"case-quick-factual"},
            {"tests/integration/test_example.py::test_example[case-other]"},
            "selector does not contain stable case id",
        ),
        ((_claim(),), {"case-quick-factual"}, set(), "uncollected selector"),
    ],
)
def test_synthetic_registry_rejects_ambiguous_or_uncollected_cases(
    claims: tuple[TestEvidenceClaim, ...],
    cases: set[str],
    collected: set[str],
    message: str,
) -> None:
    with pytest.raises(EvidenceClaimError, match=message):
        validate_evidence_claims(claims, supplied_case_ids=cases, collected_selectors=collected)


def test_duplicate_selector_claims_are_rejected() -> None:
    second = replace(_claim(), claim_id="claim-second", scenario_case_id=None)

    with pytest.raises(EvidenceClaimError, match="duplicate selector"):
        validate_evidence_claims(
            (_claim(), second),
            supplied_case_ids={"case-quick-factual"},
            collected_selectors={SELECTOR},
        )


def test_inventory_references_cannot_disagree_about_one_selector() -> None:
    first = _claim(scenario_case_id=None, discovery_ids=())
    contradictory = replace(
        first,
        claim_id="claim-contradictory",
        seam=StableSeam.NODE_INTERFACE,
    )

    with pytest.raises(EvidenceClaimError, match="contradictory selector reference"):
        validate_inventory_claim_references(
            (
                ("incident:RM-01", (first.claim_id,)),
                ("node:bootstrap", (contradictory.claim_id,)),
            ),
            claims={
                first.claim_id: first,
                contradictory.claim_id: contradictory,
            },
        )


def test_inventory_reference_to_unknown_claim_reports_owner() -> None:
    with pytest.raises(EvidenceClaimError, match="incident:RM-01: unknown claim claim-missing"):
        validate_inventory_claim_references(
            (("incident:RM-01", ("claim-missing",)),),
            claims={},
        )
