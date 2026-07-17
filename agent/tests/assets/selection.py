"""Canonical pytest marker expressions for Deep Research test lanes.

@impl EVH-009
"""

DETERMINISTIC_EXCLUDE = "requires_llm or release_e2e or postgres"
FAST_PATHS = ("tests/contract", "tests/domain", "tests/engine", "tests/unit", "tests/graph", "tests/eval")
INTEGRATION_PATHS = ("tests/integration", "tests/blocking_io")
LIVE_PATHS = ("tests/live",)
LIVE_EXPRESSION = "requires_llm and not release_e2e"
RELEASE_EXPRESSION = "release_e2e"

__all__ = [
    "DETERMINISTIC_EXCLUDE",
    "FAST_PATHS",
    "INTEGRATION_PATHS",
    "LIVE_EXPRESSION",
    "LIVE_PATHS",
    "RELEASE_EXPRESSION",
]
