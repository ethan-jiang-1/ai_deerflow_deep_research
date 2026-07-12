## Why

Change 00 established and archived the trusted runtime substrate, generic `GraphHost`
action registry, isolated checkpoint namespaces, runtime projection, reflected
`deerflow_deep_research.tool:deep_research_tool`, and file-SQLite restart durability.
The repository still has no research topology, lifecycle actions, graph-owned HITL, or
per-phase node packages. Implementing real research behavior before those contracts
exist would make every later node change redefine routing, persistence, and resume
semantics independently.

This change creates the complete Deep Research control-flow skeleton with deterministic
fakes. It proves the graph can start, suspend twice for human input, resume after a
process restart, repair, rerun, stop, cancel, and finish before any LLM, web, or research
filesystem behavior is introduced.

## What Changes

- Add one explicit top-level topology for `bootstrap`, `hitl1`, `topic_planning`,
  `wave0`, `wave1`, `wave2_synthesis`, `targeted_evidence`, `hitl2`, `rerun`,
  `readiness`, and `final_delivery`, with typed routers for pass, repair, rerun, stop,
  and completion edges.
- Add the canonical `graph/nodes/<phase>/` packages and public `NODE_SPEC` surfaces.
  Every package keeps a permanent deterministic fake implementation. Real selection
  fails closed until the later change that owns that node supplies an implementation;
  mixed-mode tests may inject an explicit test implementation without changing the
  topology.
- Add a request-independent graph recipe plus an implementation map. Runtime-scoped
  `GraphContextView` and a runtime-owned reduced dependency resolver are passed through
  non-checkpointed LangGraph invocation context. The resolver creates the correct
  per-node/per-attempt `NodeBuildDependencies` when a node actually runs; no
  `TrustedRuntimeEnvelope`, sandbox handle, host path, AppConfig, or checkpointer
  identity enters graph state.
- Add a minimal, versioned skeleton state containing only lifecycle status, stable
  start-message correlation/digest, phase/generation counters, validated deterministic
  fixture controls, fan-out results, pending HITL correlation, consumed response ids,
  and a bounded execution trace. Full `ResearchState`, evidence, work-unit,
  submission-ledger, and delivery schemas remain owned by changes 02 and later.
- Add deterministic Wave0/Wave1 `Send` fan-out and reducer-based fan-in fixtures, plus
  repair and rerun loops with explicit bounded counters.
- Add graph-owned HITL1/HITL2 interrupts. A suspended action returns an outer
  `ToolMessage` with the existing `artifact.human_input` version-1 request payload and
  ends the current lead-agent turn. Resume accepts no answer in the tool arguments: it
  reads the latest actual `HumanMessage` from trusted runtime state, requires matching
  `human_input_response.source` and `request_id` metadata when present, binds it to the
  one pending graph interrupt, and rejects stale, replayed, cross-thread, or mismatched
  responses. The response value originates from that `HumanMessage`, never a model
  supplied control-tool field.
- Extend the reflected tool and generic host registration with typed `start`, `resume`,
  `status`, and `cancel` handlers while preserving the independent `infra_probe`
  topology and namespace. `start` accepts no caller-selected id or question: it binds
  the latest eligible real `HumanMessage`, then derives a collision-resistant opaque
  research id from trusted user/thread scope plus that stable message id. Retrying the
  same start after a failure therefore reopens or reprojects the same lifecycle instead
  of orphaning a randomly named checkpoint. Subsequent actions require the returned id
  but still derive authority from trusted user/thread context. `cancel` is a durable
  terminal transition for a checkpointed research lifecycle; cancellation of an
  actively executing outer tool task continues to use DeerFlow/asyncio cancellation
  from change 00 rather than a second run-control system.
- Define one bounded version-1 control-result envelope for suspended, running,
  completed, stopped, cancelled, unavailable, and denied outcomes. A suspended
  `ToolMessage` carries the same envelope as text fallback plus the human-input
  artifact, so the lead agent can reliably retain the opaque research id and request
  id without parsing UI prose.
- Add deterministic topology snapshots and zero-API E2E paths for happy completion,
  Wave0/Wave1 repair, targeted-evidence convergence, every HITL2 decision
  (`proceed | revise_view | repair | rerun | stop`), readiness/final repair,
  cancellation, invalid/replayed resume, idempotent start-result reprojection, and
  file-SQLite process-restart resume. Memory remains explicitly same-process only.
- Update the committed public entry skill and dedicated Agent/SOUL guidance to describe
  the newly available lifecycle actions without moving graph logic into prompts.

The new requirement IDs are `RUI-006` and `REG-001` through `REG-005`.

## Capabilities

### New Capabilities

- `research-graph-lifecycle`: Complete deterministic topology, implementation mapping,
  fake parallelism, graph-owned HITL, typed lifecycle actions, restart recovery,
  topology snapshots, and zero-API E2E behavior.

### Modified Capabilities

- `runtime-integration`: The existing reflected control tool advances from an
  infrastructure-probe-only surface to action-specific research lifecycle dispatch
  while retaining the probe as an isolated diagnostic action.

## Impact

- **Downstream source:** additive work under
  `agent/src/deerflow_deep_research/{domain,graph,runtime}/`, including topology,
  routing, implementation mapping, lifecycle handlers, minimal skeleton contracts, and
  the eleven canonical node packages. `tool.py` evolves to an action-discriminated
  strict schema and may return a public LangGraph `Command` containing a `ToolMessage`
  for HITL suspension.
- **Tests and governance:** new agent-owned unit, contract, graph, integration, E2E,
  topology snapshot, restart-subprocess, reflected-command viability, and requirement
  traceability coverage. No real LLM or network API is used.
- **Checkpoint data:** one new versioned research namespace and minimal skeleton-state
  schema, including only an opaque start-message reference/digest rather than raw
  runtime authority. The existing infra-probe topology, checkpoint namespace, and
  durability behavior are unchanged.
- **Sandbox data:** runtime projection derives the canonical research root, but fake
  nodes do not call sandbox research tools and write no evidence, cache, ledger, or
  report artifacts. Large business data remains out of checkpoints.
- **Node-agent roles:** none in this change. Every fake is a deterministic graph node;
  the bounded embedded-agent bridge remains unused until a real-node change.
- **DeerFlow extension surfaces:** `config.yaml -> tools[name=deep_research].use` remains
  `deerflow_deep_research.tool:deep_research_tool`; the existing
  `tool_groups[name=deep-research-control]`,
  `extensions_config.json -> skills.deep-research-controller.enabled`,
  `skills/public/deep-research-controller/SKILL.md`, and per-user
  `{DEER_FLOW_HOME}/users/{user_id}/agents/deep-research/{config.yaml,SOUL.md}` remain
  the only entry surfaces. MCP, ACP, DeerFlow `task` subagents, phase skills, and DPT
  bundle control files are not used.
- **Reload boundary:** public skill, Agent/SOUL, and reflected tool description changes
  take effect on the next agent build. Python package code requires the normal Gateway
  restart/source reload already established by change 00. No `config.yaml` startup-only
  field, mount, database/checkpointer, sandbox, worker-count, or launcher behavior is
  changed, so this change introduces no new `reload_boundary.STARTUP_ONLY_FIELDS`
  impact.
- **Non-goals:** no real research node, model call, web access, evidence/work-unit/
  submission ledger, report artifact, progress UI optimization, launcher, Docker live
  smoke, Postgres profile, multi-worker coordination, or modification under `backend/`
  or `frontend/`. Any upstream change is a separate BREAKING escalation.
