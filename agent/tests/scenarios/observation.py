"""Test-owned authority projection and closed invariant evaluation.

@impl EVH-007
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum

DIAGNOSTIC_RE = re.compile(r"^[a-z][a-z0-9_.-]{1,63}$")
REF_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{1,127}$")
HASH_RE = re.compile(r"^h_[A-Za-z0-9_-]{2,127}$")


class InvariantName(StrEnum):
    ROUTE_EXPECTED = "route-expected"
    TERMINAL_COMPLETED = "terminal-completed"
    IDENTITY_ISOLATED = "identity-isolated"
    ATTEMPTS_BOUNDED = "attempts-bounded"
    ACCEPTED_AUTHORITY = "accepted-authority"
    NO_LEDGER_CONFLICT = "no-ledger-conflict"
    REPLAY_IDEMPOTENT = "replay-idempotent"
    PATHS_CONTAINED = "paths-contained"
    ARTIFACTS_HASHED = "artifacts-hashed"
    CITATIONS_BOUND = "citations-bound"
    LABELED_EVIDENCE_COMPLETE = "labeled-evidence-complete"
    HONEST_DEGRADATION = "honest-degradation"
    AUTHORITY_NOT_FORGED = "authority-not-forged"
    NO_PARTIAL_AUTHORITY = "no-partial-authority"
    FAULT_OUTCOMES_COMPLETE = "fault-outcomes-complete"
    BUDGET_EXHAUSTED = "budget-exhausted"
    PARTIAL_WORK_OUTCOMES_COMPLETE = "partial-work-outcomes-complete"
    CHECKPOINT_CONTROL_COMPLETE = "checkpoint-control-complete"
    FILESYSTEM_AUTHORITY_ATOMIC = "filesystem-authority-atomic"


class EvidenceState(StrEnum):
    SUPPORTED = "supported"
    CONTRADICTED = "contradicted"
    UNCERTAIN = "uncertain"


@dataclass(frozen=True)
class LabeledEvidenceFact:
    claim_id: str
    state: EvidenceState
    source_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.claim_id, str) or not REF_RE.fullmatch(self.claim_id):
            raise ValueError("evidence_fact_claim_id_invalid")
        if not isinstance(self.state, EvidenceState):
            raise ValueError("evidence_fact_state_invalid")
        if not _valid_refs(self.source_refs):
            raise ValueError("evidence_fact_source_refs_invalid")
        if self.state in {EvidenceState.SUPPORTED, EvidenceState.CONTRADICTED} and not self.source_refs:
            raise ValueError("evidence_fact_authority_required")
        if self.state is EvidenceState.UNCERTAIN and self.source_refs:
            raise ValueError("uncertain_evidence_refs_forbidden")


@dataclass(frozen=True)
class CheckpointFacts:
    route: str | None
    terminal: str | None
    identity_isolated: bool
    attempt_count: int

    def __post_init__(self) -> None:
        if self.route is not None and not DIAGNOSTIC_RE.fullmatch(self.route):
            raise ValueError("checkpoint_route_invalid")
        if self.terminal is not None and not DIAGNOSTIC_RE.fullmatch(self.terminal):
            raise ValueError("checkpoint_terminal_invalid")
        if not isinstance(self.identity_isolated, bool):
            raise ValueError("checkpoint_identity_invalid")
        if not isinstance(self.attempt_count, int) or not 0 <= self.attempt_count <= 1_000:
            raise ValueError("checkpoint_attempt_count_invalid")


@dataclass(frozen=True)
class LedgerFacts:
    accepted_refs: tuple[str, ...]
    conflict_detected: bool
    replay_idempotent: bool

    def __post_init__(self) -> None:
        if not _valid_refs(self.accepted_refs):
            raise ValueError("ledger_accepted_refs_invalid")
        if not isinstance(self.conflict_detected, bool) or not isinstance(self.replay_idempotent, bool):
            raise ValueError("ledger_flags_invalid")


@dataclass(frozen=True)
class SandboxFacts:
    paths_contained: bool
    artifact_hashes: tuple[tuple[str, str], ...]
    citation_bindings: tuple[tuple[str, tuple[str, ...]], ...]

    def __post_init__(self) -> None:
        if not isinstance(self.paths_contained, bool):
            raise ValueError("sandbox_containment_invalid")
        if not isinstance(self.artifact_hashes, tuple) or any(
            not isinstance(item, tuple)
            or len(item) != 2
            or not _contained_relative_path(item[0])
            or not isinstance(item[1], str)
            or not HASH_RE.fullmatch(item[1])
            for item in self.artifact_hashes
        ):
            raise ValueError("sandbox_artifact_hashes_invalid")
        if not isinstance(self.citation_bindings, tuple) or any(
            not isinstance(item, tuple)
            or len(item) != 2
            or not isinstance(item[0], str)
            or not REF_RE.fullmatch(item[0])
            or not _valid_refs(item[1])
            for item in self.citation_bindings
        ):
            raise ValueError("sandbox_citation_bindings_invalid")


@dataclass(frozen=True)
class WorkGateOutcome:
    route: str
    failure_codes: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.route not in {"repair", "exhausted"}:
            raise ValueError("work_gate_route_invalid")
        if (
            not isinstance(self.failure_codes, tuple)
            or not self.failure_codes
            or len(set(self.failure_codes)) != len(self.failure_codes)
            or any(not isinstance(code, str) or not DIAGNOSTIC_RE.fullmatch(code) for code in self.failure_codes)
        ):
            raise ValueError("work_gate_failure_codes_invalid")


@dataclass(frozen=True)
class WorkStateFacts:
    accepted_work_ids: tuple[str, ...] = ()
    failed_attempt_ids: tuple[str, ...] = ()
    gate_outcomes: tuple[WorkGateOutcome, ...] = ()

    def __post_init__(self) -> None:
        if not _valid_refs(self.accepted_work_ids):
            raise ValueError("work_state_accepted_ids_invalid")
        if not _valid_refs(self.failed_attempt_ids):
            raise ValueError("work_state_failed_ids_invalid")
        if (
            not isinstance(self.gate_outcomes, tuple)
            or len(self.gate_outcomes) > 8
            or any(not isinstance(outcome, WorkGateOutcome) for outcome in self.gate_outcomes)
        ):
            raise ValueError("work_state_gate_outcomes_invalid")


@dataclass(frozen=True)
class LifecycleFacts:
    research_ids: tuple[str, ...] = ()
    resume_request_ids: tuple[str, ...] = ()
    cancel_statuses: tuple[str, ...] = ()
    post_terminal_resume_code: str | None = None
    final_status: str | None = None
    durabilities: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for field_name in ("research_ids", "resume_request_ids", "cancel_statuses", "durabilities"):
            values = getattr(self, field_name)
            if (
                not isinstance(values, tuple)
                or len(values) > 16
                or any(not isinstance(value, str) or not REF_RE.fullmatch(value) for value in values)
            ):
                raise ValueError(f"lifecycle_{field_name}_invalid")
        for field_name in ("post_terminal_resume_code", "final_status"):
            value = getattr(self, field_name)
            if value is not None and (not isinstance(value, str) or not DIAGNOSTIC_RE.fullmatch(value)):
                raise ValueError(f"lifecycle_{field_name}_invalid")


@dataclass(frozen=True)
class FilesystemFaultOutcome:
    fault_point: str
    records_after_fault: int
    records_after_replay: int
    replay_disposition: str
    paths_contained: bool
    staging_residue: bool

    def __post_init__(self) -> None:
        if self.fault_point not in {
            "before_staging_write",
            "after_staging_fsync",
            "after_ledger_replace",
            "after_directory_fsync",
        }:
            raise ValueError("filesystem_fault_point_invalid")
        if (
            not isinstance(self.records_after_fault, int)
            or not 0 <= self.records_after_fault <= 3
            or not isinstance(self.records_after_replay, int)
            or not 0 <= self.records_after_replay <= 3
        ):
            raise ValueError("filesystem_fault_record_count_invalid")
        if self.replay_disposition not in {"appended", "replayed"}:
            raise ValueError("filesystem_fault_replay_disposition_invalid")
        if not isinstance(self.paths_contained, bool) or not isinstance(self.staging_residue, bool):
            raise ValueError("filesystem_fault_flags_invalid")


@dataclass(frozen=True)
class ScenarioObservation:
    checkpoint: CheckpointFacts
    ledger: LedgerFacts
    sandbox: SandboxFacts
    diagnostic_codes: tuple[str, ...] = ()
    degradation: str | None = None
    evidence_facts: tuple[LabeledEvidenceFact, ...] = ()
    work_state: WorkStateFacts = field(default_factory=WorkStateFacts)
    lifecycle: LifecycleFacts = field(default_factory=LifecycleFacts)
    filesystem_faults: tuple[FilesystemFaultOutcome, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.checkpoint, CheckpointFacts):
            raise ValueError("observation_checkpoint_invalid")
        if not isinstance(self.ledger, LedgerFacts):
            raise ValueError("observation_ledger_invalid")
        if not isinstance(self.sandbox, SandboxFacts):
            raise ValueError("observation_sandbox_invalid")
        if (
            not isinstance(self.diagnostic_codes, tuple)
            or len(self.diagnostic_codes) > 64
            or any(not isinstance(value, str) or not DIAGNOSTIC_RE.fullmatch(value) for value in self.diagnostic_codes)
        ):
            raise ValueError("observation_diagnostic_forbidden")
        if self.degradation is not None and not DIAGNOSTIC_RE.fullmatch(self.degradation):
            raise ValueError("observation_degradation_invalid")
        if (
            not isinstance(self.evidence_facts, tuple)
            or len(self.evidence_facts) > 128
            or any(not isinstance(fact, LabeledEvidenceFact) for fact in self.evidence_facts)
            or len({fact.claim_id for fact in self.evidence_facts}) != len(self.evidence_facts)
        ):
            raise ValueError("observation_evidence_facts_invalid")
        if not isinstance(self.work_state, WorkStateFacts):
            raise ValueError("observation_work_state_invalid")
        if not isinstance(self.lifecycle, LifecycleFacts):
            raise ValueError("observation_lifecycle_invalid")
        if (
            not isinstance(self.filesystem_faults, tuple)
            or len(self.filesystem_faults) > 8
            or any(not isinstance(outcome, FilesystemFaultOutcome) for outcome in self.filesystem_faults)
            or len({outcome.fault_point for outcome in self.filesystem_faults}) != len(self.filesystem_faults)
        ):
            raise ValueError("observation_filesystem_faults_invalid")


def evaluate_invariants(
    observation: ScenarioObservation,
    invariants: tuple[InvariantName, ...],
    *,
    max_attempts: int,
    expected_route: str | None = None,
) -> dict[InvariantName, bool]:
    if not isinstance(max_attempts, int) or max_attempts < 1:
        raise ValueError("invariant_attempt_bound_invalid")
    if not isinstance(invariants, tuple) or any(not isinstance(name, InvariantName) for name in invariants):
        raise ValueError("unknown_invariant")
    if len(set(invariants)) != len(invariants):
        raise ValueError("duplicate_invariant")

    accepted = set(observation.ledger.accepted_refs)
    cited = {ref for _claim_id, refs in observation.sandbox.citation_bindings for ref in refs}
    evidence_states = {fact.state for fact in observation.evidence_facts}
    gate_outcomes = observation.work_state.gate_outcomes
    has_repair = any(outcome.route == "repair" and "work_failed" in outcome.failure_codes for outcome in gate_outcomes)
    has_fatigue = any(
        outcome.route == "exhausted"
        and "fatigue_escalation" in outcome.failure_codes
        and "repair_budget_exhausted" not in outcome.failure_codes
        for outcome in gate_outcomes
    )
    has_budget_exhaustion = any(
        outcome.route == "exhausted"
        and "repair_budget_exhausted" in outcome.failure_codes
        and "fatigue_escalation" not in outcome.failure_codes
        for outcome in gate_outcomes
    )
    evaluations = {
        InvariantName.ROUTE_EXPECTED: expected_route is not None and observation.checkpoint.route == expected_route,
        InvariantName.TERMINAL_COMPLETED: observation.checkpoint.terminal == "completed",
        InvariantName.IDENTITY_ISOLATED: observation.checkpoint.identity_isolated,
        InvariantName.ATTEMPTS_BOUNDED: observation.checkpoint.attempt_count <= max_attempts,
        InvariantName.ACCEPTED_AUTHORITY: bool(accepted),
        InvariantName.NO_LEDGER_CONFLICT: not observation.ledger.conflict_detected,
        InvariantName.REPLAY_IDEMPOTENT: observation.ledger.replay_idempotent,
        InvariantName.PATHS_CONTAINED: observation.sandbox.paths_contained,
        InvariantName.ARTIFACTS_HASHED: bool(observation.sandbox.artifact_hashes),
        InvariantName.CITATIONS_BOUND: bool(observation.sandbox.citation_bindings) and cited <= accepted,
        InvariantName.LABELED_EVIDENCE_COMPLETE: evidence_states == set(EvidenceState),
        InvariantName.HONEST_DEGRADATION: (
            observation.degradation is not None
            and not observation.evidence_facts
            and not observation.sandbox.citation_bindings
        ),
        InvariantName.AUTHORITY_NOT_FORGED: (
            not observation.ledger.conflict_detected
            and observation.sandbox.paths_contained
            and observation.checkpoint.route not in {"unauthorized", "exhausted"}
        ),
        InvariantName.NO_PARTIAL_AUTHORITY: (
            not observation.ledger.accepted_refs
            and not observation.sandbox.artifact_hashes
            and not observation.sandbox.citation_bindings
        ),
        InvariantName.FAULT_OUTCOMES_COMPLETE: {
            "tools-unavailable",
            "wall-time",
            "cancellation-propagated",
        }
        <= set(observation.diagnostic_codes),
        InvariantName.BUDGET_EXHAUSTED: "budget-exhausted" in observation.diagnostic_codes,
        InvariantName.PARTIAL_WORK_OUTCOMES_COMPLETE: (
            bool(observation.work_state.accepted_work_ids)
            and bool(observation.work_state.failed_attempt_ids)
            and has_repair
            and has_fatigue
            and has_budget_exhaustion
        ),
        InvariantName.CHECKPOINT_CONTROL_COMPLETE: (
            len(observation.lifecycle.research_ids) >= 2
            and len(set(observation.lifecycle.research_ids)) == 1
            and len(observation.lifecycle.resume_request_ids) == 2
            and len(set(observation.lifecycle.resume_request_ids)) == 1
            and observation.lifecycle.cancel_statuses == ("cancelled", "cancelled")
            and observation.lifecycle.post_terminal_resume_code == "invalid_transition"
            and observation.lifecycle.final_status == "cancelled"
            and len(observation.lifecycle.durabilities) == len(observation.lifecycle.research_ids)
            and set(observation.lifecycle.durabilities) == {"restart_durable"}
        ),
        InvariantName.FILESYSTEM_AUTHORITY_ATOMIC: (
            {outcome.fault_point for outcome in observation.filesystem_faults}
            == {
                "before_staging_write",
                "after_staging_fsync",
                "after_ledger_replace",
                "after_directory_fsync",
            }
            and all(
                outcome.records_after_fault in {1, 2}
                and outcome.records_after_replay == 2
                and outcome.replay_disposition == ("replayed" if outcome.records_after_fault == 2 else "appended")
                and outcome.paths_contained
                and not outcome.staging_residue
                for outcome in observation.filesystem_faults
            )
        ),
    }
    return {name: evaluations[name] for name in invariants}


def _valid_refs(values: object) -> bool:
    return (
        isinstance(values, tuple)
        and len(values) <= 1_000
        and len(set(values)) == len(values)
        and all(isinstance(value, str) and REF_RE.fullmatch(value) for value in values)
    )


def _contained_relative_path(value: object) -> bool:
    return (
        isinstance(value, str)
        and bool(value)
        and not value.startswith(("/", "\\"))
        and ".." not in value.split("/")
        and "\\" not in value
        and len(value) <= 256
    )


__all__ = [
    "CheckpointFacts",
    "EvidenceState",
    "FilesystemFaultOutcome",
    "InvariantName",
    "LabeledEvidenceFact",
    "LifecycleFacts",
    "LedgerFacts",
    "SandboxFacts",
    "ScenarioObservation",
    "WorkGateOutcome",
    "WorkStateFacts",
    "evaluate_invariants",
]
