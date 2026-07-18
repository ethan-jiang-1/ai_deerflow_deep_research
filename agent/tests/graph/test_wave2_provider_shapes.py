"""Minimized Wave2 provider shapes through the production parser.

@impl EVH-006
@impl EVH-010
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from deerflow_deep_research.graph.nodes.wave2_synthesis.prompts import parse_synthesis_output
from tests.assets.provider_shapes import load_provider_shape_cases, thaw_provider_shape_payload

CASES = tuple(
    case
    for case in load_provider_shape_cases(Path(__file__).parents[1] / "fixtures/provider_shapes/wave2.json")
    if case.case_id != "shape-wave2-evidence-alias-binding"
)


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.case_id)
def test_wave2_provider_shape(case) -> None:
    output = parse_synthesis_output(json.dumps(thaw_provider_shape_payload(case.payload)))
    observed = {
        "findings": [finding.model_dump(mode="json") for finding in output.findings],
        "relations": [relation.model_dump(mode="json") for relation in output.relations],
        "gaps": [gap.model_dump(mode="json") for gap in output.gaps],
        "summary": output.summary,
    }
    assert observed == thaw_provider_shape_payload(case.expected_payload)
