## Why

The Deep Research real-mode demo exposed thirteen failures only after expensive full-pipeline runs even though the fake graph and existing tests passed. The project now needs one executable testing and evaluation capability that moves deterministic failures to stable seams, exercises real agent workflows without external APIs, and reserves live-model and full-real runs for behavior and release acceptance.

## What Changes

- Establish one three-batch testing control plane for code correctness, deterministic agent-workflow conformance, and live/release evaluation, using `_backlog/plans/deep-research-test-assets-master-strategy.md` as the approved design input.
- Audit the current suite against the thirteen real-mode incident classes, add only missing deterministic regressions, and expose stable `make` targets and an agent-owned PR workflow that never requires network or model credentials.
- Define reusable typed scenarios and test adapters for trusted runtime context, local mounted sandbox/filesystem behavior, scripted model/tool conversations, unique run identity, redacted diagnostics, and fault injection.
- Exercise each real node and each high-risk real-prefix workflow through real graph, runtime bridge, middleware, policy, budget, parser, submission, gate, checkpoint, and artifact code while replacing only true external model/tool dependencies.
- Add short `@requires_llm` live canaries and a full-real release-acceptance lane with explicit hard invariants, reported quality metrics, unique identities, observable retries, and deterministic-regression follow-up for every newly discovered failure.
- Add requirement-to-test traceability and stable selection semantics so deterministic PR tests, live nightly evaluation, and release E2E cannot silently collapse into one ambiguous suite.
- Keep `backend/` and `frontend/` unchanged. No production topology, checkpoint schema, sandbox artifact layout, runtime configuration, model/tool configuration, public/custom skill, per-user Agent/SOUL, MCP, ACP, DeerFlow task subagent, or downstream reflection path is added or changed. A live/release defect may receive the smallest production fix already required by an existing capability spec after a red deterministic regression is added at the lowest stable seam; this exception does not authorize new product behavior or layout. Existing test entrypoints under `agent/` and repository GitHub workflows remain the only new operational surfaces; no next-agent-build or Gateway restart is required.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `evaluation-hardening`: modify `EVH-001` through `EVH-005` and add `EVH-006` through `EVH-010`, deepening the existing replay corpus, metrics, fault-injection, adversarial-source, and release-gate requirements into a three-batch testing strategy covering incident closure, deterministic agent workflows, live canaries, full-real acceptance, and requirement-to-test traceability.

## Impact

- Test and evaluation assets under `agent/tests/`, including shared fixtures and scenario corpus data.
- `agent/Makefile`, `agent/pyproject.toml`, `agent/README.md`, and `agent/AGENTS.md` for stable commands, markers, and development rules.
- Agent-owned GitHub Actions workflows for deterministic PR, scheduled live, and manual/release execution.
- OpenSpec evaluation-hardening requirements and governance registry/checker coverage.
- No new runtime dependency, production API, graph node, state field, sandbox path, model/tool role, or deployment configuration. Narrow conformance fixes may make an existing production node materialize an artifact already required at its canonical path.
