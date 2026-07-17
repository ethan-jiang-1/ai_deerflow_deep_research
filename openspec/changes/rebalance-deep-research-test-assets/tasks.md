# Test Asset Rebalancing Tasks

> Current progress: **0/38 complete**. Proposal artifacts are ready for review; implementation has not started.
>
> Progress rule: update this summary and the active task after every focused red/green slice. A task is checked only after its named selector passes. Record the selector, observed result, and any honest scope reduction directly below that task while applying the change.
>
> Hard boundary: this change modifies project-owned `agent/`, OpenSpec, documentation, and agent workflows only. `backend/` and `frontend/` remain unchanged.

## 1. Baseline And Authenticity Contract

- [ ] 1.1 Capture the current deterministic selector distribution, empty `workflow` collection, scenario-to-executor gaps, late-node live coverage, and metric proxy behavior in a generated test-owned baseline fixture with a red governance test that detects each known gap. @impl EVH-006, EVH-008, EVH-009
- [ ] 1.2 Define the closed test-owned stable-seam and execution-evidence contracts for route/terminal results, exercised real seams, model/tool calls, accepted ledger refs, artifact/citation refs, degradation and typed failure codes; add validation and redaction tests. @impl EVH-007, EVH-008
- [ ] 1.3 Add invariant evaluators over checkpoint, validated ledger, and contained sandbox projections; prove unknown invariants fail and nominal executor completion cannot auto-pass declared hard invariants. @impl EVH-007
- [ ] 1.4 Mark current tests that genuinely cross applicable real bridge/policy/authority paths with `workflow`, explicitly leave lower-authenticity tests unmarked, and add contract tests for both classifications. @impl EVH-008, EVH-009
- [ ] 1.5 Add non-empty `make test-workflow` selection, keep it inside the complete deterministic union, and update PR CI plus lane-selection tests to prove it excludes `requires_llm`, `release_e2e`, and `postgres`. @impl EVH-008, EVH-009

## 2. Executable Scenario Interface

- [ ] 2.1 Replace string-labeled scripted inputs with frozen typed model-turn, tool-result/tool-failure, and supported fault-point contracts; add bounds, schema, and secret/path rejection tests. @impl EVH-001, EVH-007
- [ ] 2.2 Add a closed stable-entrypoint registry for node/capability, worker-subgraph, lifecycle/mixed-graph, and authority-store adapters; reject arbitrary callables, duplicate entrypoints, and scenarios without a compatible adapter. @impl EVH-001, EVH-007
- [ ] 2.3 Implement the deterministic scenario runner so it executes the selected real seam adapter and returns execution evidence, then evaluates route, terminal, artifacts, citations, every hard invariant, metrics, and permitted degradation with scenario/lane/authenticity diagnostics. @impl EVH-001, EVH-007
- [ ] 2.4 Build reusable local runtime, scripted model/tool, checkpoint, ledger, and contained-artifact adapters behind the entrypoint interface without duplicating production routing, validation, or authority rules. @impl EVH-001, EVH-008
- [ ] 2.5 Add governance tests that fail for descriptive-only scenarios, unbound executors, unknown invariants, insufficient authenticity, missing authority evidence, and credentials or public network access in deterministic execution. @impl EVH-001, EVH-007, EVH-009

## 3. First-Wave Replay Corpus

- [ ] 3.1 Convert `quick-factual` into an executable real worker/ledger replay that proves accepted evidence and valid citation binding at the lowest applicable workflow seam. @impl EVH-001, EVH-008
- [ ] 3.2 Convert `claim-verification` into an executable replay with supported, contradicted, and uncertain evidence states and authoritative finding/ref assertions. @impl EVH-001, EVH-002
- [ ] 3.3 Convert `insufficient-evidence` into an executable replay that reaches typed honest degradation without accepted unsupported claims or fabricated citations. @impl EVH-001, EVH-002, EVH-008
- [ ] 3.4 Convert `prompt-injection` into an executable real tool/worker/validator/ledger/gate replay that proves route, gate, ledger, checkpoint, and path authority cannot be forged. @impl EVH-001, EVH-004, EVH-008
- [ ] 3.5 Convert `malformed-output` into an executable real node/worker replay that consumes all bounded repair responses and fails closed without partial ledger or artifact authority. @impl EVH-001, EVH-008
- [ ] 3.6 Convert `tool-unavailable-timeout` and `budget-exhaustion` into executable real bridge/policy replays with typed failure codes, cancellation semantics, call bounds, and no partial publication. @impl EVH-001, EVH-003, EVH-008
- [ ] 3.7 Convert `partial-worker-success` into an executable fan-out/submit/gate replay that distinguishes accepted, failed, repair, fatigue, and exhausted outcomes from authoritative work-unit state. @impl EVH-001, EVH-003, EVH-008
- [ ] 3.8 Convert `checkpoint-control` into an executable lifecycle replay covering duplicate resume, cancel idempotency, terminal monotonicity, and restart-safe checkpoint identity. @impl EVH-001, EVH-003
- [ ] 3.9 Convert `sandbox-filesystem-failure` into executable atomic-publication and replay cases at supported fault points with containment and prior-or-single-new authority guarantees. @impl EVH-001, EVH-003
- [ ] 3.10 Parameterize the corpus runner over all ten required scenario ids and prove each produces collected `workflow` evidence at its declared lowest seam with no credentials or public network. @impl EVH-001, EVH-007, EVH-008, EVH-009

## 4. Provider-Shape Regression Corpus

- [ ] 4.1 Define the minimized provider-shape fixture schema and loader with discovery id, focused node, input schema version, synthetic payload, expected normalized/fail-closed result, and sensitivity metadata. @impl EVH-010
- [ ] 4.2 Migrate the historical Wave0 URL, fetch-status, limitations, partial-source, duplicate-source, and direct-answer variations into redacted parameterized fixtures through production normalization and validation seams. @impl EVH-006, EVH-010
- [ ] 4.3 Migrate the historical Wave1 provider ids, source ids/ref rewrites, open-question states, source ordering, and malformed submit variations into redacted parameterized fixtures through production contract/materializer/submit seams. @impl EVH-006, EVH-010
- [ ] 4.4 Migrate the historical Wave2 finding, gap, relation, endpoint, priority, affected-topic, evidence-alias, sparse-output, and semantic-floor variations into redacted parameterized fixtures through production parser/node/validator seams. @impl EVH-006, EVH-010
- [ ] 4.5 Add corpus governance that joins fixtures to `LIVE-*`/`RELEASE-*` discoveries and deterministic selectors, rejects duplicate/unowned fixtures, and scans for credentials, raw host paths, and non-minimized research content. @impl EVH-006, EVH-010

## 5. Late-Node Live Canaries

- [ ] 5.1 Add test-owned authority seed builders that publish minimum valid Wave0/Wave1 ledger records, synthesis inputs, and typed gaps through existing store interfaces, with hash/schema/containment tests and no production bypass. @impl EVH-005, EVH-007
- [ ] 5.2 Add a one-topic Wave1 live canary using a real model and web tool with seeded Wave0 authority, one outer attempt, explicit token/tool/time bounds, and authoritative submit/gate assertions. @impl EVH-005, EVH-009
- [ ] 5.3 Add a Wave2 synthesis live canary using a real model with seeded accepted evidence, zero tools, citation/evidence binding assertions, and redacted response-shape diagnostics. @impl EVH-005, EVH-009
- [ ] 5.4 Add a one-gap targeted-evidence live canary using a real model and bounded web tool with seeded synthesis authority, validated publication, and no full-prefix claim. @impl EVH-005, EVH-009
- [ ] 5.5 Update live selection, preflight, reports, archive scans, and scheduled workflow so all six focused canaries are explicit, isolated, bounded, non-retrying at the outer layer, and labeled `LIVE_REAL_DEPENDENCIES` rather than public-entry/full-pipeline evidence. @impl EVH-005, EVH-009, EVH-010

## 6. Validated Quality Metrics

- [ ] 6.1 Define and test the pure validated-evaluation-outcome projection from accepted records, canonical sources, findings, must-answer bindings, typed gaps, and citation maps. @impl EVH-002
- [ ] 6.2 Replace ref-prefix citation precision and submission-count coverage with accepted-record citation precision, major-finding citation completeness, and explicit question-to-supported-finding or honest-gap coverage, including empty and forged-binding cases. @impl EVH-002
- [ ] 6.3 Replace submission-ref diversity with canonical source identity and normalized-host diversity, and validate unsupported-major-claim and annotated contradiction-recall semantics. @impl EVH-002
- [ ] 6.4 Version or compatibly extend serialized live reports as required, preserve historical report readability, and record a new observational baseline without adding blocking quality thresholds. @impl EVH-002, EVH-005

## 7. Mechanical Governance And Documentation

- [ ] 7.1 Strengthen incident, real-node, fault, and scenario inventories so each mapping declares required seam/authenticity and is checked against collected marker plus execution-evidence registrations rather than selector existence alone. @impl EVH-006, EVH-007, EVH-008
- [ ] 7.2 Extend requirement coverage with required-authenticity metadata so workflow requirements cannot be satisfied solely by module or real-node-fake-capability `@impl` references; add checker failure-behavior tests. @impl EVH-008, EVH-009, EVH-010
- [ ] 7.3 Update `agent/README.md`, `agent/AGENTS.md`, and `agent/docs/regression-descent.md` with the four selections, executable scenario contract, provider-shape provenance, seeded live semantics, validated metrics, and the continued single-E2E policy. @impl EVH-001, EVH-002, EVH-005, EVH-010
- [ ] 7.4 Run strict OpenSpec, requirement/spec/architecture governance, asset and requirement coverage, lock, Ruff, deterministic fast/workflow/integration/full suites, viability, durability, blocking-I/O, live report redaction, and repository-boundary checks; verify `backend/` and `frontend/` are unchanged. @impl EVH-001..EVH-010
