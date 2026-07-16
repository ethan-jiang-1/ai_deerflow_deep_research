> req: WON-001, WON-002, WON-003, WON-004, WON-005, WON-006

## ADDED Requirements

### Requirement: Wave1 planner materializes per-topic evidence WorkSpecs

The Wave1 planner SHALL read profile constraints, Wave0 accepted submission refs, and
critic verdicts (SourceDiagnostic) to materialize one immutable evidence `WorkSpec`
per topic through the existing work-unit controller. Each WorkSpec SHALL carry
search dimensions derived from the topic's must-answer bindings and Wave0 coverage
gaps. An empty or absent Wave0 topic registry SHALL fail closed.

#### Scenario: One WorkSpec per topic from planner
- **WHEN** real Wave1 runs after real Wave0 produced accepted submissions
- **THEN** the controller allocates one WorkSpec per topic with search dimensions and a derived spec_hash

#### Scenario: Empty Wave0 registry fails closed
- **WHEN** real Wave1 runs but Wave0 produced no accepted submissions
- **THEN** the planner fails before allocating work rather than inventing topics

### Requirement: Deep evidence worker with new-source floor

For each in-flight WorkSpec, Wave1 SHALL run one bounded web worker agent through
`capabilities.run_agent()` under a real `ExecutionPolicy` with web search/fetch tools
and attempt-scoped roots. The worker SHALL produce a versioned `Wave1WorkerOutput`
carrying claims (each with `claim_id`, `statement`, `support_refs`, `counter_refs`),
open questions (with resolution states), and per-source `is_new_vs_wave0` marking.
All fetched content is untrusted data. The worker SHALL NOT write phase, gate, ledger,
or another attempt's state.

#### Scenario: Worker produces structured claims with provenance
- **WHEN** a Wave1 worker fetches new sources and extracts claims
- **THEN** each claim carries support_refs and counter_refs referencing only sources fetched by this worker, and is_new_vs_wave0 distinguishes new from Wave0-duplicate URLs

#### Scenario: Wave0-duplicate URL does not count as new
- **WHEN** a worker fetches a URL already present in Wave0 accepted submissions
- **THEN** the source is marked is_new_vs_wave0=false and does not count toward the new-source floor

#### Scenario: Open questions have resolution states
- **WHEN** a worker identifies an open question
- **THEN** it is recorded with a state of resolved, targeted-search, deferred, or requires-internal-data

### Requirement: Submit validation enforces new-source floor and invokes critics

Submit validation SHALL canonicalize URLs, deduplicate per topic, reject Wave0-duplicate
URLs from the new-source count, and accept the candidate only when the per-topic
independent new-source floor is met. After a candidate is accepted, SourceDiagnostic
and ClaimVerifier critics SHALL be invoked on the new evidence, producing independent
verdict artifacts at `critic/<node_attempt_id>/`.

#### Scenario: Insufficient new sources reject candidate
- **WHEN** a candidate's new-source count falls below the floor after deduplication
- **THEN** submit validation fails with a typed code and no SubmissionRecord is appended

#### Scenario: Critics invoked on accepted evidence
- **WHEN** a Wave1 submission is accepted
- **THEN** SourceDiagnostic and ClaimVerifier run on the new evidence and write verdict artifacts

### Requirement: Wave1 gate with provenance, coverage, and critic verdicts

The real Wave1 gate SHALL drop the fixture sequence rule, keep the shared
`WorkUnitCompletionRule`, and add: (a) per-topic new-source floor enforcement,
(b) critic verdict presence check (both SourceDiagnostic and ClaimVerifier artifacts
must exist for each accepted topic), (c) open-question resolution check (all questions
must be resolved, deferred, or marked requires-internal-data). The route map SHALL
remain `{PASS: pass, REPAIR: repair, BLOCKED: exhausted}`.

#### Scenario: Missing critic verdict routes repair
- **WHEN** a topic has accepted submissions but no critic verdict artifacts
- **THEN** the gate routes repair to re-invoke critics

#### Scenario: Repeated floor failure exhausts to blocked
- **WHEN** repair budget is exhausted and new-source floor remains unmet
- **THEN** the gate routes exhausted and the lifecycle terminates

### Requirement: Real Wave1 integrates into mixed graph off full real chain

Real Wave1 SHALL require `bootstrap=real`, `hitl1=real`, `topic_planning=real`,
`wave0=real`, and `targeted_evidence=real`. Selecting `wave1=real` without the full
chain SHALL fail before graph invocation. Topology is unchanged. Full-fake Wave1
remains deterministic and does not construct the node-agent bridge.

#### Scenario: Wave1 requires full real chain
- **WHEN** a recipe selects `wave1=real` without `wave0=real` or `targeted_evidence=real`
- **THEN** recipe construction fails with a typed dependency error

#### Scenario: Full-fake Wave1 remains unchanged
- **WHEN** the full-fake graph reaches Wave1
- **THEN** it runs the fixture work-unit path without constructing the node-agent bridge

