> req: REA-001, REA-002, REA-003, REA-004, REA-005, REA-006, REA-007

## ADDED Requirements

### Requirement: Hard checks verify citation availability, provenance, and HITL2 consumption

The readiness node SHALL run three deterministic hard checks on pre-existing state: accepted submissions are non-empty (`check_citation_availability`), all refs have valid `ref:` prefix (`check_provenance`), and at least one HITL2 request was consumed (`check_hitl2_consumption`). Failures SHALL be collected as `HardRuleFailure` tuples. Structural failures (no evidence, bad provenance) SHALL cause the node to route to `exhausted` with `BLOCKED` terminal status — these indicate preconditions that repair cannot fix.

#### Scenario: No accepted evidence is a structural failure
- **WHEN** `accepted_submission_refs` is empty
- **THEN** the node produces a `citation_no_accepted_evidence` failure and routes to `exhausted` with `terminal_status=BLOCKED`

#### Scenario: Valid evidence passes citation availability
- **WHEN** `accepted_submission_refs` contains at least one valid ref starting with `ref:`
- **THEN** the citation availability check produces zero failures

#### Scenario: Malformed ref is a provenance failure
- **WHEN** an accepted submission ref is `"bad-format"` (no `ref:` prefix)
- **THEN** the node produces a `provenance_invalid_ref` failure with the malformed ref

#### Scenario: No HITL2 consumption is a structural failure
- **WHEN** `consumed_request_ids` is empty
- **THEN** the node produces a `hitl2_not_consumed` failure and routes to `exhausted`

### Requirement: Semantic critic assesses answerability per must-answer question

The readiness node SHALL invoke a bounded read-only critic that receives must-answer questions and accepted evidence refs. The critic SHALL produce per-question answerability verdicts: `ready_substantive`, `ready_insufficient_judgment`, or `blocked_repair_required`. The initial implementation SHALL use a deterministic fallback; the real agent loop SHALL follow the evidence critic pattern (change 09). The critic SHALL NOT have web tools.

#### Scenario: Deterministic fallback marks all questions as ready_substantive
- **WHEN** the deterministic fallback critic runs with N must-answer questions
- **THEN** N `ready_substantive` verdicts are produced, each with a fallback note in `limitation_note`

#### Scenario: Critic has no web tools
- **WHEN** the critic agent's tool policy is inspected
- **THEN** `web_search` and `web_fetch` are absent from the allowed tool set

#### Scenario: Critic output that fails Pydantic schema validation raises error
- **WHEN** the critic returns JSON not matching `ReadinessCriticOutput`
- **THEN** the node raises `ValueError`

### Requirement: Report plan materializer produces immutable projection

A deterministic materializer SHALL produce a `ReadinessReportPlan` from the critic's verdicts and hard-rule results. The plan SHALL contain writable conclusions (from `ready_substantive`), mandatory uncertainties (from `ready_insufficient_judgment`), and prohibited upgrades. A `ContentRef` SHALL be written to the `readiness_report_plan` checkpoint field with a valid sandbox path and content hash.

#### Scenario: ready_substantive verdicts become writable conclusions
- **WHEN** the critic produces `ready_substantive` for Q1 and Q3
- **THEN** the report plan lists Q1 and Q3 as writable conclusions with backing claim IDs

#### Scenario: ready_insufficient_judgment verdicts become mandatory uncertainties
- **WHEN** the critic produces `ready_insufficient_judgment` for Q2 with limitation "data is contradictory"
- **THEN** the report plan lists Q2 under mandatory uncertainties with that limitation

#### Scenario: blocked_repair_required verdicts produce neither conclusions nor uncertainties
- **WHEN** the critic produces `blocked_repair_required` for Q4
- **THEN** Q4 is absent from both conclusions and uncertainties; `readiness_blocked_count` is incremented

#### Scenario: Report plan is checkpointed
- **WHEN** the materializer produces a report plan
- **THEN** a `ContentRef` with a valid `sandbox_path` matching `workspace/deep-research/r_{43-char-id}/review/report-plan.json` (per `SANDBOX_PATH_RE`) and a 43-char `content_hash` (per `CONTENT_HASH_RE`) is written to `readiness_report_plan`

### Requirement: Node determines its own route based on hard-rule results and critic verdicts

The readiness node SHALL write its own `route` field (non-gated pattern, like hitl2 and rerun). Route determination SHALL follow this priority: structural hard-rule failures → `exhausted` with `BLOCKED`; any `blocked_repair_required` critic verdicts → `repair_targeted`; otherwise → `pass`.

#### Scenario: All checks pass routes to pass
- **WHEN** all hard rules produce zero failures AND `readiness_blocked_count` is zero
- **THEN** the node writes `route = "pass"` routing to `final_delivery`

#### Scenario: Blocked questions route to repair_targeted
- **WHEN** hard rules pass but `readiness_blocked_count > 0`
- **THEN** the node writes `route = "repair_targeted"` routing to `targeted_evidence`

#### Scenario: Structural failures route to exhausted
- **WHEN** hard rules detect `citation_no_accepted_evidence`
- **THEN** the node writes `route = "exhausted"` with `terminal_status = BLOCKED`

#### Scenario: Mixed structural and critic failures prioritize structural
- **WHEN** hard rules detect a provenance failure AND the critic reports blocked questions
- **THEN** the node routes to `exhausted` (structural failure takes priority)

### Requirement: Node collects all failures before determining route

The readiness node SHALL collect all hard-rule failures and critic verdicts before determining the route. No single failure SHALL short-circuit the collection. All failures SHALL be written to `readiness_hard_failures` for diagnostic traceability.

#### Scenario: All failures appear in checkpoint state
- **WHEN** hard rules detect one citation failure and one provenance failure
- **THEN** both failures appear in `readiness_hard_failures` written to checkpoint state

### Requirement: Critic runs under bounded read-only policy

The readiness critic SHALL execute under an `ExecutionPolicy` with model-call limits, token budget, wall-time timeout, read-only filesystem access, and zero web tools. Invalid critic output SHALL fail closed.

#### Scenario: Critic output schema mismatch fails closed
- **WHEN** the critic returns JSON that does not validate against `ReadinessCriticOutput`
- **THEN** the node raises `ValueError`

### Requirement: Mixed-graph integration with unchanged topology

Real readiness SHALL require `hitl2=real`. Selecting `readiness=real` without `hitl2=real` SHALL fail before graph invocation. Full-fake readiness SHALL remain unchanged (fixture gate provides route). Topology SHALL be unchanged.

#### Scenario: Real readiness requires real hitl2
- **WHEN** a recipe selects `readiness=real` without `hitl2=real`
- **THEN** recipe construction fails with a typed dependency error

#### Scenario: Full-fake readiness unchanged
- **WHEN** the full-fake graph reaches the readiness node
- **THEN** it returns a no-op update with the fixture gate providing the route

#### Scenario: Real readiness coexists with fake final_delivery
- **WHEN** readiness is real but final_delivery is still fake
- **THEN** the graph routes `pass` → `final_delivery` and the fake final handles it
