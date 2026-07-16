## Context

Change 08 delivered real Wave0 source intake with validated `SubmissionRecord`s. Change 09 added SourceDiagnostic and ClaimVerifier critics. Change 10 builds on both: Wave1 performs deep per-topic evidence extraction, searching for new sources beyond Wave0's baseline, extracting structured claims with provenance, running critics on the output, and enforcing a higher coverage floor.

Wave1 already has the topology position: `wave0 --pass--> wave1`, gated with `repair`/`pass`/`exhausted`. Its real factory is `UNAVAILABLE_REAL_FACTORY`.

The shared work-unit component handles fan-out/fan-in/submit/drain. The Wave0 worker pattern (prompt → run_agent → parse → materialize) is reused. The critic dispatch pattern (change 09) is reused for post-submit validation.

## Goals / Non-Goals

**Goals:**
- Materialize per-topic evidence WorkSpecs from the planner, gated by profile constraints and Wave0 background coverage.
- Run bounded web workers that search/fetch new sources, extract claims with support/counter refs, record open questions, and mark `is_new_vs_wave0`.
- Enforce new-source floor at submit-validation: Wave0-duplicate URLs do not count.
- Run SourceDiagnostic and ClaimVerifier on accepted Wave1 submissions, producing verdict artifacts the gate consumes.
- Implement a real Wave1 gate: hard provenance (all work drained, per-topic new-source floor), semantic coverage (critic verdicts present, no fatal contradictions), and open-question resolution.
- Integrate real Wave1 into the mixed graph requiring the full real chain through wave0 and critics. Topology and full-fake path unchanged.

**Non-Goals:**
- No cross-topic synthesis or targeted Wave2 search.
- No final report writing.
- No modification to `backend/` or `frontend/`.
- Wave1 sources do not auto-satisfy Wave2's new-source floor.

## Decisions

### Decision 1: Reuse shared work-unit component with real intents and worker

Same pattern as Wave0: the real Wave1 factory drives `run_work_unit_component` with per-topic intents materialized from profile constraints + Wave0 background, and a real worker that calls `capabilities.run_agent()`.

### Decision 2: Worker produces structured output with provenance

The Wave1 worker produces `Wave1WorkerOutput`: claims (each with `claim_id`, `statement`, `support_refs`, `counter_refs`), open questions (with resolution states), and per-source `is_new_vs_wave0` marking. The output schema is versioned (`schema_version=1`).

### Decision 3: Submit validation enforces new-source floor

The submit validator canonicalizes URLs, deduplicates per topic, and rejects candidates where `is_new_vs_wave0` sources fall below the floor. Wave0-duplicate URLs are tracked via URL set comparison. After submit, critics are invoked on the accepted evidence.

### Decision 4: Gate consumes critic verdicts

The Wave1 gate reads critic artifacts produced post-submit and enforces: all planned work drained, per-topic new-source floor met, critic verdicts present, no fatal contradictions. This is the first gate to consume critic output (changes 08/09 prepared the contracts).

### Decision 5: Repair loop with bounded retry

Repair re-executes only topics lacking coverage, with a per-phase budget. Workers can be re-invoked with adjusted search dimensions. Failed repair exhausts to terminal `blocked`.

### Decision 6: Mixed-graph dependency chain

Real Wave1 requires `bootstrap=real`, `hitl1=real`, `topic_planning=real`, `wave0=real`, and `targeted_evidence=real`. Selecting `wave1=real` without the full chain fails before graph invocation.

## Risks / Trade-offs

- **Live web search is non-deterministic**: all tests use replay/fake tools.
- **Critic invocation adds latency**: post-submit critic dispatch is sequential per work item. Acceptable because critics are bounded single-call agents.
- **New-source floor may be hard to meet**: repair loop with bounded budget handles this; exhausted topics produce a terminal blocked route.

## Open Questions

- Exact new-source floor threshold (N independent new sources). Default to 2; configurable in a later change.
- Whether to cache critic verdicts in checkpoint state or derive from sandbox. Deferred; reads from sandbox for now.
