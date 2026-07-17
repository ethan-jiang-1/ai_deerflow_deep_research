"""Every registered real node owns deterministic conformance selectors.

@impl EVH-007
@impl EVH-008
"""

from __future__ import annotations

import pytest

from deerflow_deep_research.graph.registry import load_research_node_specs
from tests.assets.node_conformance import NODE_CONFORMANCE, NodeConformanceError, validate_node_conformance


def test_matrix_exactly_covers_registered_real_nodes() -> None:
    registered = set(load_research_node_specs())
    assert {entry.logical_name for entry in NODE_CONFORMANCE} == registered
    for entry in NODE_CONFORMANCE:
        assert "::test_" in entry.success_selector
        assert "::test_" in entry.risk_selector
        assert entry.highest_risk


@pytest.mark.parametrize("entry", NODE_CONFORMANCE, ids=lambda entry: entry.logical_name)
def test_each_real_node_declares_distinct_success_and_risk_scenarios(entry) -> None:
    assert entry.success_selector != entry.risk_selector


def test_stale_node_selector_reports_logical_name() -> None:
    collected = {selector for entry in NODE_CONFORMANCE for selector in (entry.success_selector, entry.risk_selector)}
    first = NODE_CONFORMANCE[0]
    collected.remove(first.risk_selector)
    with pytest.raises(NodeConformanceError) as exc_info:
        validate_node_conformance(NODE_CONFORMANCE, collected, registered_names=set(load_research_node_specs()))
    assert first.logical_name in str(exc_info.value)
