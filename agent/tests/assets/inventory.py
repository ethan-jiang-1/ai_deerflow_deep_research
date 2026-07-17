"""Machine-readable mapping from real-mode incidents to deterministic tests.

@impl EVH-006
@impl EVH-007
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum


class StableSeam(StrEnum):
    CONTRACT = "contract"
    DOMAIN_ENGINE = "domain-engine"
    NODE_CAPABILITY = "node-capability"
    RUNTIME_STORE = "runtime-store"
    LIFECYCLE_GRAPH = "lifecycle-graph"
    PUBLIC_ENTRY = "public-entry"


class Authenticity(StrEnum):
    MODULE = "module"
    REAL_NODE_FAKE_CAPABILITIES = "real-node-fake-capabilities"
    SCRIPTED_REAL_WORKFLOW = "scripted-real-workflow"


class HistoricalStatus(StrEnum):
    COVERED = "covered"
    REPLACED = "replaced"
    NEW_REGRESSION = "new-regression"


@dataclass(frozen=True)
class IncidentCoverage:
    incident_id: str
    title: str
    risk_family: str
    seam: StableSeam
    authenticity: Authenticity
    selectors: tuple[str, ...]
    invariant: str
    historical_status: HistoricalStatus


class CoverageError(ValueError):
    pass


@dataclass(frozen=True)
class VerifiedLane:
    command: str
    selector: str
    result: str


BATCH1_VERIFIED_LANES = (
    VerifiedLane("make test-assets", "not (requires_llm or release_e2e or postgres)", "13 incidents / 1170 tests"),
    VerifiedLane("make test-fast", "contract domain engine unit graph eval", "1094 passed"),
    VerifiedLane("make test-integration", "integration blocking_io", "72 passed / 4 gateway skips"),
    VerifiedLane("make test-viability", "reflected runtime + cancellation", "5 passed"),
    VerifiedLane("make test-durability", "file SQLite provider recovery", "8 passed / 1 postgres skip"),
    VerifiedLane("make test-blocking-io", "blocking_io", "9 passed"),
)


INCIDENTS = (
    IncidentCoverage(
        "RM-01",
        "all-real builder import and compilation",
        "compile-and-registration",
        StableSeam.CONTRACT,
        Authenticity.MODULE,
        ("tests/unit/test_research_runtime_capabilities.py::test_all_real_recipe_compiles",),
        "every registered real implementation compiles without a deferred NameError",
        HistoricalStatus.NEW_REGRESSION,
    ),
    IncidentCoverage(
        "RM-02",
        "non-interactive policy forwarding",
        "context-forwarding",
        StableSeam.PUBLIC_ENTRY,
        Authenticity.REAL_NODE_FAKE_CAPABILITIES,
        ("tests/unit/test_non_interactive.py::test_tool_forwards_non_interactive_policy_to_action_input",),
        "trusted non-interactive policy reaches ResearchActionInput",
        HistoricalStatus.NEW_REGRESSION,
    ),
    IncidentCoverage(
        "RM-03",
        "missing demo model configuration",
        "model-readiness",
        StableSeam.RUNTIME_STORE,
        Authenticity.MODULE,
        ("tests/unit/test_node_agent_bridge.py::test_default_model_resolver_rejects_empty_model_config",),
        "empty model configuration fails with a stable readiness diagnostic",
        HistoricalStatus.NEW_REGRESSION,
    ),
    IncidentCoverage(
        "RM-04",
        "invalid demo parent sandbox",
        "sandbox-readiness",
        StableSeam.RUNTIME_STORE,
        Authenticity.MODULE,
        ("tests/unit/test_demo_core.py::test_demo_adapter_provides_legal_unique_sandbox",),
        "demo parent sandbox has provider identity and unique run identity",
        HistoricalStatus.NEW_REGRESSION,
    ),
    IncidentCoverage(
        "RM-05",
        "mounted workspace storage probe",
        "filesystem-readiness",
        StableSeam.RUNTIME_STORE,
        Authenticity.MODULE,
        ("tests/unit/test_work_unit_store.py::test_store_factory_accepts_verified_temp_workspace",),
        "verified local mounted workspace creates the runtime store",
        HistoricalStatus.COVERED,
    ),
    IncidentCoverage(
        "RM-06",
        "empty tool resolver configuration",
        "tool-readiness",
        StableSeam.RUNTIME_STORE,
        Authenticity.MODULE,
        ("tests/unit/test_node_agent_bridge.py::test_default_tools_resolver_rejects_missing_allowed_tools",),
        "configured policy tools cannot silently resolve to an empty set",
        HistoricalStatus.NEW_REGRESSION,
    ),
    IncidentCoverage(
        "RM-07",
        "missing typed tool policy specs",
        "tool-policy",
        StableSeam.NODE_CAPABILITY,
        Authenticity.MODULE,
        ("tests/unit/test_research_runtime_capabilities.py::test_worker_policies_specify_every_allowed_tool",),
        "every allowed worker tool has an eligible typed policy spec",
        HistoricalStatus.NEW_REGRESSION,
    ),
    IncidentCoverage(
        "RM-08",
        "wave-specific worker capability routing",
        "capability-routing",
        StableSeam.LIFECYCLE_GRAPH,
        Authenticity.REAL_NODE_FAKE_CAPABILITIES,
        ("tests/unit/test_research_runtime_capabilities.py::test_all_real_context_routes_distinct_worker_policies",),
        "Wave0 and Wave1 resolve their own bridge and policy",
        HistoricalStatus.NEW_REGRESSION,
    ),
    IncidentCoverage(
        "RM-09",
        "token admission with large tool history",
        "budget-admission",
        StableSeam.NODE_CAPABILITY,
        Authenticity.SCRIPTED_REAL_WORKFLOW,
        ("tests/unit/test_budget_middleware.py::test_large_tool_result_history_uses_bounded_admission",),
        "bounded tool results do not make a valid next model call impossible",
        HistoricalStatus.NEW_REGRESSION,
    ),
    IncidentCoverage(
        "RM-10",
        "model and parallel tool call limits",
        "budget-boundaries",
        StableSeam.NODE_CAPABILITY,
        Authenticity.MODULE,
        (
            "tests/unit/test_budget_middleware.py::test_max_model_calls_refused_before_handler",
            "tests/unit/test_budget_middleware.py::test_parallel_tool_call_limit",
        ),
        "configured call boundaries accept N and reject N plus one",
        HistoricalStatus.COVERED,
    ),
    IncidentCoverage(
        "RM-11",
        "topic planner malformed output",
        "structured-output-repair",
        StableSeam.NODE_CAPABILITY,
        Authenticity.REAL_NODE_FAKE_CAPABILITIES,
        ("tests/graph/test_topic_planning_node.py::test_repeated_invalid_plan_exhausts_without_topic_state",),
        "repeated malformed output fails closed without fabricated planner state",
        HistoricalStatus.REPLACED,
    ),
    IncidentCoverage(
        "RM-12",
        "gate fatigue after mixed worker outcomes",
        "gate-fatigue",
        StableSeam.DOMAIN_ENGINE,
        Authenticity.MODULE,
        ("tests/engine/test_gate_kernel.py::TestFatigue::test_successful_evaluation_resets_prior_failure_fatigue",),
        "a successful or changed evaluation breaks a prior consecutive failure chain",
        HistoricalStatus.NEW_REGRESSION,
    ),
    IncidentCoverage(
        "RM-13",
        "demo checkpoint identity reuse",
        "checkpoint-isolation",
        StableSeam.PUBLIC_ENTRY,
        Authenticity.MODULE,
        ("tests/unit/test_demo_core.py::test_demo_adapter_provides_legal_unique_sandbox",),
        "each demo adapter receives unique thread and run identity",
        HistoricalStatus.NEW_REGRESSION,
    ),
)


def validate_incident_coverage(
    incidents: Iterable[IncidentCoverage],
    collected_selectors: set[str],
    *,
    excluded_selectors: set[str],
) -> None:
    seen: set[str] = set()
    errors: list[str] = []
    for incident in incidents:
        if incident.incident_id in seen:
            errors.append(f"{incident.incident_id}: duplicate incident id")
        seen.add(incident.incident_id)
        for selector in incident.selectors:
            if selector not in collected_selectors:
                errors.append(f"{incident.incident_id}: stale selector {selector}")
            if selector in excluded_selectors:
                errors.append(f"{incident.incident_id}: {selector} excluded from deterministic lane")
    if errors:
        raise CoverageError("\n".join(errors))


__all__ = [
    "INCIDENTS",
    "Authenticity",
    "BATCH1_VERIFIED_LANES",
    "CoverageError",
    "HistoricalStatus",
    "IncidentCoverage",
    "StableSeam",
    "VerifiedLane",
    "validate_incident_coverage",
]
