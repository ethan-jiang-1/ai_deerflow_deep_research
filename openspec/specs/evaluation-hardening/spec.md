# evaluation-hardening Specification

> req: EVH-001, EVH-002, EVH-003, EVH-004, EVH-005, EVH-006, EVH-007, EVH-008, EVH-009, EVH-010

## Purpose

Provide deterministic workflow conformance, live behavioral evaluation, full-real release acceptance, and mechanical regression traceability for Deep Research.

## Requirements

### Requirement: Eval corpus framework supports replay-based testing

The eval framework SHALL drive reusable typed scenarios through deterministic workflow entrypoints with scripted model and tool adapters. The corpus SHALL cover quick factual, claim verification, insufficient evidence, malformed structured output, unavailable tools, budget exhaustion, partial worker success, checkpoint control, and sandbox/filesystem failure. Deterministic corpus execution SHALL require no model API, external network, or operator credentials.

#### Scenario: One scenario is reusable across deterministic and live modes
- **WHEN** a scenario declares both scripted inputs and live capability requirements
- **THEN** deterministic conformance and live evaluation SHALL consume the same objective, expected invariants, artifact expectations, and metric definitions

#### Scenario: Insufficient evidence remains an acceptable bounded outcome
- **WHEN** the scripted sources do not support the requested conclusion
- **THEN** the workflow SHALL record the limitation without fabricating an accepted claim or citation

### Requirement: Quality metrics are pure functions

Quality metrics SHALL be pure Python functions with no model calls or I/O. They SHALL compute citation precision, citation completeness, must-answer coverage, source diversity, contradiction recall, and unsupported-major-claim counts from validated scenario outcomes. Metric evaluation SHALL distinguish hard correctness and security invariants from quality scores whose thresholds require an observed live baseline.

#### Scenario: Hard invariant failure is not averaged into a quality score
- **WHEN** a scenario produces an unauthorized route, forged submission, invalid artifact binding, or incorrect terminal lifecycle outcome
- **THEN** evaluation SHALL fail independently of citation, coverage, diversity, or cost scores

#### Scenario: Quality scores are reproducible for a replay outcome
- **WHEN** the same validated replay outcome is evaluated twice
- **THEN** all quality metric values SHALL be identical

### Requirement: Fault injection covers critical graph points

Fault injection tests SHALL exercise real lifecycle, checkpoint, runtime bridge, store, and graph seams for crash, timeout, cancel, duplicate resume, partial write, stale checkpoint, and conflicting worker-result faults. Each fault SHALL produce verified recovery, an idempotent replay, or an explicit typed terminal outcome without silent partial success.

#### Scenario: Duplicate resume crosses the lifecycle handler seam
- **WHEN** the same consumed HITL response is submitted twice through the resume handler
- **THEN** the second submission SHALL be idempotent and SHALL NOT advance the graph or duplicate artifacts

#### Scenario: Partial publication is recovered through the authoritative store
- **WHEN** a fault is injected at a supported atomic-publication boundary
- **THEN** recovery SHALL expose either the prior committed state or the single durable new state, never a partially authoritative result

### Requirement: Adversarial source tests verify isolation

Adversarial scenarios SHALL pass prompt-injected and authority-forging source content through the real untrusted-data, worker, submission, and gate path. External content SHALL NOT override routing, forge accepted submissions, mutate checkpoint authority, escape attempt-scoped paths, or influence deterministic gate verdicts except through validated evidence fields.

#### Scenario: Route-like source text remains untrusted data
- **WHEN** a scripted tool result contains route, gate, or submission instructions
- **THEN** the real worker and gate path SHALL preserve graph-owned routing and ledger authority

#### Scenario: Adversarial path request is contained
- **WHEN** model output or tool input attempts to read or write outside declared roots
- **THEN** policy SHALL deny the operation and no out-of-scope artifact SHALL be created

### Requirement: Release gate combines deterministic CI with optional LLM canary

The release system SHALL expose three non-overlapping execution lanes: network-free deterministic PR gates, credentialed short live canaries and behavioral evaluation, and manual/release full-real acceptance. Real-model tests SHALL carry the `requires_llm` marker. Missing required credentials in an explicitly selected live or release lane SHALL fail preflight rather than silently skip. Full-real acceptance SHALL use unique thread, run, and research identities and SHALL report every retry.

#### Scenario: Default test command is network-free
- **WHEN** the normal PR test target runs without model or tool credentials
- **THEN** no `requires_llm`, Postgres, or release-acceptance scenario SHALL be selected and no external network SHALL be required

#### Scenario: Nightly canary runs the shortest real prefixes
- **WHEN** the scheduled live lane has valid credentials
- **THEN** it SHALL run start-to-HITL1, HITL1-to-topic-planning, and one-topic Wave0 canaries and report hard invariants, quality metrics, retries, tokens, cost where available, and wall time

#### Scenario: Release acceptance uses isolated identity
- **WHEN** full-real acceptance is invoked more than once
- **THEN** each invocation SHALL use new thread, run, and research identities and SHALL NOT inherit a prior blocked or completed checkpoint

### Requirement: Recorded incidents close at the lowest responsible seam

Every incident recorded in `test-assets-postmortem-real-mode-integration.md` SHALL map to at least one current deterministic test selector at the lowest stable responsible seam. The inventory SHALL identify replaced or duplicate historical recommendations and SHALL include all-real compilation, context forwarding, model/tool/sandbox readiness, mounted filesystem stores, capability/policy routing, budgets, structured output, gate fatigue, and checkpoint identity.

#### Scenario: Incident inventory cannot claim stale coverage
- **WHEN** a mapped test selector is renamed, removed, skipped by the deterministic lane, or no longer reaches the stated seam
- **THEN** the incident-coverage check SHALL fail with the incident id and missing selector or seam

#### Scenario: Integration failure is diagnosable without full E2E
- **WHEN** a recorded interface mismatch is reintroduced
- **THEN** a deterministic test SHALL fail before live or release execution and SHALL identify the affected scenario, seam, and stable error or invariant

### Requirement: Scenarios declare stable test seams and authenticity

Each reusable scenario SHALL declare a stable id, risk family, owning requirement ids, optional regression ids, entrypoint, required authenticity level, initial context/checkpoint/workspace conditions, scripted inputs where applicable, expected routes and terminal outcome, artifact and citation expectations, hard invariants, applicable metrics, and permitted degradation. Supported authenticity levels SHALL distinguish fake graph, real node with fake capabilities, scripted real workflow, live real dependencies, and full-real pipeline.

#### Scenario: Lower authenticity cannot satisfy a higher claim
- **WHEN** a scenario is executed with fake nodes or fake node capabilities
- **THEN** its result SHALL NOT be reported as agent-loop, live-model, or full-real coverage

#### Scenario: Scenario diagnostics carry stable identity
- **WHEN** a scenario fails in any execution lane
- **THEN** the failure output SHALL include its scenario id, execution lane, authenticity level, and failed invariant or metric

### Requirement: Deterministic tests conform real agent workflows

Every available real node SHALL have at least one deterministic success scenario and one highest-risk failure, repair, degradation, or exhausted scenario through its stable node interface. Every node that uses a model or tool SHALL additionally have coverage through the real runtime bridge, middleware, execution policy, budget, structured-output, submission, gate, checkpoint, and filesystem path applicable to that node, replacing only external model and tool adapters. High-risk real prefixes SHALL run as mixed graphs with later unrelated nodes kept fake.

#### Scenario: Scripted worker traverses the complete policy path
- **WHEN** a scripted model issues an allowed web tool call and returns a valid worker result
- **THEN** the real resolver, bridge, middleware, policy, budget, validator, submit path, gate, checkpoint, and attempt-scoped artifact path SHALL all be exercised and the work SHALL reach its expected accepted or degraded outcome

#### Scenario: Malformed output follows bounded repair policy
- **WHEN** scripted model responses remain malformed through the configured repair attempts
- **THEN** the node SHALL reach its specified fallback or typed exhausted outcome without fabricated success

### Requirement: Test selection and requirement traceability are mechanical

Stable commands and markers SHALL separate fast deterministic, integration/workflow, live, and release-acceptance suites. The default complete deterministic command SHALL include all project-owned zero-API tests while excluding credentialed and deferred-provider tests. A governance checker SHALL require every alive requirement to be referenced by at least one collected deterministic test and SHALL reject unknown requirement ids. Selection and traceability checks SHALL test their own failure behavior.

#### Scenario: Requirement without a collected deterministic test fails governance
- **WHEN** an alive requirement has no valid test-side `@impl` reference in the deterministic suite
- **THEN** the checker SHALL fail and report the uncovered requirement id

#### Scenario: Explicit live selection does not overlap deterministic PR
- **WHEN** test collection is performed for the PR and live targets
- **THEN** every `requires_llm` test SHALL appear only in the live or release selection and every deterministic hard-gate scenario SHALL remain in the PR selection

### Requirement: Higher-level failures descend into deterministic assets

Every defect discovered by live evaluation or full-real acceptance SHALL be classified by risk and stable seam. When the behavior can be reproduced without the external provider, the fixing change SHALL add the smallest deterministic scenario that fails before the fix and passes after it. Provider-only distribution changes SHALL remain recorded as live scenarios with captured redacted diagnostics and SHALL NOT be misrepresented as deterministic coverage.

#### Scenario: E2E integration defect gains a deterministic regression
- **WHEN** full-real acceptance exposes a context, policy, parser, store, graph, or artifact-contract defect
- **THEN** the fixing change SHALL add a deterministic regression at the lowest responsible seam before the defect is considered closed

#### Scenario: Provider-only behavior remains a live concern
- **WHEN** a failure depends on nondeterministic model or external-tool behavior that cannot be faithfully replayed
- **THEN** it SHALL remain a labeled live scenario with attempts and redacted evidence rather than a tautological deterministic test
