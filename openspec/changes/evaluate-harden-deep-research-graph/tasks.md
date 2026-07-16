## 1. Batch 1 Red Tests And Current-Asset Audit

- [ ] 1.1 Build a current test inventory from pytest collection, classify each asset by stable seam and authenticity level, and record which historical recommendations are already covered, stale, duplicated, or tautological. Add red contract tests for inventory schema and stale selector detection. @impl EVH-006, EVH-007
- [ ] 1.2 Create the machine-readable thirteen-incident mapping with risk family, lowest responsible seam, deterministic pytest node ids, and stable invariant/error; make the mapping checker red for missing or incorrectly selected coverage. @impl EVH-006
- [ ] 1.3 Add red tests for all-real graph compilation/imports, non-interactive policy forwarding, model/tool readiness diagnostics, legal sandbox identity, mounted-workspace store creation, and unique demo thread/run/research identity. @impl EVH-006
- [ ] 1.4 Add red tests for distinct per-node capability/policy resolution, allowed-tool-to-typed-spec completeness, budget admission with large tool results and call boundaries, structured-output repair/fallback, and mixed success/failure gate fatigue. @impl EVH-006, EVH-008
- [ ] 1.5 Add red contract tests proving deterministic, live, release, and Postgres selector sets have the required inclusion/exclusion behavior and that the deterministic lane denies external network access. @impl EVH-009
- [ ] 1.6 Add red governance contract tests for unknown test-side `@impl`, an alive requirement without a collected deterministic test, and package-only references that do not identify a collected test. @impl EVH-009, EVH-010

## 2. Batch 1 Test Control Plane And Incident Closure

- [ ] 2.1 Implement the test-owned incident inventory schema/checker, connect every incident to current collected deterministic selectors, and replace tautological regression claims with tests at the named real seam. @impl EVH-006
- [ ] 2.2 Add shared fixtures for a valid `TrustedRuntimeEnvelope`, real local sandbox mappings, temporary mounted workspace paths, unique thread/run/research identity, deterministic time/randomness, and redacted diagnostics without adding production test hooks. @impl EVH-006, EVH-007
- [ ] 2.3 Extend the scripted model fixture for ordered responses, tool calls, usage metadata, malformed output, timeout, and provider failure; add small typed scripted web tools with fixed results and failures. @impl EVH-007, EVH-008
- [ ] 2.4 Implement the missing incident regressions and any narrowly required production fixes using red-before-green slices; keep `backend/`, `frontend/`, production topology, state schema, and sandbox layout unchanged. @impl EVH-006
- [ ] 2.5 Add `workflow`, `requires_llm`, and `release_e2e` marker semantics plus `make test-fast`, `make test-integration`, and a complete network-free `make test`; retain existing focused targets as compatible subsets. @impl EVH-009
- [ ] 2.6 Implement the requirement-to-collected-test checker, add it to permanent governance commands, and annotate owning test surfaces with exact `@impl EVH-001..010` references. @impl EVH-009, EVH-010
- [ ] 2.7 Add an agent-owned PR workflow for lint, governance, fast tests, and deterministic integration/workflow tests with no model credentials or public-network dependency. @impl EVH-005, EVH-009
- [ ] 2.8 Run the Batch 1 gate: incident checker, requirement coverage checker, selector contracts, `make test-fast`, `make test-integration`, `make lint`, and existing viability/durability/blocking-I/O targets; record the passing selectors in the inventory. @impl EVH-006, EVH-009, EVH-010

## 3. Batch 2 Typed Scenario Corpus

- [ ] 3.1 Add red tests for the test-owned scenario model covering stable id, risk family, requirement/regression ids, entrypoint, authenticity, preconditions, scripted/live inputs, expected outcomes/artifacts, hard invariants, metrics, and permitted degradation. @impl EVH-001, EVH-007
- [ ] 3.2 Implement the minimal scenario model and explicit scripted/live/release runner interfaces; reject unsupported authenticity claims and include scenario identity in every failure. @impl EVH-001, EVH-007
- [ ] 3.3 Port quick factual, claim verification, insufficient evidence, prompt injection, malformed output, tool unavailable/timeout, budget exhaustion, partial success, checkpoint control, and filesystem failure into reusable scenario families. @impl EVH-001, EVH-003, EVH-004, EVH-007
- [ ] 3.4 Replace state-dictionary/string-only eval tests with scenarios that traverse the real lifecycle, untrusted-data, ledger, gate, bridge, checkpoint, or filesystem seam they claim to cover; retain pure metric tests only for independent worked examples. @impl EVH-002, EVH-003, EVH-004, EVH-008
- [ ] 3.5 Expand pure metrics to citation completeness, contradiction recall, and unsupported-major-claim counts, and separate hard-invariant results from quality scores. @impl EVH-002

## 4. Batch 2 Deterministic Agent Workflow Conformance

- [ ] 4.1 Inventory every available real node and add a parameterized conformance matrix requiring one success and one highest-risk failure/repair/degradation/exhausted scenario at the `NodeSpec`/capabilities seam. @impl EVH-007, EVH-008
- [ ] 4.2 Add zero-tool model-node conformance through the real runtime bridge and policy path for HITL1, topic planning, synthesis, HITL2, rerun, readiness, and final delivery where applicable. @impl EVH-008
- [ ] 4.3 Add worker conformance scenarios that traverse real resolver, bridge, scripted web tool, middleware, policy, budget, structured result, attempt-scoped filesystem, submit validator, ledger, gate, and checkpoint for Wave0, targeted evidence, and Wave1. @impl EVH-003, EVH-004, EVH-008
- [ ] 4.4 Add mixed-graph real-prefix scenarios through handlers for each high-risk prefix, keeping unrelated later nodes fake and asserting route, checkpoint, accepted submissions, artifacts, and implementation-mode honesty. @impl EVH-001, EVH-008
- [ ] 4.5 Add real-seam fault injection for duplicate resume, cancel, timeout, partial publication, stale checkpoint, conflicting worker result, and restart recovery; require idempotent recovery or explicit terminal outcome. @impl EVH-003, EVH-010
- [ ] 4.6 Add adversarial source scenarios through scripted tools and the real worker/gate path for prompt injection, forged submission text, route-like content, path traversal, duplicate/SEO sources, and unavailable/paywalled sources. @impl EVH-004, EVH-008
- [ ] 4.7 Run the Batch 2 gate: the entire deterministic suite under network denial, scenario authenticity/coverage contracts, full-fake regressions, all mixed-prefix scenarios, viability, durability, blocking-I/O, lint, and governance. @impl EVH-001, EVH-003, EVH-004, EVH-008, EVH-009

## 5. Batch 3 Live Canaries And Behavioral Reports

- [ ] 5.1 Add red preflight and selection tests proving explicitly selected live runs fail clearly on missing credentials/config and never silently skip, while normal deterministic tests remain credential-free. @impl EVH-005, EVH-009
- [ ] 5.2 Implement live scenario execution and redacted reporting for attempts, hard invariants, quality metrics, model/tool identity, tokens and cost when available, tool calls, retries, and wall time. @impl EVH-002, EVH-005, EVH-007
- [ ] 5.3 Add `@requires_llm` canaries for start-to-HITL1, HITL1-to-topic-planning, and one-topic Wave0 using unique run identities and bounded time/cost/attempts. @impl EVH-005, EVH-009
- [ ] 5.4 Add `make test-live` and a scheduled/manually dispatched agent live workflow using repository secrets, strict credential preflight, redacted logs, and uploaded scenario reports. @impl EVH-005, EVH-009
- [ ] 5.5 Run the live canaries in an appropriately credentialed environment, record the first non-blocking quality baseline and hard-invariant results, and document provider-only behaviors that cannot be faithfully replayed. @impl EVH-002, EVH-005, EVH-010

## 6. Batch 3 Full-Real Release Acceptance

- [ ] 6.1 Add red tests for release preflight, unique thread/run/research identity per invocation, bounded visible retries, checkpoint isolation, and required terminal/artifact assertions. @impl EVH-005, EVH-009
- [ ] 6.2 Implement `@release_e2e` full-real acceptance from the real public entry through final delivery, asserting lifecycle trace, accepted submissions, report artifacts, citation bindings, containment, and cleanup without reusing prior checkpoints. @impl EVH-004, EVH-005, EVH-009
- [ ] 6.3 Add `make test-release-e2e` and a manual/reusable release workflow that depends on deterministic gates and fails preflight rather than skipping when its environment is incomplete. @impl EVH-005, EVH-009
- [ ] 6.4 Add the live/E2E regression-descent workflow and documentation: every discovered defect records risk/seam classification and either a red-before-green deterministic scenario or an explicit provider-only live rationale. @impl EVH-006, EVH-010
- [ ] 6.5 Produce the DPT invariant parity and release report listing achieved and outstanding quality, resilience, cost, and security evidence without treating a single successful demo as proof. @impl EVH-002, EVH-003, EVH-004, EVH-005
- [ ] 6.6 Run the Batch 3 gate in the appropriate credentialed environment: all live canaries and one isolated full-real acceptance pass their hard invariants; archive reports contain no secrets or raw host paths. @impl EVH-005, EVH-009, EVH-010

## 7. Documentation, Governance, And Archive Gates

- [ ] 7.1 Update `agent/README.md` and `agent/AGENTS.md` with the four asset classes, authenticity ladder, five stable seams, scenario rules, commands, CI cadence, and E2E regression-descent policy. @impl EVH-007, EVH-009, EVH-010
- [ ] 7.2 Update the master strategy with final command/workflow names and close the four absorbed test-asset source plans according to `_backlog/plans/README.md`; close the master plan only after all three batches pass. @impl EVH-006, EVH-010
- [ ] 7.3 Run `openspec validate evaluate-harden-deep-research-graph --strict`, `python3 openspec/governance/check_project_reqs.py`, `python3 openspec/governance/check_project_specs.py`, `python3 openspec/governance/check_project_architecture.py`, the new requirement-coverage and incident-coverage checkers, `cd agent && make lock-check && make lint && make test && make test-viability && make test-durability && make test-blocking-io`, and verify `backend/`/`frontend/` are unchanged. @impl EVH-001, EVH-003, EVH-004, EVH-005, EVH-006, EVH-007, EVH-008, EVH-009, EVH-010
