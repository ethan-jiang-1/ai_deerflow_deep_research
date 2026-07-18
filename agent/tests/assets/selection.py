"""Canonical pytest marker expressions for Deep Research test lanes.

@impl EVH-009
"""

DETERMINISTIC_EXCLUDE = "requires_llm or release_e2e or postgres"
FAST_PATHS = ("tests/contract", "tests/domain", "tests/engine", "tests/unit", "tests/graph", "tests/eval")
FAST_EXPRESSION = "not (requires_llm or release_e2e or postgres or workflow)"
INTEGRATION_PATHS = ("tests/integration", "tests/blocking_io")
INTEGRATION_EXPRESSION = FAST_EXPRESSION
WORKFLOW_PATHS = ("tests",)
WORKFLOW_EXPRESSION = "workflow and not (requires_llm or release_e2e or postgres)"
LIVE_PATHS = ("tests/live",)
LIVE_EXPRESSION = "requires_llm and not release_e2e"
RELEASE_PATHS = ("tests/e2e",)
RELEASE_EXPRESSION = "requires_llm and release_e2e"

__all__ = [
    "DETERMINISTIC_EXCLUDE",
    "FAST_EXPRESSION",
    "FAST_PATHS",
    "INTEGRATION_EXPRESSION",
    "INTEGRATION_PATHS",
    "LIVE_EXPRESSION",
    "LIVE_PATHS",
    "RELEASE_EXPRESSION",
    "RELEASE_PATHS",
    "WORKFLOW_EXPRESSION",
    "WORKFLOW_PATHS",
]
