"""Executable incident and test-asset inventory contracts.

@impl EVH-006
@impl EVH-007
"""

from __future__ import annotations

import pytest

from tests.assets.inventory import (
    INCIDENTS,
    Authenticity,
    CoverageError,
    HistoricalStatus,
    StableSeam,
    validate_incident_coverage,
)


def test_incident_inventory_has_thirteen_unique_complete_records() -> None:
    assert len(INCIDENTS) == 13
    assert len({incident.incident_id for incident in INCIDENTS}) == 13
    for incident in INCIDENTS:
        assert incident.title
        assert incident.risk_family
        assert isinstance(incident.seam, StableSeam)
        assert isinstance(incident.authenticity, Authenticity)
        assert isinstance(incident.historical_status, HistoricalStatus)
        assert incident.selectors
        assert all("::test_" in selector for selector in incident.selectors)
        assert incident.invariant


def test_stale_selector_reports_incident_and_selector() -> None:
    collected = {selector for incident in INCIDENTS for selector in incident.selectors}
    stale = INCIDENTS[0].selectors[0]
    collected.remove(stale)

    with pytest.raises(CoverageError) as exc_info:
        validate_incident_coverage(INCIDENTS, collected, excluded_selectors=set())

    detail = str(exc_info.value)
    assert INCIDENTS[0].incident_id in detail
    assert stale in detail


def test_deterministic_selector_cannot_be_excluded() -> None:
    collected = {selector for incident in INCIDENTS for selector in incident.selectors}
    excluded = {INCIDENTS[0].selectors[0]}

    with pytest.raises(CoverageError, match="excluded from deterministic lane"):
        validate_incident_coverage(INCIDENTS, collected, excluded_selectors=excluded)
