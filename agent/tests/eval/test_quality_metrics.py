"""Independent worked examples for quality metrics and hard invariants.

@impl EVH-002
"""

from __future__ import annotations

import pytest

from tests.eval.metrics import assert_hard_invariants


def test_hard_invariant_failure_is_not_a_quality_score() -> None:
    with pytest.raises(AssertionError, match="forged_submission"):
        assert_hard_invariants({"hard_invariant_failures": ("forged_submission",)})
    assert_hard_invariants({"hard_invariant_failures": ()})
