# bootstrap-node Specification

> req: BON-001, BON-002, BON-003, BON-004, BON-005

## Purpose

The real bootstrap node owns atomic establishment of the minimal research bundle directory and
its schema/version marker, the pure binding-validation that replaces the change-01 fake fixture
pass, deterministic failure/recovery handling, research-scoped establishment that preserves the
existing start/resume/status/cancel lifecycle invariants, and mixed-graph integration where
bootstrap is the first real phase while every other phase remains fake. It performs no research
model call; identity derivation and start/idempotency/conflict semantics remain owned by the
lifecycle handler (REG-004).

## Requirements

### Requirement: Bootstrap atomically establishes the research bundle

The real bootstrap node SHALL atomically establish the minimal research bundle directory tree
(`request/` only; all other subtrees remain lazy) under the canonical `bundle_root`
(`workspace/deep-research/<research_id>/`) and write a schema/version marker at
`workspace/deep-research/<research_id>/request/marker.json` before any route is published. The
marker SHALL be a versioned JSON with `schema_version=1` binding `research_id`,
`start_message_id`, `request_digest`, and `state_schema_version`. Establishment SHALL reuse the
change-04 shared-workspace capability (bounded POSIX lock, same-directory replace, durability
sync) and SHALL fail closed with `work_unit_storage_unavailable` on an unsupported provider
before writing anything. A partial establishment (missing or mismatched marker) SHALL be
cleaned up and re-established on re-entry so it is never observable as an active or completed
bundle. The bootstrap node SHALL NOT create a DPT `rb_status.json` phase cursor or any
evidence, work-spec, or DPT control file.

#### Scenario: Fresh establishment binds the checkpoint identity
- **WHEN** the real bootstrap runs for a fresh research id with a validated checkpoint
- **THEN** it creates the `request/` subtree under `workspace/deep-research/<research_id>/` and writes `marker.json` (`schema_version=1`) whose `research_id`, `start_message_id`, `request_digest`, and `state_schema_version` equal the checkpoint's, before the route is published

#### Scenario: Partial directory is recovered, not mistaken for active
- **WHEN** establishment is interrupted leaving a bundle directory whose marker is missing or mismatched, and the bootstrap re-enters
- **THEN** it detects the missing or mismatched marker, removes the partial tree, and re-establishes atomically; no reader can observe the partial bundle as an active or completed research

#### Scenario: Re-entry with an existing matching marker is idempotent
- **WHEN** bootstrap re-enters after a crash that left a complete marker matching the checkpoint binding
- **THEN** it re-establishes (overwrites idempotently) and routes normally, without treating the existing marker as a conflict or leaving a duplicate

#### Scenario: Unsupported workspace fails closed before any write
- **WHEN** the shared-workspace capability is unavailable for the thread's provider/mount
- **THEN** establishment raises `work_unit_storage_unavailable` before creating any directory or marker, and no bundle state is published

### Requirement: Bootstrap binding-validation determines the route

The real bootstrap node SHALL run a pure binding-validation that compares the on-disk marker to
the checkpointed control state and determines the bootstrap route from that validation, replacing
the fake fixture pass. The validation SHALL produce typed `FailureCode` values from the closed
gate-kernel registry and SHALL perform no research model, web, MCP, ACP, or DeerFlow `task`
subagent call. The bootstrap node SHALL remain non-gated and SHALL NOT consult `fixture_plan`
for its route. On a successful binding the node SHALL route `needs_input` to `hitl1`; it SHALL
NOT emit `profile_complete` because it performs no profile derivation.

#### Scenario: Bound marker routes to HITL1 with no model call
- **WHEN** the marker is bound to the checkpoint (`research_id`, `start_message_id`, `request_digest`, `schema_version` all match)
- **THEN** the bootstrap routes `needs_input` to `hitl1` and makes no research model call

#### Scenario: Marker divergence is rejected and fails closed
- **WHEN** the read-back marker diverges from the checkpoint binding after establishment (identity mismatch or schema mismatch)
- **THEN** the validation produces a typed `FailureCode` and the bootstrap fails closed (terminal `BLOCKED`, `route=exhausted`) rather than routing `needs_input` onward

#### Scenario: The fixture pass is replaced
- **WHEN** a fixture supplies a `fixture_plan` bootstrap sequence and the real bootstrap runs
- **THEN** the real bootstrap derives its route from the binding validation, not from `fixture_plan`

### Requirement: Bootstrap failure is deterministic and fail-closed

Bootstrap failure SHALL perform deterministic cleanup and bounded retry with typed failure codes
and SHALL never invoke a research LLM or publish an inconsistent bundle or route. Recoverable
establishment failures (partial directory, transient lock contention, or a stale/mismatched
marker found on entry) SHALL be cleaned up and retried internally up to a bound. A divergence
or unsupported marker `schema_version` that persists AFTER a fresh establish indicates
corruption (the marker was just written bound to this checkpoint) and SHALL fail closed to a
terminal `BLOCKED` lifecycle with `route=exhausted` so the topology routes to `END`; exhausted
retries likewise fail closed.

#### Scenario: Recoverable failure is retried without a model call
- **WHEN** a recoverable failure occurs (partial directory, transient lock contention, or a stale/mismatched marker found on entry)
- **THEN** the bootstrap cleans up and retries internally up to a bound, succeeds, and makes no research LLM call

#### Scenario: Post-establish divergence terminates fail-closed
- **WHEN** a fresh establish completes but the read-back marker still diverges from the checkpoint, or retries are exhausted
- **THEN** the bootstrap sets `terminal_status=BLOCKED` with `route=exhausted` toward `END` and publishes no inconsistent bundle or route

#### Scenario: No research surface is invoked on failure
- **WHEN** bootstrap establishment or validation fails
- **THEN** no research LLM, web, MCP, ACP, or DeerFlow `task` subagent call is made

### Requirement: Bootstrap preserves lifecycle invariants and keeps establishment research-scoped

The real bootstrap SHALL NOT weaken the existing start/resume/status/cancel invariants owned by
REG-004: duplicate same-message start remains idempotent, a different-message start on an active
thread still returns `thread_research_exists`, and an already-terminal research is not
re-established or re-routed. The new behavior the bootstrap adds is research-scoped
establishment and binding-level fail-closed: the `BootstrapBundleStore` SHALL be scoped to the
checkpoint's `research_id` alone, SHALL NOT read, write, or bind another research's bundle, and
the bootstrap SHALL fail closed when the on-disk marker carries an unsupported marker
`schema_version` or a `research_id` that differs from the checkpoint's. Path/user/thread
isolation itself is inherited from `derive_research_id` and `derive_research_thread_key`
(REG-004/RUI-003) and is not re-implemented here.

#### Scenario: Duplicate same-message start stays idempotent (REG-004 regression)
- **WHEN** a duplicate same-message start re-enters an existing real-bootstrap lifecycle
- **THEN** the existing lifecycle is resumed and no second bundle is established

#### Scenario: Different-message start still conflicts (REG-004 regression)
- **WHEN** a start targets a thread that already has an active research with a different message or digest
- **THEN** the lifecycle handler returns `thread_research_exists` without establishing a second bundle or touching the active research's bundle

#### Scenario: Already-terminal research is not re-established (REG-004 regression)
- **WHEN** a start targets a thread whose research is already terminal
- **THEN** the terminal status is reported without re-establishing the bundle or re-routing bootstrap

#### Scenario: Establishment is research-scoped
- **WHEN** the real bootstrap establishes a bundle for research A
- **THEN** it touches only `workspace/deep-research/<research_id_A>/` and never reads, writes, or binds the bundle of any other research id

#### Scenario: Marker schema mismatch and cross-research binding are rejected
- **WHEN** the on-disk marker carries an unsupported `schema_version` or a `research_id` that differs from the checkpoint's
- **THEN** the bootstrap fails closed and does not route onward to research

### Requirement: Real bootstrap integrates into the mixed implementation map

The real bootstrap factory SHALL be selectable by the existing per-node fake/real implementation
map (REG-001) in place of the fake, while every other phase remains fake, preserving the
normalized topology and the full-fake lifecycle end-to-end path. The full-fake map (all phases
fake) SHALL remain unchanged. The lifecycle handlers SHALL be able to run the mixed graph, so
`ResearchGraphRecipe` SHALL accept an `implementation_modes` override (default all-fake) without
changing the production full-fake recipe. The mixed-graph end-to-end run SHALL keep the lifecycle
result `implementation_mode=full_fake` because bootstrap produces no research findings or report.

#### Scenario: Mixed map selects the real bootstrap
- **WHEN** the implementation map selects `real` for bootstrap and `fake` for every other phase
- **THEN** the graph compiles, the real bootstrap factory is selected (not the unavailable sentinel), and the normalized node order and all non-bootstrap edges are unchanged

#### Scenario: Lifecycle handlers can run the mixed graph
- **WHEN** `ResearchGraphRecipe` is created with `implementation_modes` setting `bootstrap=real` and every other phase `fake`
- **THEN** the lifecycle handlers compile and run the mixed graph, selecting the real bootstrap factory, while the default recipe remains all-fake

#### Scenario: Full-fake map is unchanged
- **WHEN** the implementation map selects `fake` for every phase
- **THEN** the fake bootstrap is selected and the full-fake lifecycle end-to-end path is unchanged

#### Scenario: Mixed end-to-end remains full_fake
- **WHEN** the mixed graph runs end-to-end through bootstrap and the remaining fake phases
- **THEN** bootstrap establishes the bundle and routes to `hitl1`, every remaining fake phase completes without a research model call, and the lifecycle result remains `implementation_mode=full_fake`
