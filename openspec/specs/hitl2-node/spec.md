# hitl2-node Specification

> req: HIT-001, HIT-002, HIT-003
## Purpose
Real human decision node with deterministic brief builder and interrupt/resume lifecycle.

## Requirements



### Requirement: Deterministic brief builder generates decision brief from accepted findings

The HITL2 brief builder SHALL generate a structured decision brief from accepted
findings, synthesis gaps, and critic verdicts present in checkpoint state. The brief
SHALL include a summary of confirmed findings, key uncertainties, unresolved gaps
with priority, and the available decision actions. The brief SHALL only reference
data already present in accepted state; it SHALL NOT fabricate new facts, call an
LLM, or read sandbox files.

#### Scenario: Brief built from accepted findings
- **WHEN** HITL2 runs after wave2_synthesis has produced accepted findings
- **THEN** a structured brief is produced containing finding summaries, unresolved gaps, and available actions

#### Scenario: Brief does not fabricate content
- **WHEN** accepted findings are empty
- **THEN** the brief honestly reports zero findings rather than generating placeholder text

### Requirement: Interrupt presents brief and parses closed-set user decision

HITL2 SHALL present the brief to the user through the existing interrupt pipeline
already implemented in the fake: generate a `request_id` (encoding generation),
create `PendingResearchInterrupt` with `HumanInputRequest` in `CHOICE` mode and
options from the `Hitl2Decision` enum (`proceed`, `revise_view`, `repair`, `rerun`,
`stop`), call `interrupt()`, validate the response via `AcceptedHumanResponse` with
request-id matching, and route to the corresponding topology edge. Cancellation
SHALL be handled via `InternalCancelDecision`. The `request_id` already encodes
the generation, providing stale-resume detection without additional state fields.

#### Scenario: User selects a decision route
- **WHEN** user responds to the interrupt with a valid `Hitl2Decision` value
- **THEN** the node routes to the corresponding edge and records consumed request/message ids

#### Scenario: User cancels during interrupt
- **WHEN** the runtime delivers an `InternalCancelDecision` instead of a user response
- **THEN** the node routes to `cancel` with terminal status `CANCELLED`

#### Scenario: Stale resume is rejected by request-id mismatch
- **WHEN** the graph resumes after an interrupt but the generation has changed (recomputed request_id differs)
- **THEN** `AcceptedHumanResponse` validation fails and the graph raises `ValueError`

#### Scenario: Invalid response is rejected
- **WHEN** the resume payload does not match the expected `AcceptedHumanResponse` schema
- **THEN** a `ValueError` is raised and the graph fails closed

### Requirement: Mixed-graph integration requires full real chain

Real HITL2 SHALL require `wave2_synthesis=real` (which transitively requires the
full chain through wave0, wave1, and targeted_evidence). Selecting `hitl2=real`
without `wave2_synthesis=real` SHALL fail before graph invocation. Full-fake HITL2
SHALL remain unchanged. Topology SHALL be unchanged.

#### Scenario: Real HITL2 requires real wave2_synthesis
- **WHEN** a recipe selects `hitl2=real` without `wave2_synthesis=real`
- **THEN** recipe construction fails with a typed dependency error

#### Scenario: Full-fake HITL2 remains unchanged
- **WHEN** the full-fake graph reaches HITL2
- **THEN** it runs the fixture interrupt path with no real findings and no regression
