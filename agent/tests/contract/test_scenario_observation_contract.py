"""Authority-projected scenario observations and invariant registry.

@impl EVH-007
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from tests.scenarios.observation import (
    CheckpointFacts,
    EvidenceState,
    FilesystemFaultOutcome,
    InvariantName,
    LabeledEvidenceFact,
    LedgerFacts,
    LifecycleFacts,
    SandboxFacts,
    ScenarioObservation,
    WorkGateOutcome,
    WorkStateFacts,
    evaluate_invariants,
)


def _observation(**overrides: object) -> ScenarioObservation:
    values: dict[str, object] = {
        "checkpoint": CheckpointFacts(
            route="pass",
            terminal="completed",
            identity_isolated=True,
            attempt_count=1,
        ),
        "ledger": LedgerFacts(
            accepted_refs=("h_accepted",),
            conflict_detected=False,
            replay_idempotent=True,
        ),
        "sandbox": SandboxFacts(
            paths_contained=True,
            artifact_hashes=(("final/report.md", "h_report"),),
            citation_bindings=(("claim-1", ("h_accepted",)),),
        ),
        "diagnostic_codes": ("completed",),
        "evidence_facts": (),
    }
    values.update(overrides)
    return ScenarioObservation(**values)


def test_closed_invariants_are_computed_from_authority_facts() -> None:
    result = evaluate_invariants(
        _observation(),
        (
            InvariantName.TERMINAL_COMPLETED,
            InvariantName.IDENTITY_ISOLATED,
            InvariantName.ATTEMPTS_BOUNDED,
            InvariantName.ACCEPTED_AUTHORITY,
            InvariantName.REPLAY_IDEMPOTENT,
            InvariantName.PATHS_CONTAINED,
            InvariantName.ARTIFACTS_HASHED,
            InvariantName.CITATIONS_BOUND,
        ),
        max_attempts=1,
    )
    assert result == {name: True for name in result}


def test_failed_authority_fact_cannot_be_reported_as_passing() -> None:
    result = evaluate_invariants(
        _observation(ledger=LedgerFacts(accepted_refs=(), conflict_detected=True, replay_idempotent=False)),
        (InvariantName.ACCEPTED_AUTHORITY, InvariantName.NO_LEDGER_CONFLICT, InvariantName.REPLAY_IDEMPOTENT),
        max_attempts=1,
    )
    assert result == {
        InvariantName.ACCEPTED_AUTHORITY: False,
        InvariantName.NO_LEDGER_CONFLICT: False,
        InvariantName.REPLAY_IDEMPOTENT: False,
    }


def test_unknown_invariant_fails_closed() -> None:
    with pytest.raises(ValueError, match="unknown_invariant"):
        evaluate_invariants(_observation(), ("authority",), max_attempts=1)


@pytest.mark.parametrize(
    "diagnostic",
    [
        "ANTHROPIC_API_KEY=sk-secret",
        "/Users/alice/private/report.txt",
        "/home/alice/private/report.txt",
        "free form provider output with spaces",
    ],
)
def test_observation_diagnostics_reject_sensitive_or_unbounded_text(diagnostic: str) -> None:
    with pytest.raises(ValueError, match="observation_diagnostic_forbidden"):
        _observation(diagnostic_codes=(diagnostic,))


def test_citation_binding_requires_accepted_ledger_authority() -> None:
    observation = _observation(
        sandbox=SandboxFacts(
            paths_contained=True,
            artifact_hashes=(("final/report.md", "h_report"),),
            citation_bindings=(("claim-1", ("h_missing",)),),
        )
    )
    assert evaluate_invariants(
        observation,
        (InvariantName.CITATIONS_BOUND,),
        max_attempts=1,
    ) == {InvariantName.CITATIONS_BOUND: False}


def test_authority_facts_reject_mutable_duplicates_and_path_escape() -> None:
    with pytest.raises(ValueError, match="ledger_accepted_refs_invalid"):
        LedgerFacts(accepted_refs=["h_accepted"], conflict_detected=False, replay_idempotent=True)
    with pytest.raises(ValueError, match="ledger_accepted_refs_invalid"):
        LedgerFacts(
            accepted_refs=("h_accepted", "h_accepted"),
            conflict_detected=False,
            replay_idempotent=True,
        )
    with pytest.raises(ValueError, match="sandbox_artifact_hashes_invalid"):
        SandboxFacts(
            paths_contained=True,
            artifact_hashes=(("../private/report.md", "h_report"),),
            citation_bindings=(),
        )


def test_labeled_evidence_invariant_requires_supported_contradicted_and_uncertain_states() -> None:
    complete = _observation(
        evidence_facts=(
            LabeledEvidenceFact("claim-supported", EvidenceState.SUPPORTED, ("source:one",)),
            LabeledEvidenceFact("claim-contradicted", EvidenceState.CONTRADICTED, ("source:one",)),
            LabeledEvidenceFact("claim-uncertain", EvidenceState.UNCERTAIN, ()),
        )
    )
    assert evaluate_invariants(
        complete,
        (InvariantName.LABELED_EVIDENCE_COMPLETE,),
        max_attempts=1,
    ) == {InvariantName.LABELED_EVIDENCE_COMPLETE: True}

    incomplete = replace(complete, evidence_facts=complete.evidence_facts[:2])
    assert evaluate_invariants(
        incomplete,
        (InvariantName.LABELED_EVIDENCE_COMPLETE,),
        max_attempts=1,
    ) == {InvariantName.LABELED_EVIDENCE_COMPLETE: False}


def test_no_partial_authority_requires_empty_ledger_artifacts_and_citations() -> None:
    empty = _observation(
        ledger=LedgerFacts((), False, True),
        sandbox=SandboxFacts(True, (), ()),
    )
    assert evaluate_invariants(
        empty,
        (InvariantName.NO_PARTIAL_AUTHORITY,),
        max_attempts=1,
    ) == {InvariantName.NO_PARTIAL_AUTHORITY: True}

    partial = replace(empty, sandbox=SandboxFacts(True, (("partial.json", "h_partial"),), ()))
    assert evaluate_invariants(
        partial,
        (InvariantName.NO_PARTIAL_AUTHORITY,),
        max_attempts=1,
    ) == {InvariantName.NO_PARTIAL_AUTHORITY: False}


def test_partial_worker_outcomes_are_distinguished_from_authoritative_work_state() -> None:
    observation = replace(
        _observation(),
        work_state=WorkStateFacts(
            accepted_work_ids=("g0_wave0_w0000", "g0_wave0_w0002"),
            failed_attempt_ids=("g0_wave0_w0001_a00",),
            gate_outcomes=(
                WorkGateOutcome(route="repair", failure_codes=("work_failed",)),
                WorkGateOutcome(route="exhausted", failure_codes=("work_failed", "fatigue_escalation")),
                WorkGateOutcome(
                    route="exhausted",
                    failure_codes=("work_failed", "repair_budget_exhausted"),
                ),
            ),
        ),
    )

    assert evaluate_invariants(
        observation,
        (InvariantName.PARTIAL_WORK_OUTCOMES_COMPLETE,),
        max_attempts=3,
    ) == {InvariantName.PARTIAL_WORK_OUTCOMES_COMPLETE: True}


def test_partial_worker_invariant_rejects_conflated_fatigue_and_exhaustion() -> None:
    observation = replace(
        _observation(),
        work_state=WorkStateFacts(
            accepted_work_ids=("g0_wave0_w0000",),
            failed_attempt_ids=("g0_wave0_w0001_a00",),
            gate_outcomes=(
                WorkGateOutcome(
                    route="exhausted",
                    failure_codes=("work_failed", "fatigue_escalation", "repair_budget_exhausted"),
                ),
            ),
        ),
    )

    assert evaluate_invariants(
        observation,
        (InvariantName.PARTIAL_WORK_OUTCOMES_COMPLETE,),
        max_attempts=3,
    ) == {InvariantName.PARTIAL_WORK_OUTCOMES_COMPLETE: False}


def test_checkpoint_control_requires_restart_stable_identity_and_monotonic_terminal_state() -> None:
    observation = replace(
        _observation(),
        lifecycle=LifecycleFacts(
            research_ids=("r_checkpoint",) * 7,
            resume_request_ids=("request-next", "request-next"),
            cancel_statuses=("cancelled", "cancelled"),
            post_terminal_resume_code="invalid_transition",
            final_status="cancelled",
            durabilities=("restart_durable",) * 7,
        ),
    )

    assert evaluate_invariants(
        observation,
        (InvariantName.CHECKPOINT_CONTROL_COMPLETE,),
        max_attempts=7,
    ) == {InvariantName.CHECKPOINT_CONTROL_COMPLETE: True}


@pytest.mark.parametrize(
    "lifecycle",
    [
        LifecycleFacts(
            research_ids=("r_first", "r_other"),
            resume_request_ids=("request-next", "request-next"),
            cancel_statuses=("cancelled", "cancelled"),
            post_terminal_resume_code="invalid_transition",
            final_status="cancelled",
            durabilities=("restart_durable", "restart_durable"),
        ),
        LifecycleFacts(
            research_ids=("r_checkpoint",) * 2,
            resume_request_ids=("request-first", "request-advanced"),
            cancel_statuses=("cancelled", "cancelled"),
            post_terminal_resume_code="invalid_transition",
            final_status="cancelled",
            durabilities=("restart_durable", "restart_durable"),
        ),
        LifecycleFacts(
            research_ids=("r_checkpoint",) * 2,
            resume_request_ids=("request-next", "request-next"),
            cancel_statuses=("cancelled", "completed"),
            post_terminal_resume_code="invalid_transition",
            final_status="completed",
            durabilities=("restart_durable", "restart_durable"),
        ),
    ],
)
def test_checkpoint_control_rejects_identity_resume_or_terminal_drift(lifecycle: LifecycleFacts) -> None:
    observation = replace(_observation(), lifecycle=lifecycle)

    assert evaluate_invariants(
        observation,
        (InvariantName.CHECKPOINT_CONTROL_COMPLETE,),
        max_attempts=7,
    ) == {InvariantName.CHECKPOINT_CONTROL_COMPLETE: False}


def test_filesystem_faults_preserve_prior_or_single_new_authority() -> None:
    observation = replace(
        _observation(),
        filesystem_faults=(
            FilesystemFaultOutcome("before_staging_write", 1, 2, "appended", True, False),
            FilesystemFaultOutcome("after_staging_fsync", 1, 2, "appended", True, False),
            FilesystemFaultOutcome("after_ledger_replace", 2, 2, "replayed", True, False),
            FilesystemFaultOutcome("after_directory_fsync", 2, 2, "replayed", True, False),
        ),
    )

    assert evaluate_invariants(
        observation,
        (InvariantName.FILESYSTEM_AUTHORITY_ATOMIC,),
        max_attempts=4,
    ) == {InvariantName.FILESYSTEM_AUTHORITY_ATOMIC: True}


def test_filesystem_fault_invariant_rejects_duplicate_or_staging_authority() -> None:
    observation = replace(
        _observation(),
        filesystem_faults=(FilesystemFaultOutcome("before_staging_write", 3, 3, "appended", True, True),),
    )

    assert evaluate_invariants(
        observation,
        (InvariantName.FILESYSTEM_AUTHORITY_ATOMIC,),
        max_attempts=4,
    ) == {InvariantName.FILESYSTEM_AUTHORITY_ATOMIC: False}
