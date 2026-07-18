"""Incrementally migrated real replay registry bindings.

@impl EVH-001
@impl EVH-008
@impl EVH-009
"""

from __future__ import annotations

from scripts.check_test_assets import collect_pytest_selectors
from tests.assets.evidence import EVIDENCE_CLAIMS
from tests.assets.selection import DETERMINISTIC_EXCLUDE
from tests.scenarios.governance import validate_scenario_evidence
from tests.scenarios.observation import (
    CheckpointFacts,
    FilesystemFaultOutcome,
    LedgerFacts,
    LifecycleFacts,
    SandboxFacts,
    ScenarioObservation,
    WorkGateOutcome,
    WorkStateFacts,
)
from tests.scenarios.replays import FIRST_WAVE_CASES, FIRST_WAVE_FAMILIES


def test_migrated_replays_bind_to_exact_collected_claims() -> None:
    validate_scenario_evidence(
        FIRST_WAVE_FAMILIES,
        FIRST_WAVE_CASES,
        EVIDENCE_CLAIMS,
        observations={
            "quick-factual": ScenarioObservation(
                checkpoint=CheckpointFacts(route=None, terminal=None, identity_isolated=True, attempt_count=1),
                ledger=LedgerFacts(("h_authority",), False, True),
                sandbox=SandboxFacts(True, (("work/result.json", "h_result"),), ()),
            ),
            "claim-verification": ScenarioObservation(
                checkpoint=CheckpointFacts(route=None, terminal=None, identity_isolated=True, attempt_count=1),
                ledger=LedgerFacts(("h_authority",), False, True),
                sandbox=SandboxFacts(True, (("work/result.json", "h_result"),), ()),
            ),
            "insufficient-evidence": ScenarioObservation(
                checkpoint=CheckpointFacts(route=None, terminal=None, identity_isolated=True, attempt_count=1),
                ledger=LedgerFacts(("h_authority",), False, True),
                sandbox=SandboxFacts(True, (("work/result.json", "h_result"),), ()),
                degradation="insufficient-evidence",
            ),
            "prompt-injection": ScenarioObservation(
                checkpoint=CheckpointFacts(route="pass", terminal=None, identity_isolated=True, attempt_count=1),
                ledger=LedgerFacts(("h_authority",), False, True),
                sandbox=SandboxFacts(True, (("work/result.json", "h_result"),), ()),
            ),
            "malformed-output": ScenarioObservation(
                checkpoint=CheckpointFacts(route=None, terminal=None, identity_isolated=True, attempt_count=1),
                ledger=LedgerFacts((), False, True),
                sandbox=SandboxFacts(True, (), ()),
                degradation="malformed-output",
            ),
            "tool-unavailable-timeout": ScenarioObservation(
                checkpoint=CheckpointFacts(route=None, terminal=None, identity_isolated=True, attempt_count=1),
                ledger=LedgerFacts((), False, True),
                sandbox=SandboxFacts(True, (), ()),
                diagnostic_codes=("tools-unavailable", "wall-time", "cancellation-propagated"),
                degradation="tool-unavailable-timeout",
            ),
            "budget-exhaustion": ScenarioObservation(
                checkpoint=CheckpointFacts(route=None, terminal=None, identity_isolated=True, attempt_count=1),
                ledger=LedgerFacts((), False, True),
                sandbox=SandboxFacts(True, (), ()),
                diagnostic_codes=("budget-exhausted",),
                degradation="budget-exhaustion",
            ),
            "partial-worker-success": ScenarioObservation(
                checkpoint=CheckpointFacts(
                    route="exhausted", terminal="blocked", identity_isolated=True, attempt_count=3
                ),
                ledger=LedgerFacts(("h_authority",), False, True),
                sandbox=SandboxFacts(True, (("work/result.json", "h_result"),), ()),
                work_state=WorkStateFacts(
                    accepted_work_ids=("g0_wave0_w0000",),
                    failed_attempt_ids=("g0_wave0_w0001_a00",),
                    gate_outcomes=(
                        WorkGateOutcome("repair", ("work_failed",)),
                        WorkGateOutcome("exhausted", ("work_failed", "fatigue_escalation")),
                        WorkGateOutcome("exhausted", ("work_failed", "repair_budget_exhausted")),
                    ),
                ),
            ),
            "checkpoint-control": ScenarioObservation(
                checkpoint=CheckpointFacts(route=None, terminal="cancelled", identity_isolated=True, attempt_count=7),
                ledger=LedgerFacts((), False, True),
                sandbox=SandboxFacts(True, (), ()),
                lifecycle=LifecycleFacts(
                    research_ids=("r_checkpoint",) * 7,
                    resume_request_ids=("request-next", "request-next"),
                    cancel_statuses=("cancelled", "cancelled"),
                    post_terminal_resume_code="invalid_transition",
                    final_status="cancelled",
                    durabilities=("restart_durable",) * 7,
                ),
            ),
            "sandbox-filesystem-failure": ScenarioObservation(
                checkpoint=CheckpointFacts(route=None, terminal=None, identity_isolated=True, attempt_count=4),
                ledger=LedgerFacts(("h_prior", "h_new"), False, True),
                sandbox=SandboxFacts(True, (), ()),
                filesystem_faults=(
                    FilesystemFaultOutcome("before_staging_write", 1, 2, "appended", True, False),
                    FilesystemFaultOutcome("after_staging_fsync", 1, 2, "appended", True, False),
                    FilesystemFaultOutcome("after_ledger_replace", 2, 2, "replayed", True, False),
                    FilesystemFaultOutcome("after_directory_fsync", 2, 2, "replayed", True, False),
                ),
            ),
        },
        collected_selectors=collect_pytest_selectors(
            paths=("tests",),
            expression=f"not ({DETERMINISTIC_EXCLUDE})",
            label="deterministic replay registry",
        ),
    )
