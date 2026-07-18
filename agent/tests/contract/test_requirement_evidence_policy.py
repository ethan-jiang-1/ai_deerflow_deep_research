"""Cross-lane requirement evidence remains independent and collected.

@impl EVH-008
@impl EVH-009
@impl EVH-010
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from tests.assets.evidence import (
    AssetClass,
    AuthenticityLevel,
    FocusedSelection,
    StableSeam,
    TestEvidenceClaim,
)
from tests.assets.requirement_evidence import (
    REQUIREMENT_EVIDENCE_POLICY,
    RequirementEvidenceError,
    collected_deterministic_impl_ids,
    load_alive_requirement_ids,
    validate_requirement_evidence,
)


def _claim(
    claim_id: str,
    requirement_id: str,
    asset_class: AssetClass,
    authenticity: AuthenticityLevel | None,
) -> TestEvidenceClaim:
    selections = {
        AssetClass.CODE_CORRECTNESS: FocusedSelection.FAST,
        AssetClass.DETERMINISTIC_WORKFLOW_CONFORMANCE: FocusedSelection.WORKFLOW,
        AssetClass.LIVE_BEHAVIORAL_EVALUATION: FocusedSelection.LIVE,
        AssetClass.RELEASE_ACCEPTANCE: FocusedSelection.RELEASE,
    }
    return TestEvidenceClaim(
        claim_id=claim_id,
        selector=f"tests/unit/test_policy.py::test_{claim_id.replace('-', '_')}",
        expected_selection=selections[asset_class],
        requirement_ids=(requirement_id,),
        asset_class=asset_class,
        seam=StableSeam.RUNTIME_INTEGRATION,
        authenticity=authenticity,
    )


def _evh005_claims() -> tuple[TestEvidenceClaim, ...]:
    return (
        _claim("evh005-deterministic", "EVH-005", AssetClass.CODE_CORRECTNESS, None),
        _claim(
            "evh005-live",
            "EVH-005",
            AssetClass.LIVE_BEHAVIORAL_EVALUATION,
            AuthenticityLevel.LIVE_REAL_DEPENDENCIES,
        ),
        _claim(
            "evh005-release",
            "EVH-005",
            AssetClass.RELEASE_ACCEPTANCE,
            AuthenticityLevel.FULL_REAL_PIPELINE,
        ),
    )


def test_cross_lane_policy_accepts_required_independent_evidence() -> None:
    claims = _evh005_claims()
    validate_requirement_evidence(
        policy=(next(item for item in REQUIREMENT_EVIDENCE_POLICY if item.requirement_id == "EVH-005"),),
        claims=claims,
        alive_requirement_ids={"EVH-005", "EVH-006"},
        deterministic_impl_ids={"EVH-005", "EVH-006"},
        collected_selectors={claim.selector for claim in claims},
    )


def test_cross_lane_policy_rejects_missing_asset_class() -> None:
    claims = _evh005_claims()[:-1]
    with pytest.raises(RequirementEvidenceError, match="EVH-005.*release-acceptance"):
        validate_requirement_evidence(
            policy=(next(item for item in REQUIREMENT_EVIDENCE_POLICY if item.requirement_id == "EVH-005"),),
            claims=claims,
            alive_requirement_ids={"EVH-005"},
            deterministic_impl_ids={"EVH-005"},
            collected_selectors={claim.selector for claim in claims},
        )


def test_cross_lane_policy_rejects_missing_collected_deterministic_impl() -> None:
    with pytest.raises(RequirementEvidenceError, match="missing deterministic @impl: EVH-006"):
        validate_requirement_evidence(
            policy=(),
            claims=(),
            alive_requirement_ids={"EVH-006"},
            deterministic_impl_ids=set(),
            collected_selectors=set(),
        )


def test_cross_lane_policy_rejects_unknown_requirement_id() -> None:
    policy = (replace(REQUIREMENT_EVIDENCE_POLICY[0], requirement_id="EVH-999"),)
    with pytest.raises(RequirementEvidenceError, match="unknown policy requirement: EVH-999"):
        validate_requirement_evidence(
            policy=policy,
            claims=(),
            alive_requirement_ids={"EVH-004"},
            deterministic_impl_ids={"EVH-004"},
            collected_selectors=set(),
        )


def test_ordinary_alive_requirement_needs_only_collected_deterministic_impl() -> None:
    validate_requirement_evidence(
        policy=(),
        claims=(),
        alive_requirement_ids={"EVH-006"},
        deterministic_impl_ids={"EVH-006"},
        collected_selectors=set(),
    )


def test_alive_loader_reads_main_specs_not_active_delta(tmp_path) -> None:
    main = tmp_path / "openspec/specs/example/spec.md"
    delta = tmp_path / "openspec/changes/change/specs/example/spec.md"
    main.parent.mkdir(parents=True)
    delta.parent.mkdir(parents=True)
    main.write_text("> req: ABC-001\n", encoding="utf-8")
    delta.write_text("> req: ABC-002\n", encoding="utf-8")

    assert load_alive_requirement_ids(tmp_path) == {"ABC-001"}


def test_impl_loader_counts_only_collected_test_modules(tmp_path) -> None:
    collected = tmp_path / "tests/unit/test_collected.py"
    uncollected = tmp_path / "tests/unit/test_uncollected.py"
    collected.parent.mkdir(parents=True)
    collected.write_text('"""@impl ABC-001"""\n\ndef test_one(): pass\n', encoding="utf-8")
    uncollected.write_text('"""@impl ABC-002"""\n\ndef test_two(): pass\n', encoding="utf-8")

    assert collected_deterministic_impl_ids(
        tmp_path,
        {"tests/unit/test_collected.py::test_one"},
    ) == {"ABC-001"}
