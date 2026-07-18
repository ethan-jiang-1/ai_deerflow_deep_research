"""Every registered real node owns deterministic conformance selectors.

@impl EVH-007
@impl EVH-008
"""

from __future__ import annotations

import pytest

from deerflow_deep_research.graph.registry import load_research_node_specs
from tests.assets.evidence import EVIDENCE_CLAIMS, claim_index, validate_inventory_claim_references
from tests.assets.node_conformance import NODE_CONFORMANCE, NodeConformanceError, validate_node_conformance


def test_matrix_exactly_covers_registered_real_nodes() -> None:
    registered = set(load_research_node_specs())
    assert {entry.logical_name for entry in NODE_CONFORMANCE} == registered
    claims = claim_index(EVIDENCE_CLAIMS)
    for entry in NODE_CONFORMANCE:
        assert entry.success_claim_id in claims
        assert entry.risk_claim_id in claims
        assert entry.highest_risk
    validate_inventory_claim_references(
        ((entry.logical_name, (entry.success_claim_id, entry.risk_claim_id)) for entry in NODE_CONFORMANCE),
        claims=claims,
    )


@pytest.mark.parametrize("entry", NODE_CONFORMANCE, ids=lambda entry: entry.logical_name)
def test_each_real_node_declares_distinct_success_and_risk_scenarios(entry) -> None:
    assert entry.success_claim_id != entry.risk_claim_id


def test_stale_node_selector_reports_logical_name() -> None:
    claims = claim_index(EVIDENCE_CLAIMS)
    collected = {
        claims[claim_id].selector
        for entry in NODE_CONFORMANCE
        for claim_id in (entry.success_claim_id, entry.risk_claim_id)
    }
    first = NODE_CONFORMANCE[0]
    collected.remove(claims[first.risk_claim_id].selector)
    with pytest.raises(NodeConformanceError) as exc_info:
        validate_node_conformance(
            NODE_CONFORMANCE,
            claims,
            collected,
            registered_names=set(load_research_node_specs()),
        )
    assert first.logical_name in str(exc_info.value)
