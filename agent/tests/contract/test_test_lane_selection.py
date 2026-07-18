"""Test-lane selection and deterministic network contracts.

@impl EVH-009
@impl EVH-005
"""

from __future__ import annotations

import socket
import subprocess
import sys

import pytest

from tests.assets.selection import (
    DETERMINISTIC_EXCLUDE,
    FAST_EXPRESSION,
    FAST_PATHS,
    INTEGRATION_EXPRESSION,
    INTEGRATION_PATHS,
    LIVE_EXPRESSION,
    LIVE_PATHS,
    RELEASE_EXPRESSION,
    WORKFLOW_EXPRESSION,
    WORKFLOW_PATHS,
)


def test_lane_expressions_are_non_overlapping_and_complete() -> None:
    assert DETERMINISTIC_EXCLUDE == "requires_llm or release_e2e or postgres"
    assert FAST_EXPRESSION == "not (requires_llm or release_e2e or postgres or workflow)"
    assert INTEGRATION_EXPRESSION == FAST_EXPRESSION
    assert WORKFLOW_EXPRESSION == "workflow and not (requires_llm or release_e2e or postgres)"
    assert LIVE_EXPRESSION == "requires_llm and not release_e2e"
    assert RELEASE_EXPRESSION == "requires_llm and release_e2e"
    assert set(FAST_PATHS).isdisjoint(INTEGRATION_PATHS)
    assert WORKFLOW_PATHS == ("tests",)
    assert LIVE_PATHS == ("tests/live",)
    assert "tests/eval" in FAST_PATHS
    assert "tests/integration" in INTEGRATION_PATHS


def _collect(paths: tuple[str, ...], expression: str) -> set[str]:
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", *paths, "-m", expression],
        capture_output=True,
        check=False,
        text=True,
    )
    assert result.returncode in {0, 5}, result.stderr or result.stdout
    return {line.strip() for line in result.stdout.splitlines() if "::" in line and not line.startswith("=")}


def test_live_tests_are_selected_only_by_the_live_lane() -> None:
    live = _collect(LIVE_PATHS, LIVE_EXPRESSION)
    deterministic = _collect(LIVE_PATHS, f"not ({DETERMINISTIC_EXCLUDE})")

    assert live == {
        "tests/live/test_canaries.py::test_live_prefix_canary[live-start-to-hitl1]",
        "tests/live/test_canaries.py::test_live_prefix_canary[live-hitl1-to-topic-planning]",
        "tests/live/test_canaries.py::test_live_prefix_canary[live-one-topic-wave0]",
        "tests/live/test_canaries.py::test_live_prefix_canary[live-one-topic-wave1]",
        "tests/live/test_canaries.py::test_live_prefix_canary[live-wave2-synthesis]",
        "tests/live/test_canaries.py::test_live_prefix_canary[live-one-gap-targeted-evidence]",
        "tests/live/test_preflight.py::test_live_model_preflight",
        "tests/live/test_preflight.py::test_live_web_preflight",
    }
    assert deterministic == set()


def test_deterministic_focused_selections_are_disjoint_exact_partition() -> None:
    aggregate = _collect(("tests",), f"not ({DETERMINISTIC_EXCLUDE})")
    fast = _collect(FAST_PATHS, FAST_EXPRESSION)
    integration = _collect(INTEGRATION_PATHS, INTEGRATION_EXPRESSION)
    workflow = _collect(WORKFLOW_PATHS, WORKFLOW_EXPRESSION)

    assert fast
    assert integration
    assert workflow
    assert fast.isdisjoint(integration)
    assert fast.isdisjoint(workflow)
    assert integration.isdisjoint(workflow)
    assert fast | integration | workflow == aggregate


def test_release_marker_always_implies_requires_llm() -> None:
    assert _collect(("tests",), "release_e2e and not requires_llm") == set()


def test_deterministic_lane_denies_public_network() -> None:
    with pytest.raises(OSError, match="deterministic test network denied"):
        socket.create_connection(("example.com", 443), timeout=0.01)


def test_deterministic_lane_allows_loopback_socket() -> None:
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    try:
        client = socket.create_connection(listener.getsockname(), timeout=1)
        server, _ = listener.accept()
        client.close()
        server.close()
    finally:
        listener.close()
