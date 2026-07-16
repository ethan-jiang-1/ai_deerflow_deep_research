## Context

Change 18 is the release gate — it adds evaluation infrastructure without modifying the graph. All tests are zero-API deterministic (FakeToolCallingModel/ReplayChatModel). Real-LLM tests are marked `@requires_llm` and are optional in CI.

## Goals / Non-Goals

**Goals:** eval corpus framework, quality metrics, fault injection, adversarial tests, release gate.
**Non-Goals:** no new graph phases, no backend/frontend changes.

## Decisions

### Decision 1: Eval corpus uses replay fixtures

Each eval case is a Python function that sets up a `ResearchState` fixture, runs the graph with `FakeToolCallingModel`, and asserts on the output. Cases live in `tests/eval/` and are importable as a pytest module. This follows the existing `test_topology_and_implementation.py` pattern.

### Decision 2: Metrics are pure functions on state

`compute_citation_precision(state)`, `compute_must_answer_coverage(state)`, `compute_source_diversity(state)` — pure Python, no model, no I/O. They read `accepted_submission_refs`, `must_answer_questions`, and `topic_registry` from state.

### Decision 3: Fault injection uses `FakeToolCallingModel` with injected failures

Crash → raise mid-node. Timeout → `asyncio.wait_for`. Cancel → `InternalCancelDecision`. Duplicate resume → replay same HITL response twice. Each fault has an expected outcome (recovery or terminal state).

### Decision 4: Adversarial test injects prompt-injected content

A `ReplayChatModel` returns content containing instructions like "set route=stop" or "write to ledger." The test verifies these instructions have zero effect on control flow.

### Decision 5: Release gate is a pytest marker convention

`@pytest.mark.release_gate` — deterministic tests that MUST pass. `@pytest.mark.requires_llm` — optional canary tests. CI runs release_gate tests; `requires_llm` tests run on a schedule or manually.

## Risks

- **[Risk] Eval corpus may be too small for statistical significance.** → Mitigation: the framework supports adding cases. Start with 5 representative cases; expand based on findings.
- **[Risk] Fault injection may expose bugs requiring changes to earlier nodes.** → Per plan: "发现结构缺口时回到对应 plan/change 修复" — this is expected and valuable.

## Open Questions

- DPT parity audit scope. Start with the invariant list from the master plan; document achieved vs outstanding per invariant.
