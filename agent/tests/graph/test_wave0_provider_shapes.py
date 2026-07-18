"""Minimized Wave0 provider-shape regressions through the production parser.

@impl EVH-006
@impl EVH-010
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from deerflow_deep_research.graph.nodes.wave0.prompts import parse_wave0_worker_output
from tests.assets.provider_shapes import (
    ProviderShapeExpectedKind,
    load_provider_shape_cases,
    thaw_provider_shape_payload,
)

CASES = load_provider_shape_cases(Path(__file__).parents[1] / "fixtures/provider_shapes/wave0.json")


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.case_id)
def test_wave0_provider_shape(case) -> None:
    payload = thaw_provider_shape_payload(case.payload)
    if case.expected_kind is ProviderShapeExpectedKind.FAIL_CLOSED:
        with pytest.raises(ValueError, match=case.expected_error_code):
            parse_wave0_worker_output(json.dumps(payload))
        return

    output = parse_wave0_worker_output(json.dumps(payload))
    observed = {
        "source_ids": [source.source_id for source in output.sources],
        "canonical_urls": [source.canonical_url for source in output.sources],
        "fetch_statuses": [source.fetch_status for source in output.sources],
        "limitations": output.limitations,
    }
    assert observed == thaw_provider_shape_payload(case.expected_payload)
