"""Machine-readable mapping from real-mode incidents to deterministic tests.

@impl EVH-006
@impl EVH-007
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum

from tests.assets.evidence import TestEvidenceClaim


class HistoricalStatus(StrEnum):
    COVERED = "covered"
    REPLACED = "replaced"
    DUPLICATE = "duplicate"
    NEW_REGRESSION = "new-regression"


@dataclass(frozen=True)
class IncidentCoverage:
    incident_id: str
    title: str
    risk_family: str
    claim_ids: tuple[str, ...]
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
        ("real-recipe-compiles",),
        "every registered real implementation compiles without a deferred NameError",
        HistoricalStatus.NEW_REGRESSION,
    ),
    IncidentCoverage(
        "RM-02",
        "non-interactive policy forwarding",
        "context-forwarding",
        ("non-interactive-policy-forwarding",),
        "trusted non-interactive policy reaches ResearchActionInput",
        HistoricalStatus.NEW_REGRESSION,
    ),
    IncidentCoverage(
        "RM-03",
        "missing demo model configuration",
        "model-readiness",
        ("model-resolver-empty-config",),
        "empty model configuration fails with a stable readiness diagnostic",
        HistoricalStatus.NEW_REGRESSION,
    ),
    IncidentCoverage(
        "RM-04",
        "invalid demo parent sandbox",
        "sandbox-readiness",
        ("demo-adapter-unique-sandbox",),
        "demo parent sandbox has provider identity and unique run identity",
        HistoricalStatus.NEW_REGRESSION,
    ),
    IncidentCoverage(
        "RM-05",
        "mounted workspace storage probe",
        "filesystem-readiness",
        ("store-verified-temp-workspace",),
        "verified local mounted workspace creates the runtime store",
        HistoricalStatus.COVERED,
    ),
    IncidentCoverage(
        "RM-06",
        "empty tool resolver configuration",
        "tool-readiness",
        ("tool-resolver-missing-allowed-tools",),
        "configured policy tools cannot silently resolve to an empty set",
        HistoricalStatus.NEW_REGRESSION,
    ),
    IncidentCoverage(
        "RM-07",
        "missing typed tool policy specs",
        "tool-policy",
        ("worker-policy-tool-specs",),
        "every allowed worker tool has an eligible typed policy spec",
        HistoricalStatus.NEW_REGRESSION,
    ),
    IncidentCoverage(
        "RM-08",
        "wave-specific worker capability routing",
        "capability-routing",
        ("distinct-worker-policy-routing",),
        "Wave0 and Wave1 resolve their own bridge and policy",
        HistoricalStatus.NEW_REGRESSION,
    ),
    IncidentCoverage(
        "RM-09",
        "token admission with large tool history",
        "budget-admission",
        ("budget-large-history-admission",),
        "bounded tool results do not make a valid next model call impossible",
        HistoricalStatus.NEW_REGRESSION,
    ),
    IncidentCoverage(
        "RM-10",
        "model and parallel tool call limits",
        "budget-boundaries",
        ("budget-max-model-calls", "budget-parallel-tool-calls"),
        "configured call boundaries accept N and reject N plus one",
        HistoricalStatus.COVERED,
    ),
    IncidentCoverage(
        "RM-11",
        "topic planner malformed output",
        "structured-output-repair",
        ("topic-planning-invalid-output",),
        "repeated malformed output fails closed without fabricated planner state",
        HistoricalStatus.REPLACED,
    ),
    IncidentCoverage(
        "RM-12",
        "gate fatigue after mixed worker outcomes",
        "gate-fatigue",
        ("gate-fatigue-reset",),
        "a successful or changed evaluation breaks a prior consecutive failure chain",
        HistoricalStatus.NEW_REGRESSION,
    ),
    IncidentCoverage(
        "RM-13",
        "demo checkpoint identity reuse",
        "checkpoint-isolation",
        ("demo-adapter-unique-sandbox",),
        "each demo adapter receives unique thread and run identity",
        HistoricalStatus.DUPLICATE,
    ),
)


def validate_incident_coverage(
    incidents: Iterable[IncidentCoverage],
    claims: dict[str, TestEvidenceClaim],
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
        for claim_id in incident.claim_ids:
            claim = claims.get(claim_id)
            if claim is None:
                errors.append(f"{incident.incident_id}: unknown claim {claim_id}")
                continue
            selector = claim.selector
            if selector not in collected_selectors:
                errors.append(f"{incident.incident_id}: {claim_id}: stale selector {selector}")
            if selector in excluded_selectors:
                errors.append(f"{incident.incident_id}: {selector} excluded from deterministic lane")
    if errors:
        raise CoverageError("\n".join(errors))


__all__ = [
    "INCIDENTS",
    "BATCH1_VERIFIED_LANES",
    "CoverageError",
    "HistoricalStatus",
    "IncidentCoverage",
    "VerifiedLane",
    "validate_incident_coverage",
]
