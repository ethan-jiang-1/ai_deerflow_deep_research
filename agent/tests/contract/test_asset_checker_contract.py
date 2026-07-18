"""Focused collection and central-claim checker contracts.

@impl EVH-006
@impl EVH-009
"""

from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path

import pytest

from scripts.check_test_assets import collect_pytest_selectors
from tests.assets.evidence import (
    AssetClass,
    EvidenceClaimError,
    FocusedSelection,
    StableSeam,
    TestEvidenceClaim,
    validate_claim_selections,
)
from tests.assets.inventory import CoverageError

SELECTOR = "tests/unit/test_example.py::test_example"


def _claim(**overrides: object) -> TestEvidenceClaim:
    values: dict[str, object] = {
        "claim_id": "example-correctness",
        "selector": SELECTOR,
        "expected_selection": FocusedSelection.FAST,
        "requirement_ids": ("EVH-006",),
        "asset_class": AssetClass.CODE_CORRECTNESS,
        "seam": StableSeam.DOMAIN_ENGINE,
    }
    values.update(overrides)
    return TestEvidenceClaim(**values)


def _selections(**overrides: set[str]) -> dict[FocusedSelection, set[str]]:
    values = {selection: set() for selection in FocusedSelection}
    values[FocusedSelection.FAST] = {SELECTOR}
    values.update(overrides)
    return values


def test_claim_resolves_only_to_its_expected_focused_selection() -> None:
    validate_claim_selections((_claim(),), focused_selectors=_selections())


def test_missing_expected_selector_reports_claim_and_lane() -> None:
    with pytest.raises(EvidenceClaimError, match="example-correctness.*fast"):
        validate_claim_selections(
            (_claim(),),
            focused_selectors=_selections(fast=set()),
        )


def test_selector_in_another_focused_lane_is_rejected() -> None:
    with pytest.raises(EvidenceClaimError, match="example-correctness.*integration"):
        validate_claim_selections(
            (_claim(),),
            focused_selectors=_selections(integration={SELECTOR}),
        )


def test_missing_focused_collection_is_rejected() -> None:
    selections = _selections()
    del selections[FocusedSelection.RELEASE]

    with pytest.raises(EvidenceClaimError, match="missing focused collection: release"):
        validate_claim_selections((_claim(),), focused_selectors=selections)


def test_changed_expected_lane_cannot_pass_on_old_collection() -> None:
    integration_claim = replace(_claim(), expected_selection=FocusedSelection.INTEGRATION)

    with pytest.raises(EvidenceClaimError, match="example-correctness.*integration"):
        validate_claim_selections((integration_claim,), focused_selectors=_selections())


def test_subprocess_collector_smoke_rejects_empty_or_mis_scoped_collection(tmp_path: Path) -> None:
    test_file = tmp_path / "test_known.py"
    test_file.write_text(
        "import pytest\n\n@pytest.mark.workflow\ndef test_known_collector_smoke():\n    pass\n",
        encoding="utf-8",
    )
    command = (sys.executable, "-m", "pytest")

    collected = collect_pytest_selectors(
        paths=("test_known.py",),
        expression="workflow",
        label="known-smoke",
        agent_root=tmp_path,
        command=command,
    )
    assert collected == {"test_known.py::test_known_collector_smoke"}

    with pytest.raises(CoverageError, match="mis-scoped-smoke pytest collection failed"):
        collect_pytest_selectors(
            paths=("test_known.py",),
            expression="not workflow",
            label="mis-scoped-smoke",
            agent_root=tmp_path,
            command=command,
        )
