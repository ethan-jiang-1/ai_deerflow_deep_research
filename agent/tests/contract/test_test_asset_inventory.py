"""Executable incident and test-asset inventory contracts.

@impl EVH-006
@impl EVH-007
"""

from __future__ import annotations

import pytest

from tests.assets.evidence import EVIDENCE_CLAIMS, claim_index, validate_inventory_claim_references
from tests.assets.inventory import (
    INCIDENTS,
    CoverageError,
    HistoricalStatus,
    validate_incident_coverage,
)


def test_incident_inventory_has_thirteen_unique_complete_records() -> None:
    assert len(INCIDENTS) == 13
    assert len({incident.incident_id for incident in INCIDENTS}) == 13
    claims = claim_index(EVIDENCE_CLAIMS)
    for incident in INCIDENTS:
        assert incident.title
        assert incident.risk_family
        assert isinstance(incident.historical_status, HistoricalStatus)
        assert incident.claim_ids
        assert all(claim_id in claims for claim_id in incident.claim_ids)
        assert incident.invariant

    validate_inventory_claim_references(
        ((incident.incident_id, incident.claim_ids) for incident in INCIDENTS),
        claims=claims,
    )


def test_historical_replaced_and_duplicate_recommendations_remain_explicit() -> None:
    by_id = {incident.incident_id: incident for incident in INCIDENTS}

    assert set(HistoricalStatus) == {
        HistoricalStatus.COVERED,
        HistoricalStatus.REPLACED,
        HistoricalStatus.DUPLICATE,
        HistoricalStatus.NEW_REGRESSION,
    }
    assert by_id["RM-11"].historical_status is HistoricalStatus.REPLACED
    assert by_id["RM-13"].historical_status is HistoricalStatus.DUPLICATE
    assert by_id["RM-13"].claim_ids == by_id["RM-04"].claim_ids


def test_stale_selector_reports_incident_and_selector() -> None:
    claims = claim_index(EVIDENCE_CLAIMS)
    collected = {claims[claim_id].selector for incident in INCIDENTS for claim_id in incident.claim_ids}
    stale = claims[INCIDENTS[0].claim_ids[0]].selector
    collected.remove(stale)

    with pytest.raises(CoverageError) as exc_info:
        validate_incident_coverage(INCIDENTS, claims, collected, excluded_selectors=set())

    detail = str(exc_info.value)
    assert INCIDENTS[0].incident_id in detail
    assert stale in detail


def test_deterministic_selector_cannot_be_excluded() -> None:
    claims = claim_index(EVIDENCE_CLAIMS)
    collected = {claims[claim_id].selector for incident in INCIDENTS for claim_id in incident.claim_ids}
    excluded = {claims[INCIDENTS[0].claim_ids[0]].selector}

    with pytest.raises(CoverageError, match="excluded from deterministic lane"):
        validate_incident_coverage(INCIDENTS, claims, collected, excluded_selectors=excluded)
