> req: EVH-001, EVH-002, EVH-005, EVH-006, EVH-007, EVH-008, EVH-009, EVH-010

## MODIFIED Requirements

### Requirement: Eval corpus framework supports replay-based testing

The eval framework SHALL drive reusable typed scenarios through deterministic production workflow entrypoints with scripted model and tool adapters. The corpus SHALL cover quick factual, claim verification, insufficient evidence, malformed structured output, unavailable tools, budget exhaustion, partial worker success, checkpoint control, and sandbox/filesystem failure. Every listed scenario SHALL bind executable typed scripted inputs to a collected deterministic selector and SHALL produce assertions from checkpoint, validated-ledger, or contained-sandbox authority. A scenario that contains only descriptive labels, synthetic outcome dictionaries, or an unbound executor SHALL fail asset governance. Deterministic corpus execution SHALL require no model API, external network, or operator credentials.

#### Scenario: One scenario is reusable across deterministic and live modes
- **WHEN** a scenario declares scripted inputs and live capability requirements
- **THEN** deterministic conformance and live evaluation SHALL consume the same objective, expected invariants, artifact and citation expectations, metric definitions, and permitted degradation while using lane-appropriate external adapters

#### Scenario: Every first-wave scenario executes
- **WHEN** asset governance collects the deterministic corpus
- **THEN** each required scenario family SHALL have a bound executor and at least one selected test that crosses its declared lowest stable production seam

#### Scenario: Insufficient evidence remains an acceptable bounded outcome
- **WHEN** scripted sources do not support the requested conclusion
- **THEN** the real validator, ledger, and artifact path SHALL record a typed limitation or gap without fabricating an accepted claim or citation

### Requirement: Quality metrics are pure functions

Quality metrics SHALL be pure Python functions with no model calls or I/O. They SHALL consume a validated evaluation outcome projected from accepted ledger records, canonical sources, findings, must-answer bindings, typed gaps, and citation maps. They SHALL compute citation precision from bindings to accepted records, citation completeness from cited major findings, must-answer coverage from explicit question-to-finding or honest-gap bindings, source diversity from canonical source identities and normalized hosts, contradiction recall from annotated replay expectations, and unsupported-major-claim counts from missing accepted support. Empty-input semantics SHALL be explicit. Metric evaluation SHALL distinguish hard correctness and security invariants from quality scores whose thresholds require an observed live baseline.

#### Scenario: Ref-shaped text is not a valid citation
- **WHEN** an emitted citation string has the expected prefix but does not bind to an accepted ledger record
- **THEN** citation precision SHALL treat it as unbound and the citation-binding hard invariant SHALL fail when the scenario requires valid citations

#### Scenario: Submission count does not imply question coverage
- **WHEN** accepted submissions exist but no supported finding or typed honest gap is bound to a must-answer question
- **THEN** that question SHALL remain uncovered

#### Scenario: Quality scores are reproducible for a replay outcome
- **WHEN** the same validated replay outcome is evaluated twice
- **THEN** all metric values SHALL be identical and no model, network, clock, or filesystem input SHALL be consulted

#### Scenario: Hard invariant failure is not averaged into quality
- **WHEN** a scenario has an unauthorized route, forged submission, invalid artifact binding, or incorrect terminal lifecycle outcome
- **THEN** evaluation SHALL fail independently of citation, coverage, diversity, cost, or latency scores

### Requirement: Release gate combines deterministic CI with optional LLM canary

The release system SHALL expose four mechanically distinct selections within three cadences: network-free deterministic correctness, network-free deterministic workflow conformance, credentialed short live behavioral evaluation, and manual full-real release acceptance. Real-model tests SHALL carry the `requires_llm` marker. Missing required credentials in an explicitly selected live or release lane SHALL fail preflight rather than silently skip. Live evaluation SHALL include the existing start-to-HITL1, HITL1-to-topic-planning, and one-topic Wave0 prefixes plus directly seeded Wave1, Wave2 synthesis, and targeted-evidence focused-node canaries. Full-real acceptance SHALL use unique thread, run, and research identities and report every retry.

#### Scenario: Deterministic workflow lane is explicit and non-empty
- **WHEN** PR selection collects the workflow-conformance command
- **THEN** it SHALL select at least one zero-API `workflow` test, exclude live/release/provider tests, and remain included in the complete deterministic union

#### Scenario: Late-node live canary does not rerun the full prefix
- **WHEN** Wave1, Wave2 synthesis, or targeted evidence is selected for live evaluation
- **THEN** the fixture SHALL seed the minimum validated predecessor ledger and sandbox authority, invoke the real focused node with bounded real dependencies, and report its focused authenticity without claiming public-entry or full-pipeline coverage

#### Scenario: Release acceptance remains singular
- **WHEN** the live suite expands to later provider-sensitive nodes
- **THEN** no additional routine full-real pipeline SHALL be introduced and the existing release lane SHALL remain the sole `FULL_REAL_PIPELINE` proof

### Requirement: Recorded incidents close at the lowest responsible seam

Every recorded real-mode or later live/release incident SHALL map to at least one current deterministic test selector at the lowest stable responsible seam when replayable. Incident inventory validation SHALL verify selector collection, deterministic selection, declared authenticity, stable seam, and execution-evidence registration rather than selector existence alone. Provider-dependent behavior that cannot be reproduced honestly SHALL retain a bounded live scenario and explicit rationale.

#### Scenario: Existing selector cannot overclaim its seam
- **WHEN** an incident selector still exists but its registered execution evidence does not reach the incident's declared stable seam or authenticity
- **THEN** asset governance SHALL fail with the incident id, selector, expected seam, and observed evidence class

#### Scenario: Replayable release discovery has fixture provenance
- **WHEN** a release discovery concerns a minimized provider payload shape that production parsing or normalization can replay
- **THEN** it SHALL link to a redacted provider-shape fixture and a collected deterministic selector before the discovery is considered closed

### Requirement: Scenarios declare stable test seams and authenticity

Each reusable scenario SHALL declare a stable id, risk family, owning requirement ids, optional regression ids, stable entrypoint kind, required authenticity level, required production seams, initial context/checkpoint/workspace conditions, executable typed scripted inputs where applicable, expected route and terminal outcome, artifact and citation expectations, hard invariants, metrics, and permitted degradation. Scenario execution SHALL return test-owned evidence derived from observable model/tool calls and checkpoint, ledger, and sandbox authorities. The runner SHALL reject unknown invariant names and SHALL evaluate every declared invariant, citation expectation, artifact expectation, and degradation rule.

#### Scenario: Successful execution evaluates every invariant
- **WHEN** an executor returns a nominal outcome
- **THEN** the runner SHALL calculate each declared hard invariant from execution evidence and SHALL NOT mark invariant flags true merely because the executor returned without error

#### Scenario: Lower authenticity cannot satisfy a higher claim
- **WHEN** a scenario executes with fake nodes, fake node capabilities, or without an applicable real bridge/authority seam
- **THEN** its evidence SHALL NOT satisfy `SCRIPTED_REAL_WORKFLOW`, live-model, or full-real coverage

#### Scenario: Scenario diagnostics carry stable identity
- **WHEN** a scenario fails in any execution lane
- **THEN** the failure output SHALL include scenario id, execution lane, authenticity level, failed invariant or metric, and only bounded redacted structural diagnostics

### Requirement: Deterministic tests conform real agent workflows

Every available real node SHALL retain at least one deterministic success and one highest-risk failure, repair, degradation, or exhausted scenario through its stable node interface. Every model/tool workflow claim SHALL additionally execute the applicable real runtime bridge, middleware, execution policy, budget, structured-output parser, validator, submission/gate, checkpoint, and filesystem paths while replacing only external model/tool adapters, deterministic time/randomness, and supported fault points. Such tests SHALL carry the `workflow` marker and assert observable execution evidence for their applicable seams. High-risk real prefixes SHALL run as mixed graphs with later unrelated nodes kept fake.

#### Scenario: Scripted worker traverses the complete policy path
- **WHEN** a scripted model issues an allowed web tool call and returns a valid worker result
- **THEN** observable evidence SHALL prove real resolver, bridge, middleware, policy, budget, validator, submit, gate, checkpoint, ledger, and attempt-artifact execution before the work is reported accepted or degraded

#### Scenario: Malformed output follows bounded repair policy
- **WHEN** scripted model responses remain malformed through configured repair attempts
- **THEN** the real node or worker path SHALL reach its specified typed fallback or exhausted outcome without accepted ledger publication or fabricated artifact success

#### Scenario: Directory placement does not establish workflow authenticity
- **WHEN** a test is placed under `integration`, `graph`, or `eval` without the required execution evidence
- **THEN** it SHALL remain code-correctness or real-node coverage and SHALL NOT satisfy the workflow-conformance inventory

### Requirement: Test selection and requirement traceability are mechanical

Stable commands and markers SHALL separately select fast deterministic correctness, deterministic workflow conformance, live, and release-acceptance tests. The default complete deterministic command SHALL include all project-owned zero-API tests while excluding credentialed and deferred-provider tests. Governance SHALL reject an empty workflow lane, lane overlap, scripted scenarios without collected workflow selectors, and authenticity-sensitive requirements whose only test references are below their required evidence class. Requirement references and collected selectors SHALL still reject unknown ids and uncovered alive requirements.

#### Scenario: Workflow requirement needs workflow evidence
- **WHEN** an alive requirement explicitly requires a scripted real workflow and has only module-level or real-node-fake-capability test references
- **THEN** requirement coverage SHALL fail and report the missing authenticity class

#### Scenario: Explicit lanes remain non-overlapping
- **WHEN** test collection is performed for deterministic correctness, deterministic workflow, live, and release selections
- **THEN** every test SHALL appear only in compatible selections, all zero-API tests SHALL remain in the deterministic union, and credentialed tests SHALL never enter PR selection

### Requirement: Higher-level failures descend into deterministic assets

Every defect discovered by live evaluation or full-real acceptance SHALL be classified by risk and stable seam. Replayable provider payload shapes SHALL be minimized into redacted structured fixtures linked to their discovery ids and exercised through the production parser, materializer, validator, or node seam. Behavior that depends on nondeterministic provider decisions and cannot be faithfully replayed SHALL remain a bounded live scenario with captured redacted diagnostics. Neither form SHALL be represented solely by an E2E log.

#### Scenario: Provider-shape fixture is safe and attributable
- **WHEN** a provider response variation is added to the deterministic corpus
- **THEN** it SHALL contain only the minimal synthetic keys, types, aliases, and ordering needed to reproduce the behavior, name its discovery provenance and expected normalized or fail-closed result, and pass credential, host-path, and raw-content scans

#### Scenario: E2E integration defect gains a deterministic regression
- **WHEN** full-real acceptance exposes a replayable context, policy, parser, store, graph, or artifact-contract defect
- **THEN** the fixing change SHALL add the smallest deterministic regression at the lowest responsible seam before the defect is considered closed

#### Scenario: Provider-only behavior remains live
- **WHEN** a failure depends on model/tool selection or output distribution that cannot be faithfully represented by a deterministic payload
- **THEN** it SHALL remain a labeled bounded live scenario with attempts and redacted evidence rather than a tautological scripted test
