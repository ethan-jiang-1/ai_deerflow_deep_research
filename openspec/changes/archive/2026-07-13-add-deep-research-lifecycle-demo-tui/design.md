## Context

The archived Change 01 lifecycle already exposes a deterministic in-process memory demo through `agent/scripts/demo.py`. The quickest visual surface is a separate agent-owned Textual application that calls the same `run_deep_research` path and retained `GraphHost`; formal DeerFlow TUI/Web integration is explicitly out of scope.

## Goals / Non-Goals

### Goals

- Launch a zero-API visual walkthrough with `make -C agent demo-tui`.
- Exercise the real start, HITL1 resume, HITL2 decision, cancel, and terminal projection paths.
- Keep the UI thin, deterministic, clearly full-fake, and pilot-testable.

### Non-Goals

- No modification under `backend/` or `frontend/`.
- No `DeerFlowClient`, Gateway, model, network, sandbox research artifact, production TUI, or generic human-input compatibility work.
- No graph, checkpoint schema, fixture-plan, skill, Agent/SOUL, config, mount, or reload-boundary change.

## Decisions

### 1. Agent-owned Textual shell over the existing demo helpers

`agent/scripts/demo_tui.py` will import the existing demo runtime helpers and call `run_deep_research` directly. The Textual app owns only presentation stage, prompt text, and input validation; lifecycle authority remains in the graph/checkpoint.

Alternative: modify DeerFlow's production TUI. Rejected because it expands into embedded-client and generic artifact protocol work and violates the downstream ownership boundary.

### 2. One composer, explicit stage machine

The demo uses one input widget for request, HITL1 text, and HITL2 decision. It renders the advertised HITL2 options and validates the typed choice before constructing the same structured `HumanMessage` used by existing lifecycle tests. A visible cancel button/action invokes lifecycle `cancel` rather than conflating UI interruption with cancellation.

Alternative: build a full card/component framework. Rejected as unnecessary for a demo.

### 3. Optional dependency in the agent lock

Textual is an agent-only optional extra. `make demo-tui` selects that extra; ordinary runtime/test installation remains unchanged.

### 4. Pilot tests are the product gate

Textual's `run_test()` pilot drives the visible happy path and cancel path. Tests also assert the full-fake disclaimer, real request ids, terminal status, and absence of external service requirements.

## Risks / Trade-offs

- [Risk] Users mistake the shell for formal DeerFlow TUI support. → Label the header/footer and docs as standalone demo only.
- [Risk] UI code duplicates lifecycle orchestration from the CLI. → Reuse existing demo helpers and keep only stage wiring in the Textual script.
- [Risk] Optional dependency expands the default environment. → Put Textual behind a dedicated extra selected only by the demo target.

## Migration Plan

Add the optional dependency, demo script, Make target, tests, and documentation. Rollback removes only those agent-owned surfaces; no persisted production data or runtime configuration is migrated.

## Open Questions

None. Formal DeerFlow TUI/Web human-input compatibility remains a separate backlog item.
