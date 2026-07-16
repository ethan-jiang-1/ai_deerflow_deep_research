> req: RUO-001, RUO-002, RUO-003, RUO-004

## ADDED Requirements

### Requirement: Non-interactive mode requires policy

Non-interactive start/resume SHALL be denied unless a `non_interactive_policy` dict with `auto_profile` and `auto_proceed` boolean keys is provided in the runtime context. When the policy is present, it SHALL flow through `ResearchActionInput` into the initial graph state. Without policy, non-interactive SHALL be denied with `INTERACTIVE_REQUIRED` as before.

#### Scenario: Non-interactive with policy is allowed
- **WHEN** runtime context has `non_interactive=True` and `non_interactive_policy={"auto_profile": true, "auto_proceed": true}`
- **THEN** start/resume proceeds and the policy is written to checkpoint state via initial graph values

#### Scenario: Non-interactive without policy is denied
- **WHEN** runtime context has `non_interactive=True` but no `non_interactive_policy`
- **THEN** start/resume is denied with `INTERACTIVE_REQUIRED`

#### Scenario: Interactive mode is unaffected
- **WHEN** `non_interactive` is not set (default interactive)
- **THEN** start/resume proceeds normally regardless of policy presence

### Requirement: HITL nodes auto-respond under non-interactive policy

HITL1 SHALL check `state.get("non_interactive_policy", {}).get("auto_profile")`. When True, HITL1 SHALL skip `interrupt()`, write default profile values, set `degraded_profile=True`, and record an audit note. HITL2 SHALL check `auto_proceed` similarly. When True, HITL2 SHALL skip `interrupt()`, route to `proceed`, and record an audit note.

#### Scenario: HITL1 auto-profile generates default profile
- **WHEN** `non_interactive_policy.auto_profile` is True
- **THEN** HITL1 writes default profile with `degraded_profile=True` and routes to `accepted`

#### Scenario: HITL2 auto-proceed routes to proceed
- **WHEN** `non_interactive_policy.auto_proceed` is True
- **THEN** HITL2 routes to `proceed` with an audit note

#### Scenario: HITL nodes invoke interrupt normally when policy absent
- **WHEN** `non_interactive_policy` is None or absent from state
- **THEN** HITL1 and HITL2 invoke `interrupt()` as normal

### Requirement: Orphan attempts detected on recovery

On crash recovery, work attempts in `running` status whose owning work_spec generation is lower than the current graph generation SHALL be detected as orphaned and transitioned to `failed` with orphan reason.

#### Scenario: Orphan attempt from prior generation is cleaned up
- **WHEN** recovery detects a running attempt with generation 0 while the current graph generation is 1
- **THEN** the attempt is transitioned to `failed` with orphan reason

### Requirement: Cross-cutting changes do not alter topology or full-fake

Non-interactive policy SHALL NOT alter graph topology or full-fake behavior. Full-fake graph SHALL produce identical outputs.

#### Scenario: Full-fake graph unchanged
- **WHEN** the full-fake graph runs with runtime hardening changes
- **THEN** all nodes produce the same outputs as before
