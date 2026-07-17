## Context

The archived `evaluate-harden-deep-research-graph` change established the correct four asset classes, five authenticity levels, five stable seams, deterministic/live/release commands, incident mappings, and regression-descent policy. Its final deterministic union collected 1,275 tests and the full-real lane eventually passed.

The follow-up audit found that this breadth is uneven:

- deterministic collection is weighted toward unit, contract, domain, and engine tests, while `pytest -m workflow` collects zero tests even though the marker is declared;
- the ten first-wave scenario families all declare `SCRIPTED_REAL_WORKFLOW` even though some risks belong at lifecycle or store seams, several contain only string labels, and several are never executed by the deterministic `ScenarioRunner`;
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
- Compute reproducible quality metrics from the authority that actually exists, and report unavailable when semantic labels or required artifacts do not exist.
- Keep `tasks.md` as the truthful progress surface with focused selectors and observed results recorded as work proceeds.

**Non-Goals:**

- Do not add a second test framework, a generalized simulation platform, or test-only production interfaces.
- Do not require every scenario to traverse the entire graph; each scenario stops after the smallest seam that proves its risk.
- Do not add another full-real E2E, run credentials in PR CI, or turn a single live result into a quality threshold.
- Do not use line coverage, test count, or directory placement as proof of authenticity.
- Do not change production prompts, policies, budgets, graph topology, checkpoint state, sandbox artifacts, configured tools/models, skills, Agent/SOUL, MCP, ACP, or task subagents. If a new deterministic regression exposes production nonconformance, return to proposal/design review before editing production behavior or interfaces and reassess the release-proof policy from that changed scope.
- Do not modify `backend/` or `frontend/`.

## Decisions

### 1. Keep pytest as the runner and make deterministic selections disjoint

Tests that traverse a real scripted agent workflow will carry `@pytest.mark.workflow`. `make test-workflow` will select that marker while excluding `requires_llm`, `release_e2e`, and `postgres`. `make test-fast` and `make test-integration` will explicitly exclude `workflow`; those two correctness selections remain path-disjoint, and their union with `make test-workflow` equals the complete network-free deterministic selection. The live selector is `requires_llm and not release_e2e`, while the release selector is `requires_llm and release_e2e`; governance rejects either marker's misuse, including any `release_e2e` test missing `requires_llm`. All five focused selections are therefore pairwise disjoint. PR CI will run the three deterministic selections.

The workflow marker selects the workflow-conformance asset class; it is not itself one authenticity level and is not a synonym for the `integration/` directory. A marked test must execute at least one temporally ordered production workflow: a real lifecycle/mixed graph transition sequence, a real bridge-driven agent loop, or a real worker submit/gate sequence. A lifecycle sequence without an embedded agent may carry `REAL_NODE_FAKE_CAPABILITIES` or no higher authenticity claim; only a real bridge-driven agent loop with scripted external adapters may claim `SCRIPTED_REAL_WORKFLOW`. A narrow real-node test and a standalone store fault test are correctness assets, not workflow conformance merely because they span files.

Alternative considered: infer workflow coverage from paths such as `tests/integration/`. Rejected because existing integration tests range from narrow glue checks to complete bridge/store/gate paths, and the path cannot prove authenticity.

### 2. Separate scenario families, execution cases, observations, and static claims

The current `Scenario` type mixes semantic intent, deterministic scripts, live requirements, lane identity, and expected execution results. It will be replaced by two small data contracts plus one shared assertion interface:

```text
 ScenarioFamily       ScenarioCase
(intent/degradation) (lane/seam/invariants)
          \             /
           \           /
        ScenarioObservation
                 |
                 v
       assert_scenario_case(...)
```

`ScenarioFamily` owns only the stable family id, objective/risk intent, owning requirements/regressions, and permitted degradation. `ScenarioCase` owns a stable case id, family id, lane, entrypoint, required asset class/seam/authenticity, preconditions and bounds, typed scripted inputs or live requirements, expected route/terminal/artifacts, hard invariants, and applicable metrics. Deterministic and live cases may reference the same family without pretending that they execute the same prefix or can prove the same invariants.

Each focused pytest test explicitly calls the existing production interface appropriate to its case: node/capability, worker subgraph, lifecycle/mixed graph, or authority store. Shared test helpers construct local runtime/model/tool dependencies, but no universal dispatcher hides which production interface is under test. `ScenarioObservation` contains only facts projected from observable calls and the three authorities: route/terminal result, accepted record refs, artifact refs, support/citation bindings, degradation codes, bounded call counts, and typed failure codes. It does not enter production checkpoint state or artifacts.

A central test-owned `TestEvidenceClaim` registry gives each evidence-bearing exact collected selector a stable claim id and binds it to its expected focused selection, requirement ids, asset class, one canonical stable seam, optional authenticity level, at most one scenario case id, and discovery ids. Every registered scenario case resolves to exactly one claim whose collected pytest node id contains that stable case id; a non-scenario incident/node/fault regression claim may omit it. Parameterized evidence cases use their stable case id as the pytest parameter id so the exact selector is deterministic; wildcard or prefix selector claims are forbidden. Uniform provider-shape provenance derives its selector from the registered shape case id instead of duplicating one handwritten claim per fixture. A selector needs a claim only when it is referenced by the requirement-evidence policy or a scenario, incident, node, fault, or discovery inventory; the other ordinary tests are not copied into a second catalog. Inventories reference claim ids instead of maintaining parallel selector/authenticity declarations. Existing `@impl` annotations continue to identify owning implementation surfaces; evidence claims do not replace implementation traceability.

Alternative considered: register arbitrary executor callables or build a closed universal entrypoint dispatcher. Rejected because the four production invocation shapes have substantially different preconditions; a universal dispatcher would expose nearly all of their complexity as a shallow test interface. Explicit pytest execution preserves locality while the family/case/assertion contracts remove meaningful duplication.

Alternative considered: one universal full-graph replay executor. Rejected because it recreates the expensive diagnostic problem and makes narrow failures depend on unrelated phases.

The replacement is incremental, not an in-place flag day. Tasks 2.1-2.6 define and prove the new contracts against synthetic fixtures while the legacy `Scenario`/`ScenarioRunner` remains only as a migration source for the existing catalog. Tasks 3.1-3.10 move each family to collected focused cases. Task 3.11 removes the legacy model/runner and enables real-catalog completeness. No new contract task is considered complete by weakening its schema to accept the legacy string pseudo-scripts.

The shared scripted model fixture follows the narrow mechanism of DeerFlow's proven `FakeToolCallingModel` pattern but retains the local `ScriptedChatModel` name and project-owned fixture module. Behavioral model/tool tests construct the real project agent or runtime bridge and preprogram only external model turns and tool results. The local fixture already fails when responses are exhausted; evidence-bearing workflow cases additionally assert their declared model/tool call counts, order, and relevant bound-tool observations through `ScenarioObservation`. Ordinary unit tests that use the same fixture are not forced to claim or consume a complete workflow trace. Patching `create_agent`, a bridge builder, or another assembly factory remains appropriate for constructor arguments, middleware order, tool exposure, and other wiring assertions; such a patched-assembly test cannot claim agent-loop or `SCRIPTED_REAL_WORKFLOW` behavior.

This design uses three distinct meanings that were previously all called replay:

1. A typed deterministic scenario case drives short in-memory model/tool scripts through an explicit production interface and asserts authority outcomes. This is the default for first-wave workflow cases.
2. A minimized provider-shape case feeds synthetic structured payload variation through the lowest parser/materializer/validator seam. It is fixture-based regression data, not an LLM conversation recording.
3. A persisted LLM trace replay matches recorded calls and stable event shapes. It is justified only when a concrete multi-caller/interleaved trace cannot be represented faithfully by short scripts. Following DeerFlow's actual replay implementation, matching is caller-aware, declared volatile UUID/time/path fields are normalized, and a miss fails loudly even if outer middleware converts the model error into an ordinary response. Golden assertions cover stable shape/order rather than raw prose or volatile values. This change does not add that third mechanism unless a migrated case documents the exact insufficiency and returns to review of the smallest fixture needed.

Reusable fixtures establish a hermetic boundary around only the mutable state they touch: isolated effective home/config paths and contained filesystem, explicit local runtime configuration, and public reset/restore APIs for installed sandbox providers, cached AppConfig, or project GraphHost state where used. This is concrete in the current live/release adapter: `_LiveAdapter` installs a process-global provider with `set_sandbox_provider(...)`, so its owner must call the public `reset_sandbox_provider()` during teardown even after failure. The design does not introduce a speculative autouse reset for every DeerFlow singleton. The existing public-network denial remains a separate suite-wide guard; it does not substitute for state cleanup. The local public-entry fake remains independent unless a later case demonstrates material duplication worth consolidating.

### 3. Use one canonical evidence vocabulary and prove invariants from authority projections

The static evidence vocabulary separates concepts that are currently conflated:

- asset class: code correctness, deterministic workflow conformance, live behavioral evaluation, or release acceptance;
- canonical stable seam: domain/engine, node interface, runtime integration, lifecycle/mixed graph, or public entry;
- authenticity: optional for code correctness, otherwise `FAKE_GRAPH`, `REAL_NODE_FAKE_CAPABILITIES`, `SCRIPTED_REAL_WORKFLOW`, `LIVE_REAL_DEPENDENCIES`, or `FULL_REAL_PIPELINE`.

Authenticity qualifies how a claim is exercised at its declared asset class, seam, and scope; it does not widen that scope. Ordering may reject an under-authentic claim only after asset class and seam compatibility are established. A focused `LIVE_REAL_DEPENDENCIES` node claim therefore cannot satisfy a deterministic-workflow, lifecycle-prefix, public-entry, or `FULL_REAL_PIPELINE` requirement merely because its external dependencies are real.

Current ad hoc `contract`, `module`, and `runtime-store` labels will migrate to the appropriate canonical seam and asset class. A code-correctness claim is not forced onto the agent authenticity ladder.

Invariant names will resolve through a closed test-owned registry. Each invariant evaluator consumes a scenario observation projected from:

- checkpoint state for lifecycle, route, identity, attempt, and terminal control facts;
- the validated submission ledger for accepted evidence and conflict/idempotency facts;
- contained sandbox reads for artifact schemas, hashes, findings, citations, and final content refs.

The shared assertion interface will reject unknown invariant names and will evaluate every invariant, support/citation expectation, artifact expectation, and permitted degradation applicable to the case. Successful execution will no longer set all hard-invariant flags to `True` by construction. Diagnostics remain limited to family/case/lane/authenticity, invariant name, typed codes, counts, hashes, and redacted structural summaries.

### 4. Treat provider-shape history as minimized structured fixtures

Historical provider variations will be represented by minimized typed shape cases under a dedicated test fixture corpus. Each case declares:

- stable fixture id and originating `LIVE-*` or `RELEASE-*` discovery id;
- focused node and input schema version;
- a minimized synthetic payload preserving only the relevant keys, types, ordering, and aliases;
- expected normalized contract or expected typed fail-closed result;
- explicit byte bounds and synthetic-domain metadata, plus provenance-review metadata stating that the payload was minimized instead of copied as a raw response.

A small machine-readable `DiscoveryDisposition` inventory owns classification independently from the fixture bodies. Each known discovery has exactly one disposition: `uniform_shape`, `existing_regression`, or `provider_only`. `uniform_shape` carries one stable intended shape-case id that must resolve to a collected claim at corpus closure; `existing_regression` carries one existing collected claim id; `provider_only` carries one bounded live case id and a non-empty rationale explaining why deterministic replay would be misleading. Fields for other dispositions are forbidden. This makes classification governable without parsing the human regression-descent table or duplicating fixture payloads.

Parameterized tests will feed uniform shape cases through the production parser/materializer/validator at the lowest responsible seam. Existing focused regressions may remain individual tests when their setup or seam differs; they register the same provenance rather than being duplicated only to fit a data file. Corpus governance can mechanically reject unknown discoveries, duplicate fixture ids, unowned cases, oversize payloads, non-synthetic external URLs, credentials, and raw host paths. A required provenance review records that free text is synthetic/minimized; this design does not claim that arbitrary copied research prose can be detected mechanically.

Alternative considered: retain raw provider responses. Rejected because they may contain research content, URLs, credentials, or host diagnostics and are larger than necessary to reproduce structural behavior.

Alternative considered: keep one hand-written test per alias. Rejected because provenance and coverage drift become difficult to audit and new shapes require repeated test scaffolding.

### 5. Add late-node live canaries by seeding existing authorities

Nightly live evaluation will add three bounded scenarios:

- Wave1 with one validated Wave0 submission and one topic;
- Wave2 synthesis with a small set of validated accepted Wave0/Wave1 records;
- targeted evidence with one typed synthesis gap and the minimum accepted context.

Seed builders will create validated checkpoint projections for compact control state and publish ledger/content authority through the existing store interfaces; they will not write fake ledger lines or place sandbox bodies in checkpoint state. The canary then invokes the real focused `NODE_SPEC` interface with `RuntimeNodeAgentBridge` constructed through the current production capability builders and the existing live factory's bounded budget override: Wave1 uses `_build_wave1_capabilities`, Wave2 uses the shared zero-tool `_build_hitl1_capabilities`, and targeted gap work uses `_build_wave0_capabilities`, plus their normal work-unit/synthesis stores. For Wave1, the test separates the reserved `WORK_UNIT_GATE_VIEW_KEY`, applies only `WORK_UNIT_GATE_PREVIEW_FIELDS` through `preview_work_unit_update`, validates the gate view against that projected state, then evaluates `evaluate_gate_for_node(..., real_wave1_gate_def())`. Wave2 first asserts semantic-floor behavior inside the real node, then separately evaluates `evaluate_gate_for_node` with `real_wave2_gate_def()` on the node-updated state. Targeted gap work asserts its subgraph's validated submit/ledger result and does not claim a nonexistent phase gate. These private builders are current implementation anchors, so focused canary tests may change with runtime assembly; they are not promoted to production interfaces. This deliberately proves focused node/provider compatibility with current production dependency construction, not graph-recipe assembly. Each run uses isolated identity, one outer attempt, scenario-specific call/token/time bounds, and redacted structural reporting.

These cases claim `LIVE_REAL_DEPENDENCIES` only at the focused node/runtime-integration seam with seeded authority preconditions. They do not claim public-entry, predecessor-lifecycle, production recipe assembly, or full-pipeline coverage. All six live cases run nightly only when their declared scenario deadlines sum to at most 900 seconds, leaving at least five minutes of the existing 20-minute job timeout for install, preflight, report publication, and cleanup. A focused web case may declare at most 240 seconds and a zero-tool case at most 120 seconds. Measured overruns block nightly enablement; the CI timeout is not raised to make the contract pass. The existing single release E2E remains the only `FULL_REAL_PIPELINE` proof.

Raw live/release reports remain gitignored operational artifacts. The existing successful full-real report will be reduced to one committed redacted release attestation containing only schema version, scenario id, source observation date, `source_report_sha256` of the local source report, attestation base revision, an explicit `run_revision=unknown`, attempt/retry counts, all eight invariant booleans, accepted/citation counts, and aggregate token/tool/time values. Its provenance keeps three scopes distinct: `source_run` facts are derived from the hashed JSON; `source_archive_scan` verdicts cite the committed final scan record at `openspec/changes/archive/2026-07-17-evaluate-harden-deep-research-graph/tasks.md` and preserve that its target set was both live and release reports; and `attestation_scan` verdicts describe deterministic scans of the newly generated committed file. `attestation_base_revision` identifies the repository state inspected while generating the attestation; it is not the run revision and avoids commit self-reference. The source report has no embedded run timestamp or revision, so the attestation SHALL NOT manufacture them from file metadata or a later commit. It contains no invocation ids, provider response shapes, model text, source URLs, host paths, or credentials. A deterministic contract validates this attestation against the release invariant schema and rejects scan verdicts without their declared evidence scope and source locator. The stale committed `NOT READY / full-real not executed` parity report is updated to the achieved state or explicitly superseded so committed evidence cannot contradict itself.

The reviewed migration input is frozen here so local report cleanup cannot make the task irrecoverable: source observation date `2026-07-17`; `source_report_sha256=36f41ca7c631320d05205f26afba9fbddcc0652e8f8323a7832e7816b7828146`; attestation base revision at review `665ca33575b0d7eb3a408d68956d0ac7b2669d47`; one attempt, zero outer retries; `accepted_evidence_present`, `checkpoint_isolated`, `citation_bindings_valid`, `cleanup_complete`, `lifecycle_trace_complete`, `paths_contained`, `report_artifacts_present`, and `terminal_completed` all true; two accepted submissions; two citation claims and two citation refs; 37,597 input tokens, 18,591 output tokens, 12 tool calls, and 286.1884355 seconds. The archived change tasks independently record the same pass with rounded duration/counts and record no credential-value or raw-host-path matches in the live/release archive scan; those scan verdicts are historical scan evidence, not fields invented inside the source JSON.

This change validates the collected release selector and committed attestation, but does not routinely spend another full-real run. A fresh release E2E is required only if implementation changes the release runner/public entry or a focused live discovery cannot be closed below the full pipeline; either condition returns to scope review before the run.

### 6. Compute quality from a validated evaluation outcome

A test-owned `ValidatedEvaluationOutcome` projection will read only available validated ledger records, topic/question coverage, findings/gaps, final citation maps, and optional labeled replay expectations. A metric not selected by the scenario case is `not_applicable`; a selected metric whose required authoritative input is absent or semantically unlabeled is `insufficient_authority`. A selected ratio with an empty authoritative denominator is also `insufficient_authority`; an authoritative count metric may be `measured` as zero when its source collection is present and valid but empty. `not_applicable` and `insufficient_authority` carry `value=null`; a measured metric carries a typed numeric value. Each result includes its evidence basis, so an unavailable ratio never becomes a vacuous zero or one and a measured zero count cannot be confused with missing authority. Pure metric functions use these semantics:

- citation binding rate: fraction of final citation refs bound to accepted ledger records, a structural hard signal;
- citation precision: fraction of cited claim/ref pairs labeled as genuinely supporting in a replay corpus, unavailable for unlabeled live output;
- citation completeness: fraction of emitted final claim-map entries with at least one citation bound to accepted evidence when a final citation map is available;
- finding support coverage: fraction of synthesis findings with accepted backing refs, reported separately from final citation completeness;
- must-answer coverage: fraction of authoritative must-answer questions for which every known topic in the planner's question-to-topic coverage map is represented by at least one finding or typed honest gap through `affected_topics`; partially represented questions and missing/unmapped topic ids are reported separately and never treated as direct question-to-finding authority;
- canonical-URL diversity: count of distinct canonical URLs in validated accepted `SourceRef` values; provider-local `source_id` values are references, not cross-record source identity;
- source-host diversity: count of distinct normalized hosts represented by accepted evidence, reported separately so multiple sources on one host do not inflate host breadth;
- contradiction recall: fraction of annotated expected contradiction ids represented in findings, available only for labeled replay cases;
- unsupported major claims: count derived from labeled expected support; the structural no-backing-ref count is reported separately.

Quality remains separate from hard lifecycle/security/authority failures. Live reports add `report_schema_version=1` and `metrics_schema="evidence-v1"`; reports without those fields are classified as legacy and are not compared to the new baseline. This is a compatible serialization extension, not a production schema change. Live reports record applicable metrics and trends, but this change does not introduce blocking quality thresholds.

### 7. Strengthen governance around evidence quality, not volume

The asset checker will collect the deterministic aggregate and each focused fast/integration/workflow/live/release selection, then join scenario families/cases, evidence claims, pytest markers, node/incident/fault references, provider shape cases, and regression-descent discoveries. It will fail when:

- a scenario family has no deterministic case or collected evidence claim;
- a case that claims scripted workflow authenticity has no collected workflow selector;
- a workflow selector is credentialed, excluded from deterministic CI, or lacks runtime evidence assertions;
- a node/incident/fault reference disagrees with its central claim's asset class, authenticity, or stable seam;
- a provider fixture has no discovery provenance or a closed replayable discovery has no deterministic fixture/selector;
- a declared live scenario has no bounded precondition or report assertion;
- any focused selection overlaps another, the workflow lane is empty, or the three deterministic focused selections do not exactly partition the aggregate.

Requirement coverage will continue to require every alive requirement to have at least one collected deterministic test-side `@impl` reference. That ownership reference alone will not satisfy a cross-lane evidence policy: a small policy declares required asset classes, and optional authenticity, only where the specification demands them. For example, `EVH-004/008` require workflow-conformance claims, while `EVH-005` requires deterministic control, live-behavior, and release-acceptance claims. Asset classes are independent evidence categories, not a single ordered ladder. Other requirements keep an appropriate deterministic claim at their responsible seam.

Governance is introduced incrementally so every apply task can finish green. Task 1.1 records revision/worktree/protected-tree baselines and read-only probes before any implementation or governance mutation; task 1.2 then establishes the authority/lifecycle policy and bootstrap pointers before executable asset work. Early contract tasks use synthetic valid/invalid registries to prove failure behavior without making the partially migrated repository an expected CI failure. Real-catalog enforcement is enabled only at its closure task: current model/tool-node workflow coverage in task 1.5, all ten scenario families in tasks 3.11-3.12, provider-discovery closure in task 4.8, and cross-lane requirement policy in task 7.1. Baseline probes record current failures such as the empty workflow collection, but no checked task leaves a deliberately failing repository gate for a later group to repair.

Pure validators receive direct valid/invalid fixture tests for every rule they own. Subprocess collectors, syntax-tree discovery, archive scans, and runtime detectors additionally receive a smoke case when an empty or mis-scoped scan could otherwise return success without exercising the detector. This is the applicable lesson from DeerFlow's blocking-I/O gate smoke test; it does not create a second generic `meta-test` category or require duplicate negative tests for every ordinary validator.

The durable policy is split by authority rather than copied verbatim into three places:

- the `evaluation-hardening` main spec owns approved observable and mechanically verifiable semantics; its one active delta owns the pending modifications during review/apply, archive/sync promotes them into the main spec, and archived artifacts become historical rather than continuing authority;
- `openspec/governance/test-evidence-policy.md` defines only the authority table, lifecycle, and synchronized-change protocol. It points to the owning spec for semantics, the test-owned registries for enumerable evidence metadata, and the agent checker for execution; it does not restate a competing catalog or independent SHALL requirements;
- `openspec/config.yaml` keeps only short artifact-authoring rules and a link to that policy, including the requirement to identify the evidence class/seam and justify any replay/live/E2E escalation;
- `agent/AGENTS.md` summarizes the runtime/test commands and project-specific implementation contract, while `agent/scripts/check_test_assets.py` remains the executable owner of agent asset collection and joins.

The root OpenSpec governance scripts remain read-only and Python-standard-library-only. This change does not make them invoke pytest, import agent dependencies, or maintain another exhaustive selector catalog. `openspec/governance/README.md` will list the authority/lifecycle policy as a fifth governance concern while explicitly identifying the spec/delta lifecycle as semantic authority and the executable asset checker as agent-owned. Because the new policy is a permanent governed path, task 1.2 also adds it to `project-structure.toml`, regenerates the bounded `agent/AGENTS.md` structure block, and updates structure-governance fixtures; the existing project-structure spec already delegates exact current-path enumeration to that registry, so no new project-structure semantic requirement is introduced. The policy, README pointer, `openspec/config.yaml` bootstrap rules, and a concise human-authored `agent/AGENTS.md` pointer are created in the first apply group so later slices are reviewed under them; detailed final documentation is synchronized again after the executable contracts stabilize.

At apply start, the baseline record captures `apply_base_revision`, the initial worktree status, and Git tree hashes for protected production/upstream paths: `agent/src`, `backend`, `frontend`, the release runner, and the public entry. Final boundary validation compares against those recorded trees rather than an assumed branch name or the proposal-review commit. Pre-existing user changes are recorded and preserved; they are not silently attributed to or reverted by this change. Any task that needs to alter a protected tree stops for scope review before mutation.

The current model/tool-node inventory is the six production node packages containing real `run_agent` calls or loaded method references: `hitl1`, `topic_planning`, `wave0`, `wave1`, `wave2_synthesis`, and `targeted_evidence`. This set is not inferred from `NODE_SPEC.capabilities`: topic planning has no declared capability and passes `run_agent` as a callable, while Wave2 declares its store capability even though it calls the shared bridge. Test governance uses a Python syntax-tree scan across each production node package to compare discovered loaded `run_agent` attributes with the explicit inventory, while claims and focused tests prove behavior at the interface. The syntax scan detects ownership drift; it is not evidence that an internal call executed.

### 8. Keep requirement-to-work traceability explicit

The apply plan covers the complete capability, including the two requirements whose normative text is unchanged by this delta:

| Requirement | Planned proof/work |
| --- | --- |
| `EVH-001` | typed family/case/observation contracts and all ten deterministic risk-family replays (tasks 2-3) |
| `EVH-002` | labeled replay inputs and authority-based metric semantics (tasks 3.2-3.3 and 5) |
| `EVH-003` | unchanged fault guarantee exercised by timeout, budget, partial-success, checkpoint, and filesystem cases (tasks 3.6-3.10) |
| `EVH-004` | unchanged adversarial-isolation guarantee exercised through the real untrusted worker/gate path (task 3.4) |
| `EVH-005` | protected release baseline, disjoint lanes, six bounded live cases, versioned reports, and singular persisted release proof (tasks 1.1-1.2, 1.6-1.8, 5.5, 6, and 7.2) |
| `EVH-006` | central exact-selector claims, migrated incident inventories, and live/release discovery provenance (tasks 1.3-1.4, 4, and 7.2) |
| `EVH-007` | canonical seams/authenticity, governed scenario cases, observations, and valid seeded preconditions (tasks 1.3, 2, 3.11, and 6.1) |
| `EVH-008` | audited real-node/workflow coverage plus first-wave and gap-closing workflow cases (tasks 1.4-1.5 and 3) |
| `EVH-009` | five disjoint focused selections, deterministic partition, collected-claim governance, and cross-lane policy (tasks 1.1-1.2, 1.5-1.8, 2.6, 3.11, 6, and 7.1) |
| `EVH-010` | minimized provider-shape provenance, provider-only live rationale, and regression-descent documentation (tasks 4, 6.5, and 7) |

Task 1.2 also references existing `PRS-004` solely to register the new permanent policy path, regenerate the controlled guide block, and keep structure-governance fixtures aligned. This does not change the project-structure grammar or allocate a new structural requirement.

No task may use a broader asset class, seam, or authenticity label merely to satisfy this table; the collected selector and observable authority assertions remain decisive.

## Risks / Trade-offs

- **[Risk] Scenario infrastructure becomes a second application framework.** -> Keep family/case/observation contracts and one assertion interface, but let focused pytest tests invoke existing production interfaces explicitly; do not add a universal executor or reproduce graph routing.
- **[Risk] Static claims overstate dynamic execution.** -> Claims are reviewable mappings, not runtime proof. Focused tests must assert observable model/tool calls and checkpoint/ledger/artifact outcomes; governance verifies collection and consistency but does not claim impossible static introspection of every internal call.
- **[Risk] Provider fixtures overfit one vendor's formatting.** -> Minimize fixtures to semantic structural variants, retain provenance, and require canonical output or fail-closed behavior rather than vendor-specific text.
- **[Risk] Seeded live nodes hide predecessor incompatibility.** -> Keep deterministic mixed-prefix tests and the one release E2E; label direct live canaries honestly and never use them as predecessor/public-entry evidence.
- **[Risk] Three additional live canaries increase nightly cost and runtime.** -> Use the smallest accepted authority fixtures, one topic/gap, one outer attempt, explicit budgets, and separate focused reports.
- **[Risk] Improved metrics change historical numbers.** -> Version the evaluation outcome/report schema if serialized fields change, keep old reports readable as historical evidence, and establish a new observational baseline without retroactive thresholds.
- **[Risk] Reclassifying existing tests initially reduces apparent coverage.** -> Accept the honest reduction, then fill only demonstrated gaps; never preserve a higher authenticity claim for dashboard continuity.
- **[Risk] Test guidance diverges across spec, governance, config, and agent docs.** -> Keep normative semantics only in the active spec, use governance solely for authority/lifecycle routing, keep `openspec/config.yaml` and `agent/AGENTS.md` as concise bootstrap pointers, and leave enumerable claims plus pytest collection with the agent-owned assets.

## Migration Plan

1. Record the apply/protected-tree and read-only behavioral baselines before any mutation, establish the test-evidence authority/lifecycle policy plus concise bootstrap pointers, then add each contract's synthetic valid/invalid fixtures with its owning task without leaving the repository gate red.
2. Introduce the central evidence claims, canonical seam vocabulary, syntax-discovered six-node workflow inventory, disjoint deterministic selections, scenario family/case/observation contracts, and shared assertion interface.
3. Migrate the ten scenario families one risk slice at a time, retaining existing focused tests and binding them to cases/claims at an equal or lower stable seam.
4. Add minimized provider-shape fixtures and map existing live/release discoveries before adding new live execution.
5. Replace metrics with the typed validated outcome projection and establish `evidence-v1` semantics before consuming them in new live reports.
6. Add the three direct late-node live canaries and report-schema assertions; then run the complete six-case lane with fresh identities and persist its redacted aggregate evidence before enabling all six nightly.
7. Commit the minimized release attestation, reconcile stale evidence documents, synchronize final agent/test documentation with the already-established authority policy, run the complete deterministic/specialized/live validation matrix, and avoid rerunning full-real unless the explicit rerun policy is triggered.

Rollback is test-owned: revert the implementation commits for the new tests, fixtures, commands, workflows, and evidence documents if the new lanes cannot run reliably. No production state, runtime configuration, database, checkpoint, or sandbox migration is required.

## Open Questions

None after review round 9. Scope expansion that changes production behavior, schemas, or interfaces requires returning to proposal/design review before implementation.
