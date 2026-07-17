"""Live/E2E regression-descent governance contracts.

@impl EVH-006
@impl EVH-010
"""

from __future__ import annotations

from pathlib import Path

from scripts.check_test_assets import collect_deterministic_selectors


def test_regression_descent_log_classifies_each_discovery_and_names_live_rationale_or_collected_test() -> None:
    path = Path("docs/regression-descent.md")
    text = path.read_text(encoding="utf-8")
    collected = collect_deterministic_selectors()
    rows = [line for line in text.splitlines() if line.startswith("| LIVE-") or line.startswith("| RELEASE-")]

    assert len(rows) >= 7
    for row in rows:
        columns = [column.strip() for column in row.strip("|").split("|")]
        assert len(columns) == 6
        discovery_id, risk, seam, disposition, selector, rationale = columns
        assert discovery_id.startswith(("LIVE-", "RELEASE-"))
        assert risk and seam
        assert disposition in {"deterministic-regression", "provider-only-live"}
        if disposition == "deterministic-regression":
            assert selector in collected
            assert rationale == "n/a"
        else:
            assert selector == "n/a"
            assert rationale != "n/a"
