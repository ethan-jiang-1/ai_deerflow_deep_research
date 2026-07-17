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
    FAST_PATHS,
    INTEGRATION_PATHS,
    LIVE_EXPRESSION,
    LIVE_PATHS,
    RELEASE_EXPRESSION,
)


def test_lane_expressions_are_non_overlapping_and_complete() -> None:
    assert DETERMINISTIC_EXCLUDE == "requires_llm or release_e2e or postgres"
    assert LIVE_EXPRESSION == "requires_llm and not release_e2e"
    assert RELEASE_EXPRESSION == "release_e2e"
    assert set(FAST_PATHS).isdisjoint(INTEGRATION_PATHS)
    assert LIVE_PATHS == ("tests/live",)
    assert "tests/eval" in FAST_PATHS
    assert "tests/integration" in INTEGRATION_PATHS


def _collect(path: str, expression: str) -> set[str]:
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", path, "-m", expression],
        capture_output=True,
        check=False,
        text=True,
    )
    assert result.returncode in {0, 5}, result.stderr or result.stdout
    return {line.strip() for line in result.stdout.splitlines() if "::" in line and not line.startswith("=")}


def test_live_tests_are_selected_only_by_the_live_lane() -> None:
    live = _collect(LIVE_PATHS[0], LIVE_EXPRESSION)
    deterministic = _collect(LIVE_PATHS[0], f"not ({DETERMINISTIC_EXCLUDE})")

    assert live == {
        "tests/live/test_canaries.py::test_live_prefix_canary[live-start-to-hitl1]",
        "tests/live/test_canaries.py::test_live_prefix_canary[live-hitl1-to-topic-planning]",
        "tests/live/test_canaries.py::test_live_prefix_canary[live-one-topic-wave0]",
        "tests/live/test_preflight.py::test_live_model_preflight",
        "tests/live/test_preflight.py::test_live_web_preflight",
    }
    assert deterministic == set()


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
