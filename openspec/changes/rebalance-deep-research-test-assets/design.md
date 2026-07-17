## Context

The archived `evaluate-harden-deep-research-graph` change established the correct four asset classes, five authenticity levels, five stable seams, deterministic/live/release commands, incident mappings, and regression-descent policy. Its final deterministic union collected 1,275 tests and the full-real lane eventually passed.

The follow-up audit found that this breadth is uneven:

- deterministic collection is weighted toward unit, contract, domain, and engine tests, while `pytest -m workflow` collects zero tests even though the marker is declared;
- the ten first-wave scenario families declare `SCRIPTED_REAL_WORKFLOW`, but several contain only string labels and are never executed by the deterministic `ScenarioRunner`;
- the runner checks route, terminal state, and artifact names, but does not derive declared hard invariants, citations, or permitted degradation from checkpoint, ledger, and sandbox authorities;
- selector governance verifies that a test exists, not that its marker, execution path, and claimed seam agree;
- nightly live evaluation stops at Wave0, while 15 of the 31 recorded live/release discoveries concern Wave1 or Wave2 synthesis behavior;
- current quality metrics are pure and deterministic but use placeholder proxies such as `ref:` prefixes and submission counts rather than validated citation and question bindings.

This is a test-owned architecture change. Production topology, node contracts, checkpoint schema, sandbox layout, runtime configuration, and authority ownership remain unchanged. `backend/` and `frontend/` remain untouched.

## Goals / Non-Goals

**Goals:**

- Make deterministic workflow-conformance coverage an independently selectable, non-empty, mechanically governed lane.
- Make every first-wave scenario an executable replay through its lowest responsible production seam.
- Derive scenario assertions from the three existing authorities rather than from descriptive metadata or model text.
- Preserve historical provider response variations as minimized, redacted, data-driven regression fixtures.
- Detect late-node provider drift with bounded direct live canaries instead of another full pipeline.
- Compute reproducible quality metrics from validated evidence, findings, citations, and question bindings.
- Keep `tasks.md` as the truthful progress surface with focused selectors and observed results recorded as work proceeds.

**Non-Goals:**

- Do not add a second test framework, a generalized simulation platform, or test-only production interfaces.
- Do not require every scenario to traverse the entire graph; each scenario stops after the smallest seam that proves its risk.
- Do not add another full-real E2E, run credentials in PR CI, or turn a single live result into a quality threshold.
- Do not use line coverage, test count, or directory placement as proof of authenticity.
- Do not change production prompts, policies, budgets, graph topology, checkpoint state, sandbox artifacts, configured tools/models, skills, Agent/SOUL, MCP, ACP, or task subagents unless a red deterministic regression exposes nonconformance with an existing requirement.
- Do not modify `backend/` or `frontend/`.

## Decisions

### 1. Keep pytest as the runner and add an explicit workflow lane

Tests that traverse a real scripted agent workflow will carry `@pytest.mark.workflow`. `make test-workflow` will select that marker while excluding `requires_llm`, `release_e2e`, and `postgres`; the complete deterministic union will continue to include the same tests. PR CI will run the workflow lane explicitly after fast correctness tests.

The workflow marker is an authenticity claim, not a synonym for the `integration/` directory. A marked test must execute the applicable production node or lifecycle handler and all applicable seams between the external adapter and authoritative result. A node without a model/tool loop may be covered at `REAL_NODE_FAKE_CAPABILITIES` but must not be marked workflow merely because it spans files.

Alternative considered: infer workflow coverage from paths such as `tests/integration/`. Rejected because existing integration tests range from narrow glue checks to complete bridge/store/gate paths, and the path cannot prove authenticity.

### 2. Separate scenario data, seam adapters, and execution evidence

The test-owned scenario module will expose one small execution interface:

```text
Scenario data + selected seam adapter
                 |
                 v
          execute(scenario)
                 |
                 v
   ScenarioExecutionEvidence
```

Scenario data owns objective, typed scripted model turns, typed tool results/failures, fault points, preconditions, expected route/terminal/degradation, required authority assertions, and metrics. A bounded registry maps a stable entrypoint kind to an existing seam adapter: node/capability, worker subgraph, lifecycle/mixed graph, or authority store. The adapter constructs real project nodes, bridge, middleware, policy, validators, checkpoint/store, and local filesystem as applicable.

`ScenarioExecutionEvidence` is test-owned and contains only observable facts needed by assertions: scenario id, lane, authenticity, exercised seams, route/terminal result, accepted record refs, artifact refs, citation bindings, degradation codes, bounded call counts, and typed failure codes. It does not enter production checkpoint state or artifacts.

Alternative considered: embed arbitrary executor callables inside each scenario. Rejected because it makes the manifest opaque, couples data to pytest implementation details, and prevents governance from checking completeness.

Alternative considered: one universal full-graph replay executor. Rejected because it recreates the expensive diagnostic problem and makes narrow failures depend on unrelated phases.

### 3. Prove hard invariants from authority projections

Invariant names will resolve through a closed test-owned registry. Each invariant evaluator consumes execution evidence projected from:

- checkpoint state for lifecycle, route, identity, attempt, and terminal control facts;
- the validated submission ledger for accepted evidence and conflict/idempotency facts;
- contained sandbox reads for artifact schemas, hashes, findings, citations, and final content refs.

The runner will reject unknown invariant names and will evaluate every declared hard invariant, citation expectation, artifact expectation, and permitted degradation. Successful execution will no longer set all hard-invariant flags to `True` by construction. Diagnostics remain limited to scenario/lane/authenticity, invariant name, typed codes, counts, hashes, and redacted structural summaries.

### 4. Treat provider-shape history as minimized structured fixtures

Historical provider variations will be stored under a dedicated test fixture corpus. Each fixture declares:

- stable fixture id and originating `LIVE-*` or `RELEASE-*` discovery id;
- focused node and input schema version;
- a minimized synthetic payload preserving only the relevant keys, types, ordering, and aliases;
- expected normalized contract or expected typed fail-closed result;
- sensitivity metadata proving that credentials, raw host paths, and original research content are absent.

Parameterized tests will feed these fixtures through the production parser/materializer/validator at the lowest responsible seam. Corpus governance will reject unknown discoveries, duplicate fixture ids, unowned payloads, and secret/path patterns.

Alternative considered: retain raw provider responses. Rejected because they may contain research content, URLs, credentials, or host diagnostics and are larger than necessary to reproduce structural behavior.

Alternative considered: keep one hand-written test per alias. Rejected because provenance and coverage drift become difficult to audit and new shapes require repeated test scaffolding.

### 5. Add late-node live canaries by seeding existing authorities

Nightly live evaluation will add three bounded scenarios:

- Wave1 with one validated Wave0 submission and one topic;
- Wave2 synthesis with a small set of validated accepted Wave0/Wave1 records;
- targeted evidence with one typed synthesis gap and the minimum accepted context.

Fixtures will create the same test-owned ledger and sandbox artifacts that production predecessors would publish, then invoke the real focused node through its normal runtime bridge and policy. Wave1 and targeted evidence use the real configured model and web tool; Wave2 uses the real model and its zero-tool policy. Each run uses isolated identity, one outer attempt, strict call/token/time bounds, and redacted structural reporting.

These scenarios claim `LIVE_REAL_DEPENDENCIES` only for the focused node and seeded authority preconditions. They do not claim public-entry, predecessor-lifecycle, or full-pipeline coverage. The existing single release E2E remains the only `FULL_REAL_PIPELINE` proof.

### 6. Compute quality from a validated evaluation outcome

A test-owned `ValidatedEvaluationOutcome` projection will read already validated ledger records, findings, question bindings, and citation maps. Pure metric functions will use these semantics:

- citation precision: fraction of emitted citation refs bound to accepted ledger records;
- citation completeness: fraction of major findings with at least one bound citation;
- must-answer coverage: fraction of required question ids explicitly bound to supported findings or typed honest gaps;
- source diversity: distinct canonical source identities and normalized hosts represented by accepted evidence;
- contradiction recall: fraction of annotated expected contradiction ids represented in findings, only for labeled replay cases;
- unsupported major claims: count of major findings without accepted supporting refs.

Empty-input behavior will be explicit and tested. Quality remains separate from hard lifecycle/security/authority failures. Live reports record metrics and trends, but this change does not introduce blocking quality thresholds.

### 7. Strengthen governance around evidence quality, not volume

The asset checker will join scenario manifests, executor bindings, collected selectors, pytest markers, node/incident/fault inventories, provider fixtures, and regression-descent discoveries. It will fail when:

- a scripted workflow scenario has no deterministic executor or collected workflow selector;
- a workflow selector is credentialed, excluded from deterministic CI, or lacks runtime evidence assertions;
- a node/incident selector's declared authenticity or stable seam disagrees with its registered evidence;
- a provider fixture has no discovery provenance or a closed replayable discovery has no deterministic fixture/selector;
- a declared live scenario has no bounded precondition or report assertion;
- any lane overlaps incorrectly or the workflow lane is empty.

Requirement coverage will continue to require collected deterministic tests, but module-level `@impl` text alone will not satisfy requirements that explicitly demand scripted workflow authenticity. The checker will use requirement-to-required-authenticity metadata for those requirements.

## Risks / Trade-offs

- **[Risk] Scenario infrastructure becomes a second application framework.** -> Keep one execution result type, a closed entrypoint registry, and thin adapters around existing production interfaces; do not reproduce graph routing or business rules in test code.
- **[Risk] Self-reported exercised seams become tautological.** -> Evidence assertions must be derived from observable model/tool call records, checkpoint values, ledger records, and contained artifacts; governance checks registrations, while the tests execute the claims.
- **[Risk] Provider fixtures overfit one vendor's formatting.** -> Minimize fixtures to semantic structural variants, retain provenance, and require canonical output or fail-closed behavior rather than vendor-specific text.
- **[Risk] Seeded live nodes hide predecessor incompatibility.** -> Keep deterministic mixed-prefix tests and the one release E2E; label direct live canaries honestly and never use them as predecessor/public-entry evidence.
- **[Risk] Three additional live canaries increase nightly cost and runtime.** -> Use the smallest accepted authority fixtures, one topic/gap, one outer attempt, explicit budgets, and separate focused reports.
- **[Risk] Improved metrics change historical numbers.** -> Version the evaluation outcome/report schema if serialized fields change, keep old reports readable as historical evidence, and establish a new observational baseline without retroactive thresholds.
- **[Risk] Reclassifying existing tests initially reduces apparent coverage.** -> Accept the honest reduction, then fill only demonstrated gaps; never preserve a higher authenticity claim for dashboard continuity.

## Migration Plan

1. Capture the current selector distribution and add red tests showing the empty workflow lane, inert scenarios, and placeholder metric behavior.
2. Introduce the workflow marker contract, execution evidence model, invariant registry, and non-empty `make test-workflow` lane.
3. Migrate the ten scenario families one risk slice at a time, retaining existing focused tests until their assertions are represented at an equal or lower stable seam.
4. Add minimized provider-shape fixtures and map existing live/release discoveries before adding new live execution.
5. Add the three direct late-node live canaries and report-schema assertions; run them manually with fresh identities before enabling them in nightly CI.
6. Replace metrics with the validated outcome projection and start a new non-blocking baseline.
7. Tighten governance, update operator/developer documentation, run the complete deterministic/specialized/live validation matrix, then leave the single release E2E unchanged.

Rollback is test-only: revert the change as one commit if the new lanes cannot run reliably. No production state, runtime configuration, database, checkpoint, or sandbox migration is required.

## Open Questions

- Whether all three late-node canaries should run nightly from the first merge or whether targeted evidence should begin as manual-only until its provider cost is measured. The default plan is nightly with strict bounds; review may lower its cadence without weakening deterministic coverage.
- Whether serialized live quality reports require an explicit schema-version bump or can add fields compatibly. This will be resolved from the current report consumers before implementation.
