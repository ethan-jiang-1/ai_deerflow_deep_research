"""Minimized Wave1 provider shapes through the production contract.

@impl EVH-006
@impl EVH-010
"""

from __future__ import annotations

from pathlib import Path

import pytest

from deerflow_deep_research.domain.wave1 import Wave1WorkerOutput
from tests.assets.provider_shapes import load_provider_shape_cases, thaw_provider_shape_payload

CASES = tuple(
    case
    for case in load_provider_shape_cases(Path(__file__).parents[1] / "fixtures/provider_shapes/wave1.json")
    if case.case_id in {"shape-wave1-provider-identifiers", "shape-wave1-source-id-ref-rewrites"}
)


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.case_id)
def test_wave1_provider_shape(case) -> None:
    output = Wave1WorkerOutput.model_validate(thaw_provider_shape_payload(case.payload))
    observed = {
        "source_ids": list(output.source_ids),
        "claim_ids": [claim.claim_id for claim in output.claims],
        "support_refs": [list(claim.support_refs) for claim in output.claims],
        "question_ids": [question.question_id for question in output.open_questions],
        "question_states": [question.state.value for question in output.open_questions],
    }
    assert observed == thaw_provider_shape_payload(case.expected_payload)
