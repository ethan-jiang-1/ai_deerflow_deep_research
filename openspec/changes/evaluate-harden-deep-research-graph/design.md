## Context

The existing suite is large and strong around domain contracts, fake topology, stores, and selected mixed-node lifecycles, but its labels do not express what each test can prove. The current `tests/eval` assets also include assertions over hand-constructed dictionaries and strings that do not cross the lifecycle, gate, ledger, bridge, or filesystem seams named by their requirements. During the real-mode demo integration, this allowed thirteen failures to arrive at the most expensive full-pipeline test.

The approved master strategy at `_backlog/plans/deep-research-test-assets-master-strategy.md` distinguishes code correctness, deterministic agent-workflow conformance, live behavioral evaluation, and full-system acceptance. This change owns all three implementation batches under the existing `evaluation-hardening` capability so requirement ownership and release policy remain in one place.

The production authority model is unchanged: checkpointed `ResearchState` owns control, the submission ledger owns accepted evidence, and the sandbox filesystem owns content. Tests observe those authorities through their public interfaces. No test-only state is added to production checkpoints or artifacts.

## Goals / Non-Goals

**Goals:**

- Close every recorded real-mode incident with a current deterministic regression at the lowest stable seam.
- Make authenticity explicit so fake topology, fake capabilities, scripted workflows, live dependencies, and full-real acceptance cannot be conflated.
- Reuse scenario intent and invariants across deterministic and live execution without making live credentials part of PR CI.
- Exercise real agent loops and mixed workflows while replacing only true external model and tool dependencies.
- Provide mechanical test selection, requirement traceability, scheduled live evaluation, and manual release acceptance.

**Non-Goals:**

- Do not modify `backend/`, `frontend/`, the lead-agent graph, production topology, checkpoint schema, sandbox layout, configured tools/models, skills, Agent/SOUL, MCP, ACP, or DeerFlow task subagents.
- Do not use line coverage or raw test count as an acceptance target.
- Do not add test hooks to production interfaces or expose private implementation seams.
- Do not make subjective quality thresholds blocking until repeated live observations establish a reviewed baseline.
- Do not require Postgres or Docker for the deterministic or live-model baseline; existing deferred Postgres scope remains deferred.

## Decisions

### 1. One OpenSpec change owns three sequential batches

`evaluate-harden-deep-research-graph` is a real implementation change, not a documentation-only umbrella. Its tasks are grouped as incident/control-plane work, deterministic workflow work, and live/release work, each with an intermediate verification gate. The change archives only after all three batches satisfy their requirements.

This is preferred over three changes because OpenSpec has no parent/child change mechanism and all three batches modify the same `evaluation-hardening` requirements and scenario corpus. Three parallel owners would duplicate delta specs and allow command, marker, and scenario semantics to drift. A single unstructured task list is also rejected; batch ordering and completion criteria remain explicit.

### 2. Scenarios are test-owned typed manifests with adapter-specific payloads

Add a small test-owned scenario model under `agent/tests/scenarios/` with JSON-compatible fields for identity, traceability, entrypoint, authenticity, preconditions, scripted inputs, expected outcomes, artifacts, hard invariants, metrics, and permitted degradation. Store scenario definitions as Python modules when they need typed LangChain messages or callable fault injection; use JSON fixtures only for external payload bodies and golden outcomes. Do not add scenario types to production source.

Scenario assertions are shared, but execution adapters remain explicit:

```text
Scenario intent + invariants
        ├── scripted workflow runner -> PR hard gate
        ├── live slice runner         -> nightly hard invariants + quality report
        └── full-real runner          -> manual/release acceptance
```

One generic conditional runner is rejected because it hides which dependencies are real and produces mocks with complex branching. Each runner declares its authenticity and refuses unsupported scenarios.

### 3. Five stable interfaces are the test seams

The primary seams are domain/engine interfaces; `NodeSpec` plus `NodeExecutionCapabilities`; runtime adapter/bridge/store protocols; lifecycle handlers plus mixed graph; and the real public entry. Tests assert observable state, typed outcomes, authoritative store reads, and contained artifacts through those interfaces. Existing tests of private helpers are retained only when the helper is itself a shared behavioral interface; otherwise new coverage is placed at the nearest stable seam.

This keeps tests resilient to node-internal refactors and follows the existing domain protocols rather than adding test-specific ports.

### 4. Deterministic workflow tests use real project modules

Extend `tests/fixtures/fake_models.py` into a scripted external-model adapter capable of ordered assistant responses, tool calls, usage metadata, malformed output, timeout, and provider failure. Add typed scripted web tools and a local runtime fixture that creates a valid `TrustedRuntimeEnvelope`, real local sandbox mapping, temporary mounted workspace, and unique thread/run/research identities.

Workflow tests SHALL use the real `RuntimeNodeAgentBridge`, middleware list, `ExecutionPolicy`, budget accounting, tool policy, node factory, submit validator, gate, stores, checkpoint, and local filesystem wherever the scenario claims those behaviors. Internal nodes, middleware, gates, and stores are not mocked. Time, randomness, model APIs, external tool APIs, and supported publication faults remain injectable external seams.

### 5. Incident coverage is executable inventory, not prose

Create a machine-readable test-owned mapping for the thirteen postmortem incident ids. Each entry names risk family, lowest responsible seam, one or more pytest node ids, and the stable error/invariant. A checker validates that referenced selectors are collected by the deterministic lane. Historical suggested selectors are not copied blindly; current tests are reused when they genuinely cross the seam, and tautological tests are replaced.

The inventory complements `@impl`: incident mapping proves regression closure, while requirement mapping proves capability coverage.

### 6. Commands and markers encode execution cost and authority

Add markers for `workflow`, `requires_llm`, and `release_e2e`; keep `postgres`. Define:

- `make test-fast`: deterministic contract/domain/engine/unit/graph/eval tests that do not require the heavier runtime profiles.
- `make test-integration`: deterministic integration, workflow, durability, and blocking-I/O tests.
- `make test`: the complete deterministic union, excluding `requires_llm`, `release_e2e`, and `postgres`.
- `make test-live`: only credentialed short live slices and live behavioral scenarios.
- `make test-release-e2e`: only full-real acceptance scenarios.

Marker-selection contract tests collect each command's selector expression and fail on overlap, omission, or a credentialed test entering the deterministic union. Deterministic CI also installs a network-denial guard for tests not explicitly marked live/release.

### 7. CI has separate PR, nightly, and release authorities

Add an agent PR workflow for lint, governance, fast tests, and deterministic integration/workflow tests. Add a scheduled plus manually dispatched live workflow that performs credential preflight and runs `make test-live`. Add a manually dispatched/reusable release job for `make test-release-e2e` after deterministic gates pass.

An explicitly selected live/release job fails when its required credential or effective model/tool configuration is absent; it never reports a skipped green job. Reports contain scenario id, attempts, hard invariants, quality metrics, model/tool identity without secrets, token/cost values when available, and wall time. Workflow logs and uploaded artifacts are redacted.

The live workflow uses repository secrets and test-owned runtime construction; it does not commit or rewrite `config.yaml`, `extensions_config.json`, skills, or per-user Agent files. These workflow/test changes take effect immediately on checkout and require neither next-agent-build nor Gateway restart. `reload_boundary.STARTUP_ONLY_FIELDS` remains untouched.

### 8. Hard invariants and quality baselines have different release semantics

Lifecycle, authority, containment, artifact integrity, citation binding, and terminal outcomes are hard failures in all lanes. Quality metrics are deterministic for a fixed outcome, but live thresholds begin as reports. The change records a baseline report and documents candidate thresholds; promoting a subjective metric to blocking requires a later reviewed delta after enough observations, avoiding arbitrary one-run gates.

Full-real release acceptance still fails on inability to complete its declared scenario or on any hard invariant. Retries are bounded, visible, and included in reports rather than silently converting instability into success.

### 9. Requirement coverage is based on collected deterministic tests

Add a governance checker that parses alive requirement ids and test-side `@impl` references, rejects unknown ids, and verifies at least one referenced test is collected by the deterministic suite. A package-level docstring alone is not sufficient evidence. The checker has contract tests using temporary project fixtures and joins the permanent governance gate.

This is stronger than line coverage and lighter than a second manually maintained requirement matrix. Incident ids keep their separate explicit mapping because a requirement can be covered while a specific regression is not.

## Risks / Trade-offs

- **[Risk] One change is large.** → Preserve strict batch ordering, independent batch gates, and task-level `@impl`; do not start credentialed work until deterministic assets pass.
- **[Risk] Scenario abstraction becomes a second framework.** → Keep the model test-owned and minimal, use ordinary pytest parametrization, and reject plugin or DSL dependencies.
- **[Risk] Scripted workflows overfit one model conversation.** → Test invariants and bounded outcome families, include malformed and alternative tool-call sequences, and reserve provider-distribution claims for live scenarios.
- **[Risk] Live CI is flaky or expensive.** → Run short prefixes nightly, bound attempts/cost/time, separate hard failures from quality trends, and keep full-real execution manual/release-only.
- **[Risk] Network denial breaks legitimate local integration.** → Apply it only to the deterministic lane and allow loopback/local subprocess/filesystem behavior explicitly.
- **[Risk] Requirement checker reports superficial coverage.** → Require collected deterministic test node ids and retain scenario/incident mappings for behavioral depth.
- **[Risk] Current unfinished demo change overlaps incident fixes.** → Treat its completed fixes as current behavior, reuse valid tests, and keep its remaining gate-quality issue represented in this change's parser/gate scenarios rather than editing the demo change.

## Migration Plan

1. Batch 1 adds requirements, inventory, adapters, selectors, deterministic CI, and incident regressions while preserving existing commands as compatibility aliases where practical.
2. Batch 2 replaces tautological eval tests with real-seam workflow scenarios and expands mixed-prefix coverage; old tests are removed only after equivalent interface coverage exists.
3. Batch 3 adds live/release runners and workflows, records the first baseline, and documents operator commands and failure interpretation.
4. Run the complete deterministic suite and governance gates after each batch. Rollback is removal of the new test assets, markers, targets, and workflows; no production data or runtime migration exists.
5. After archive, close the four source test-asset plans and the master strategy according to `_backlog/plans/README.md`.

## Open Questions

None. Provider-specific credentials and model names are deployment inputs to the live workflow and do not alter the scenario or test-interface design.
