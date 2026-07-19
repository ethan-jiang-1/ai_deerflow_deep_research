# evaluation-hardening Specification

> req: EVH-001, EVH-002, EVH-003, EVH-004, EVH-005, EVH-006, EVH-007, EVH-008, EVH-009, EVH-010

## Purpose

Provide deterministic workflow conformance, live behavioral evaluation, full-real release acceptance, and mechanical regression traceability for Deep Research.

## Requirements

### Requirement: Eval corpus framework supports replay-based testing

The eval framework SHALL represent each required research risk as a lane-neutral typed scenario family plus one or more lane-specific cases. The corpus SHALL cover quick factual, claim verification, insufficient evidence, prompt injection, malformed structured output, unavailable tools, budget exhaustion, partial worker success, checkpoint control, and sandbox/filesystem failure. Every family SHALL bind to at least one collected deterministic case that invokes its declared lowest stable production interface and asserts observations projected from checkpoint, validated-ledger, or contained-sandbox authority. Cases that exercise model/tool behavior SHALL use executable typed scripted inputs; lifecycle/store cases SHALL use typed action or fault inputs instead of pretending to be agent loops. A descriptive-only family, string-labeled pseudo-script, synthetic outcome dictionary, or uncollected case SHALL fail asset governance. Deterministic corpus execution SHALL require no model API, external network, or operator credentials.

#### Scenario: One family is reusable across deterministic and live cases
- **WHEN** one risk family has both deterministic and live cases
- **THEN** the cases SHALL share the same risk intent and permitted degradation while each declaring the entrypoint, inputs, bounds, expected outcomes, hard invariants, applicable metrics, seam, and authenticity it can actually prove

#### Scenario: Every first-wave family executes at its responsible seam
- **WHEN** asset governance collects the deterministic corpus
- **THEN** each required family SHALL reference at least one collected case whose evidence claim names the production seam responsible for that case without requiring unrelated graph phases

#### Scenario: Insufficient evidence remains an acceptable bounded outcome
- **WHEN** scripted sources do not support the requested conclusion
- **THEN** the real validator, ledger, and artifact path SHALL record a typed limitation or gap without fabricating an accepted claim or citation

### Requirement: Quality metrics are pure functions

Quality metrics SHALL be pure Python functions with no model calls or I/O. They SHALL consume a validated evaluation outcome projected before metric computation from available accepted ledger records, canonical sources, topic/question coverage, synthesis findings and gaps, final citation maps, and optional labeled replay expectations. The metric set SHALL distinguish structural citation-binding rate, labeled semantic citation precision, final claim-map citation completeness, synthesis finding-support coverage, must-answer coverage, distinct canonical-URL count, distinct normalized-host count, labeled contradiction recall, labeled semantic unsupported-major-claim count, and the separate structural missing-backing-ref count. Canonical-URL and host counts SHALL derive only from validated accepted `SourceRef` values; provider-local `source_id` values SHALL NOT count as cross-record source identity. A metric not selected by the scenario case SHALL return `not_applicable`; a selected metric whose required authoritative input is missing or semantically unlabeled SHALL return `insufficient_authority`. A selected ratio with no authoritative denominator population SHALL also return `insufficient_authority`; an authoritative count metric MAY return measured zero when its required source collection is present, validated, and empty. Otherwise the metric SHALL return `measured`. `not_applicable` and `insufficient_authority` SHALL carry a null value; `measured` SHALL carry a typed numeric value. Every result SHALL include its evidence basis, so an unavailable ratio cannot become a vacuous zero or one and a measured zero count cannot be confused with missing authority. Metric evaluation SHALL remain separate from hard correctness and security invariants, and quality thresholds SHALL require an observed live baseline and separate review.

#### Scenario: Ref-shaped text is not a bound citation
- **WHEN** a final citation string has the expected syntax but does not bind to an accepted ledger record
- **THEN** citation binding rate SHALL treat it as unbound and a required citation-binding hard invariant SHALL fail independently of semantic precision

#### Scenario: Semantic precision requires labels
- **WHEN** cited claim/ref pairs have accepted structural bindings but no labeled support judgment
- **THEN** citation precision and semantic unsupported-claim count SHALL report `insufficient_authority` rather than infer support from ref syntax or existence

#### Scenario: Must-answer coverage uses existing topic authority honestly
- **WHEN** questions bind to planned topics and synthesis findings or typed honest gaps name affected topics
- **THEN** a question SHALL count as covered only when every known topic in its planner-owned binding set is represented by at least one finding or typed honest gap; partially represented questions plus missing or unknown topic ids SHALL be reported separately and SHALL NOT be represented as direct question-to-finding authority

#### Scenario: Empty denominator is not perfect quality
- **WHEN** a selected ratio metric has no authoritative claims, questions, citations, findings, or labeled expectations in its required denominator
- **THEN** it SHALL return `insufficient_authority` with a null value and an evidence-basis reason rather than a vacuous zero or one

#### Scenario: Valid empty collection can measure a zero count
- **WHEN** a selected structural count metric receives its required validated authority collection and that collection is empty
- **THEN** it MAY return `measured` with numeric zero and evidence basis identifying the authoritative empty collection rather than reporting missing authority

#### Scenario: Quality scores are reproducible for a validated outcome
- **WHEN** the same validated evaluation outcome is evaluated twice
- **THEN** all metric statuses, values, and evidence bases SHALL be identical and no model, network, clock, or filesystem input SHALL be consulted

#### Scenario: Hard invariant failure is not averaged into quality
- **WHEN** a scenario has an unauthorized route, forged submission, invalid artifact binding, or incorrect terminal lifecycle outcome
- **THEN** evaluation SHALL fail independently of citation, coverage, diversity, cost, or latency scores

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

The release system SHALL expose five focused, pairwise-disjoint selections: network-free fast correctness, network-free integration correctness, network-free deterministic workflow conformance, credentialed short live behavioral evaluation, and manual full-real release acceptance. In this stable requirement title, `optional` means that credentialed LLM execution is outside the default deterministic PR path; an explicitly scheduled or manually selected live/release run remains strict and cannot skip. The complete deterministic command SHALL be an explicit aggregate of the first three and is not itself a disjoint lane. Real-model tests SHALL carry the `requires_llm` marker, the live selector SHALL be `requires_llm and not release_e2e`, and the release selector SHALL be `requires_llm and release_e2e`; governance SHALL reject a `release_e2e` test missing `requires_llm`. Missing credentials in an explicitly selected live or release lane SHALL fail preflight rather than silently skip. Live evaluation SHALL include the existing start-to-HITL1, HITL1-to-topic-planning, and one-topic Wave0 prefixes plus directly seeded Wave1, Wave2 synthesis, and targeted-evidence focused-node canaries. Every selected live case SHALL report stable case identity, hard-invariant outcomes, typed metric statuses and evidence bases, attempts/retries, tokens, tool calls, cost when available, wall time, and bounded redacted diagnostics. Full-real acceptance SHALL use unique thread, run, and research identities and report every retry.

#### Scenario: Deterministic workflow selection is explicit and non-empty
- **WHEN** PR CI collects fast correctness, integration correctness, and workflow conformance
- **THEN** the focused selections SHALL be pairwise disjoint, workflow SHALL select at least one zero-API `workflow` test, all three SHALL exclude live/release/Postgres tests, and their union SHALL equal the complete deterministic collection

#### Scenario: Late-node live canary uses production dependencies honestly
- **WHEN** Wave1, Wave2 synthesis, or targeted evidence is selected for focused live evaluation
- **THEN** its seed SHALL publish minimum valid predecessor authority through existing checkpoint/store interfaces, the case SHALL invoke the real focused node with a bounded derivative of its production policy and real external dependencies, apply reducer preview before gate evaluation where the production wrapper requires it, apply only the production gate/submit semantics that actually belong to that node, and disclaim public-entry, predecessor-lifecycle, production-recipe, and full-pipeline coverage

#### Scenario: Scheduled live budget is bounded as a whole
- **WHEN** all six focused live cases are enabled in the nightly job
- **THEN** each case SHALL have one outer attempt and explicit model/tool/token/time bounds, declared scenario deadlines SHALL sum to at most 900 seconds, each web case SHALL be at most 240 seconds, each zero-tool case SHALL be at most 120 seconds, and the existing 20-minute job SHALL retain at least five minutes for setup and cleanup

#### Scenario: Explicit live selection keeps strict preflight
- **WHEN** an operator or schedule explicitly selects live or release tests without every credential required by the selected cases
- **THEN** preflight SHALL fail with a typed readiness error rather than skip cases or silently reduce the selected set

#### Scenario: Focused live report is auditable without raw output
- **WHEN** a selected live case completes, degrades, or fails
- **THEN** its versioned report SHALL preserve the case identity, invariant results, metric applicability/authority, attempts, resource use, duration, and redacted typed diagnostics without model text, credentials, source URLs, or host paths

#### Scenario: Release acceptance uses isolated identity
- **WHEN** full-real acceptance is invoked more than once
- **THEN** every invocation SHALL use new thread, run, and research identities and SHALL NOT inherit a prior blocked or completed checkpoint

#### Scenario: Release acceptance remains singular
- **WHEN** the live suite expands to later provider-sensitive nodes
- **THEN** no additional routine full-real pipeline SHALL be introduced and the existing release lane SHALL remain the sole `FULL_REAL_PIPELINE` proof

#### Scenario: Test-only rebalancing does not spend release E2E by default
- **WHEN** implementation leaves the release runner and public entry unchanged and focused live cases expose no full-pipeline-only uncertainty
- **THEN** final validation SHALL collect the release selector and validate a committed minimal redacted attestation of the existing accepted run without requiring a fresh full-real execution

#### Scenario: Successful release proof survives local report cleanup
- **WHEN** raw `.reports/release` artifacts are absent from a clean checkout
- **THEN** a committed attestation SHALL still record schema version, scenario, source observation date, `source_report_sha256`, attestation base revision explicitly distinct from run revision, explicit unknown run revision, attempt/retry counts, all eight hard invariant results, accepted/citation counts, aggregate token/tool/time values, scoped source-archive scan verdicts, and scoped attestation scan verdicts without invocation ids, provider response shapes, model text, source URLs, credentials, or host paths

#### Scenario: Attestation provenance does not merge authorities
- **WHEN** an attestation contains release-run facts and redaction scan verdicts
- **THEN** it SHALL distinguish facts derived from the hashed source JSON, scan results recorded by the archived release gate with its committed source locator and original live/release target scope, and scans of the generated attestation itself rather than claiming every fact came from one source

#### Scenario: Attestation does not invent missing run metadata
- **WHEN** the source report has no embedded execution timestamp or code revision
- **THEN** the attestation SHALL preserve only the supported observation date, SHALL mark run revision unknown, and SHALL NOT substitute file modification time or a later repository revision as execution metadata

#### Scenario: Committed release documents cannot contradict the attestation
- **WHEN** a committed parity or release-status document describes the same evidence epoch
- **THEN** it SHALL agree with the attestation's achieved/not-achieved state or explicitly declare itself superseded

#### Scenario: Material release impact triggers scope review
- **WHEN** implementation must change production behavior or interfaces, including the release runner/public entry, or a focused live discovery cannot be validated below the full pipeline
- **THEN** the change SHALL return to proposal/design review before authorizing and recording a fresh isolated release run

### Requirement: Recorded incidents close at the lowest responsible seam

Every recorded real-mode or later live/release incident SHALL reference at least one central test-evidence claim for a collected deterministic selector at the lowest responsible stable seam when replayable. The incident inventory SHALL retain explicit replaced/duplicate recommendation status and coverage of all-real compilation, context forwarding, model/tool/sandbox readiness, mounted filesystem stores, capability/policy routing, budgets, structured output, gate fatigue, and checkpoint identity. Each claim SHALL declare a stable claim id, exact collected selector, expected focused selection, requirement ids, asset class, one canonical stable seam, optional authenticity, at most one scenario-case id, and any discovery ids; selector globs and prefixes SHALL be rejected. Every registered scenario case SHALL resolve to exactly one claim whose exact collected pytest node id contains the stable case id. Parameterized evidence cases SHALL use stable case ids as pytest ids, and uniform provider-shape selectors SHALL be derived from registered shape case ids. Only selectors referenced by the requirement-evidence policy or a scenario, incident, node, fault, or discovery inventory SHALL require central claims; ordinary collected tests SHALL NOT be duplicated into a second exhaustive catalog. Inventories SHALL reference claim ids instead of independently repeating selector/seam/authenticity declarations. Existing `@impl` annotations SHALL continue to identify owning implementation surfaces; evidence claims SHALL own test-selector proof. Governance SHALL collect and validate deterministic, workflow, live, and release claims in their expected selections, verify referential consistency and evidence policy, and SHALL NOT present static metadata as proof of unobservable internal calls. Provider-dependent behavior that cannot be reproduced honestly SHALL retain a bounded live case and explicit rationale.

#### Scenario: Existing selector cannot overclaim its evidence class
- **WHEN** a selector still exists but its central claim is below an inventory entry's required asset class, seam, or authenticity
- **THEN** asset governance SHALL fail with the inventory id, selector, required evidence, and registered claim

#### Scenario: Incident inventory cannot retain a stale selector
- **WHEN** an incident claim references a selector that is renamed, removed, skipped by its required lane, or no longer collected
- **THEN** asset governance SHALL fail with the incident id, claim id, and stale selector

#### Scenario: Integration failure is diagnosable below E2E
- **WHEN** a recorded replayable interface mismatch is reintroduced
- **THEN** its focused deterministic case SHALL fail before live or release execution and identify the family/case, seam, and typed invariant or error code

#### Scenario: Duplicate mappings cannot disagree silently
- **WHEN** incident, node, fault, or scenario inventories reference one collected selector
- **THEN** they SHALL resolve through the same central claim and governance SHALL reject contradictory local seam or authenticity metadata

#### Scenario: Replayable release discovery has deterministic provenance
- **WHEN** a release discovery concerns a provider payload shape that production parsing or normalization can replay
- **THEN** it SHALL link to either a minimized redacted shape case or an existing focused deterministic regression plus a collected evidence claim before the discovery is considered closed

### Requirement: Scenarios declare stable test seams and authenticity

Each reusable scenario family SHALL declare a stable family id, risk intent, owning requirement ids, optional regression ids, and permitted degradation. Each scenario case SHALL declare a stable case id and family id, execution lane, entrypoint, required asset class, canonical stable seam, optional authenticity, bounded preconditions, executable typed inputs or live requirements, expected route/terminal/artifact/support/citation/degradation outcomes, hard invariants, and applicable metrics. The closed asset classes SHALL be code correctness, deterministic workflow conformance, live behavioral evaluation, and release acceptance. The closed canonical stable seams SHALL be domain/engine, node interface, runtime integration, lifecycle/mixed graph, and public entry. When authenticity applies, the closed levels SHALL be `FAKE_GRAPH`, `REAL_NODE_FAKE_CAPABILITIES`, `SCRIPTED_REAL_WORKFLOW`, `LIVE_REAL_DEPENDENCIES`, and `FULL_REAL_PIPELINE`; code-correctness cases MAY omit authenticity. Authenticity SHALL qualify only the claim's already compatible asset class, seam, and scope; it SHALL NOT widen a focused claim or substitute for another asset class or seam. Focused tests SHALL invoke the existing production interface explicitly and project a test-owned observation from observable calls and checkpoint, ledger, and sandbox authorities. A shared assertion interface SHALL reject unknown invariant names and evaluate every expectation applicable to the case.

#### Scenario: Successful execution evaluates every applicable invariant
- **WHEN** a focused case returns a nominal observation
- **THEN** shared assertions SHALL calculate every case hard invariant, validate expected outcomes against the family's permitted-degradation policy, and SHALL NOT mark either successful merely because execution returned without error

#### Scenario: Code correctness is not forced onto the agent authenticity ladder
- **WHEN** a deterministic store, parser, reducer, or real-node-fake-capability case proves its declared risk without an agent loop
- **THEN** its claim SHALL retain the appropriate code-correctness asset class and seam, with no fabricated `SCRIPTED_REAL_WORKFLOW` authenticity

#### Scenario: Unknown evidence vocabulary fails closed
- **WHEN** a family, case, claim, or inventory uses an asset class, stable seam, or authenticity outside the closed canonical vocabulary
- **THEN** governance SHALL reject the value rather than preserve an ad hoc alias or infer a nearby category

#### Scenario: Lower authenticity cannot satisfy a higher claim
- **WHEN** a case claims workflow, live, or full-real evidence without the applicable real lifecycle/graph or agent-loop seams
- **THEN** governance and shared assertions SHALL reject that evidence claim

#### Scenario: Focused real dependencies do not widen coverage
- **WHEN** a live case uses real model or tool dependencies only at a directly seeded focused node
- **THEN** its `LIVE_REAL_DEPENDENCIES` authenticity SHALL NOT satisfy workflow-prefix, predecessor-lifecycle, public-entry, release-acceptance, or `FULL_REAL_PIPELINE` evidence

#### Scenario: Scenario diagnostics carry stable identity
- **WHEN** a case fails in any execution lane
- **THEN** failure output SHALL include family id, case id, lane, applicable authenticity, failed invariant or metric, and only bounded redacted structural diagnostics

### Requirement: Deterministic tests conform real agent workflows

Every available real node SHALL retain at least one deterministic success and one highest-risk failure, repair, degradation, or exhausted case through its stable node interface. Every available real node that uses a model or tool SHALL additionally retain at least one collected deterministic workflow claim through its applicable real runtime bridge-driven agent loop. Governance SHALL discover model/tool-node ownership from loaded `run_agent` attribute calls or method references across production node packages using syntax-aware inspection and compare it with the explicit audited inventory; it SHALL NOT infer ownership from declared node capabilities or present source discovery as execution proof. A deterministic test SHALL carry the `workflow` marker only when it executes at least one temporally ordered production workflow: a real lifecycle/mixed-graph transition sequence, a real runtime-bridge agent loop, or a real worker submit/gate sequence. The marker SHALL identify the workflow-conformance asset class, not automatically grant `SCRIPTED_REAL_WORKFLOW` authenticity. Model/tool workflow claims SHALL construct the applicable real agent or runtime bridge and execute its middleware, execution policy, budget, structured-output parser, validator, submission/gate, checkpoint, and filesystem paths while replacing only external model/tool adapters, deterministic time/randomness, and supported fault points. Scripted adapters SHALL fail when a requested response is exhausted; each evidence-bearing workflow case SHALL assert its declared model/tool call bounds, order, and relevant bound-tool observations without imposing complete-trace semantics on unrelated fixture users. A test that patches the agent, bridge, or assembly factory MAY prove wiring but SHALL NOT claim agent-loop behavior or `SCRIPTED_REAL_WORKFLOW` authenticity. High-risk real prefixes SHALL run as mixed graphs with later unrelated nodes kept fake.

#### Scenario: Scripted worker traverses the complete policy path
- **WHEN** a scripted model issues an allowed web tool call and returns a valid worker result
- **THEN** observable model/tool calls plus checkpoint, ledger, gate, and attempt-artifact outcomes SHALL demonstrate the real resolver, bridge, middleware, policy, budget, validator, and submit path before work is reported accepted or degraded

#### Scenario: Scripted external adapters retain the real loop
- **WHEN** deterministic model turns and tool results drive a model/tool behavior case
- **THEN** the real agent or runtime bridge SHALL consume them, premature exhaustion, unexpected calls, or call order/bounds inconsistent with the case SHALL fail, and the observation SHALL record the relevant tool bindings and calls

#### Scenario: Patched assembly proves wiring only
- **WHEN** `create_agent`, a bridge builder, or another assembly factory is patched to inspect constructor arguments, middleware order, or tool registration
- **THEN** the test MAY claim wiring correctness but SHALL NOT satisfy workflow-conformance, agent-loop, policy-path, or `SCRIPTED_REAL_WORKFLOW` evidence

#### Scenario: Lifecycle sequence can be workflow conformance without a model
- **WHEN** a deterministic case executes ordered real start/resume/cancel or mixed-graph transitions with real checkpoint authority
- **THEN** it MAY enter the workflow selection for the lifecycle/graph seam but SHALL NOT claim `SCRIPTED_REAL_WORKFLOW`, agent-loop, or live-provider authenticity without a real bridge-driven loop

#### Scenario: Malformed output follows bounded repair policy
- **WHEN** scripted model responses remain malformed through configured repair attempts
- **THEN** the real node or worker path SHALL reach its specified typed fallback or exhausted outcome without accepted ledger publication or fabricated artifact success

#### Scenario: Directory placement does not establish workflow authenticity
- **WHEN** a test is placed under `integration`, `graph`, or `eval` without a qualifying ordered production workflow
- **THEN** it SHALL remain code-correctness or real-node coverage and SHALL NOT enter the workflow-conformance selection

#### Scenario: Capability declaration does not discover model use
- **WHEN** a real node calls the shared agent bridge but declares no agent capability or declares a store/controller capability
- **THEN** syntax-aware node ownership discovery SHALL still require its workflow claim, while the collected focused test supplies the behavioral evidence

#### Scenario: Mutable fixture state is isolated and restored
- **WHEN** a deterministic, live, or release fixture changes effective config/home paths, installs a sandbox provider, mutates a cached AppConfig or GraphHost, or creates contained filesystem data and then succeeds or raises
- **THEN** the fixture owner SHALL restore each process-global state it actually changed through its public reset/restore API, and the next case SHALL observe its own explicit configuration and contained filesystem without prior checkpoint, ledger, or artifact state

#### Scenario: Persisted replay requires a concrete escalation
- **WHEN** a case proposes persisted record/replay instead of bounded scripted turns
- **THEN** it SHALL record the caller-sensitive interleaving or stable trace-shape behavior that scripts cannot faithfully represent, include caller identity in matching, normalize only declared volatile fields, fail loudly on a replay miss even when outer middleware handles the model error, and assert stable shape/order without raw provider prose or volatile-value goldens

### Requirement: Test selection and requirement traceability are mechanical

Stable commands and markers SHALL separately select fast correctness, integration correctness, deterministic workflow conformance, live evaluation, and release acceptance. The default complete deterministic command SHALL include the exact union of the three zero-API focused selections while excluding credentialed and deferred-provider tests. Every alive requirement SHALL retain at least one collected deterministic test-side `@impl` reference. Governance SHALL reject focused-selection overlap, an empty workflow selection, scenario families without deterministic cases, cases without collected claims, contradictory inventory mappings, unknown requirement ids, uncovered alive requirements, and cross-lane requirements missing any asset class or authenticity declared by their evidence policy. Asset classes SHALL be treated as independent required evidence, not a single ordered minimum; a test-side `@impl` reference records implementation ownership but does not replace a required cross-lane evidence claim. Each validator SHALL have direct invalid-fixture coverage for every rule it owns; a collector, syntax-aware discovery scan, archive scan, or runtime detector that could succeed on an empty or mis-scoped input SHALL additionally retain a focused detector smoke case.

#### Scenario: Cross-lane requirement needs every declared evidence class
- **WHEN** an alive requirement is listed in the requirement-evidence policy with required deterministic, workflow, live, or release asset classes and one class is absent
- **THEN** requirement coverage SHALL fail with the requirement id, missing class or authenticity, and observed claims

#### Scenario: Ordinary requirement does not inherit a blanket workflow mandate
- **WHEN** a requirement is not authenticity-sensitive
- **THEN** an appropriate collected deterministic claim at its responsible seam SHALL satisfy coverage without an artificial workflow case

#### Scenario: Focused selections partition deterministic collection
- **WHEN** collection is performed for fast correctness, integration correctness, workflow conformance, and the complete deterministic aggregate
- **THEN** the three focused selector sets SHALL be pairwise disjoint and their union SHALL equal the aggregate, while live, release, and Postgres selectors remain excluded

#### Scenario: Empty scan cannot masquerade as enforcement
- **WHEN** collection, syntax discovery, archive scanning, or runtime detection is added or materially changed and its input is empty, relocated, or mis-scoped
- **THEN** a focused smoke case SHALL prove that a known target violation is detected, while pure validation rules SHALL retain direct minimal invalid-fixture tests

#### Scenario: Test-evidence authority survives change archival
- **WHEN** this delta is active, synchronized, or archived and a later change needs the current test-evidence contract
- **THEN** pending modifications SHALL be discoverable from the one active owning delta, approved semantics SHALL be discoverable from the `evaluation-hardening` main spec, exact evidence metadata SHALL remain in test-owned registries, executable collection SHALL remain agent-owned, and the governance authority/lifecycle policy plus concise OpenSpec/agent pointers SHALL route contributors without treating archived proposal, design, or tasks as current authority

### Requirement: Higher-level failures descend into deterministic assets

Every defect discovered by live evaluation or full-real acceptance SHALL be classified by risk and stable seam. A machine-readable discovery disposition SHALL select exactly one of `uniform_shape`, `existing_regression`, or `provider_only`: uniform shape SHALL name an intended shape-case id that resolves to a collected claim before closure, existing regression SHALL name a collected claim id, and provider-only SHALL name a bounded live case plus non-empty replay-unsuitability rationale; fields belonging to other dispositions SHALL be rejected. Uniform replayable provider payload variations SHOULD be minimized into typed redacted shape cases linked to discovery ids; an existing focused regression MAY remain individual when its setup or responsible seam is not uniform, provided it has the same discovery provenance and central evidence claim. Behavior that depends on nondeterministic provider decisions and cannot be faithfully replayed SHALL remain a bounded live case with captured redacted diagnostics. Neither form SHALL be represented solely by an E2E log.

#### Scenario: Provider-shape case is bounded and attributable
- **WHEN** a provider response variation is added to the shared shape corpus
- **THEN** it SHALL contain only bounded keys, types, aliases, ordering, and synthetic-domain values needed to reproduce the behavior, name its discovery provenance and expected normalized or fail-closed result, pass credential, raw-host-path, external-URL, and size scans, and record human provenance review that free text was minimized rather than copied raw

#### Scenario: Existing focused regression remains valid provenance
- **WHEN** a replayable discovery already has a focused deterministic regression whose setup is not suitable for a uniform shape case
- **THEN** the discovery MAY link directly to that selector's evidence claim without duplicating the test solely to populate the corpus

#### Scenario: Discovery has one governable disposition
- **WHEN** a discovery classification is loaded
- **THEN** exactly one disposition-specific reference set SHALL be present, unknown or mixed dispositions SHALL fail, and corpus closure SHALL reject an unresolved intended shape-case id

#### Scenario: E2E integration defect gains a deterministic regression
- **WHEN** full-real acceptance exposes a replayable context, policy, parser, store, graph, or artifact-contract defect
- **THEN** the fixing change SHALL add the smallest deterministic regression at the lowest responsible seam before the defect is considered closed

#### Scenario: Provider-only behavior remains live
- **WHEN** a failure depends on model/tool selection or output distribution that cannot be faithfully represented by a deterministic payload
- **THEN** it SHALL remain a labeled bounded live case with attempts and redacted evidence rather than a tautological scripted test
