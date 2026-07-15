## Why

Topic planning is still the change-01 fake: `topic_planning/node.py` is the
`UNAVAILABLE_REAL_FACTORY` sentinel and its fake returns a hardcoded
`route="next"` that ignores the research profile entirely. Every later research
phase depends on topic planning having *actually* decomposed the confirmed
profile into a stable topic registry and a must-answer coverage map that Wave0
can target. Without a real topic planner, Wave0 (change 08) cannot generate
well-scoped source-intake work, and the research waves cannot bound their depth,
audience, or format to what HITL1 collected. This change upgrades topic planning
to a real model-calling node while preserving the existing full-fake path and the
established three-authority boundary.

## What Changes

- Replace the fake/sentinel topic planner with an LLM-generated structured topic
  plan derived from the checkpointed HITL1 profile constraints
  (`research_depth`, `target_audience`, `output_format`, `cost_tolerance`,
  `time_budget`, `must_answer_questions`, `degraded_profile`), produced through
  `capabilities.run_agent()` — the same injected agent capability used by HITL1.
  The prompt constrains the agent to one structured-output object; the model
  cannot invent topic ids, author the registry format, or mutate state.
- Add frozen closed topic contracts under `domain/topics.py`
  (`TopicPlan`/`ResearchTopic` with stable id/slug/title/scope, must-answer
  bindings, search dimensions, and exclusions) and an LLM-prompt template under
  `graph/nodes/topic_planning/prompts.py`. Topic ids/slugs are derived
  deterministically from validated content, never copied verbatim from model
  output.
- Add a deterministic materializer that normalizes the validated plan into a
  stable, bounded topic registry and a must-answer coverage map, and enforces
  hard checks: duplicate/overlapping topics, empty coverage, over-expansion, and
  must-answer coverage of the root questions. The LLM never authors the registry
  serialization.
- On validation failure, re-prompt the planner once with failure metadata; on a
  second failure or `run_agent` error, fail closed to a terminal `blocked` route
  before Wave0. topic_planning stays a non-gated controller node (like bootstrap
  and HITL1) and writes its own route directly.
- Record the validated topic registry as bounded planner-owned checkpoint state
  (extending the planning block; reusing `topic_refs`) so Wave0 can read it
  without a sandbox round-trip. topic_planning reads profile constraints from
  checkpoint short fields only — it does **not** read `request/profile.json`,
  does **not** declare `REQUEST_BUNDLE` or `WORK_UNIT_CONTROLLER`, produces no
  `WorkSpec`, and writes no sandbox file. `RESEARCH_STATE_SCHEMA_VERSION` is not
  bumped.
- Swap real topic planning into the mixed implementation map. Add exactly one
  new topology route `topic_planning --exhausted--> blocked/END` (converting the
  current direct `topic_planning -> wave0` edge to conditional
  `{next: wave0, exhausted: END}`); keep existing inbound edges unchanged and
  preserve the full-fake lifecycle. The lifecycle result remains
  `implementation_mode=full_fake`.
- `backend/` and `frontend/` are not modified.

## Capabilities

### New Capabilities

- `topic-planning-node`: Real topic planning node behavior — LLM-generated
  structured topic plan from the checkpointed profile via the runtime node-agent
  bridge with closed topic contracts and fail-closed validation, a deterministic
  materializer with topic-id/slug stability plus coverage/overlap hard checks,
  bounded inline repair, bounded planner-owned checkpoint topic state read from
  checkpoint profile fields, and explicit `next`/`exhausted` routes. Requirement
  IDs: TOP-001 through TOP-005.

### Modified Capabilities

- `research-graph-lifecycle`: add the real-topic-planning-only `exhausted` route
  label to the normalized topology and builder while preserving full-fake route
  behavior and start/resume/status/cancel semantics; require real topic planning
  to chain off real HITL1 (which already requires real bootstrap); extend the
  typed checkpoint, reducer ownership, and planner-authority contracts for
  bounded topic registry/coverage fields (version-2 compatible).
- `project-structure`: register the new production paths
  `domain/topics.py` and `graph/nodes/topic_planning/prompts.py` through the
  PRS-004 mechanical sync. No import-policy change is needed because
  topic_planning is not a HITL node and imports only `domain`/`engine`.

The `PendingResearchInterrupt`/`AcceptedHumanResponse` wire schemas, the
`deep_research_tool` reflection path, identity derivation, and the request-bundle
profile writer are unchanged. topic_planning does not interrupt.

## Impact

- **Source:** add frozen topic contracts under
  `agent/src/deerflow_deep_research/domain/topics.py`; add the planner prompt
  template under `agent/src/deerflow_deep_research/graph/nodes/topic_planning/prompts.py`;
  replace the `UNAVAILABLE_REAL_FACTORY` sentinel in
  `graph/nodes/topic_planning/node.py` with the real factory that calls
  `capabilities.run_agent()`, validates/materializes the plan, and sets the
  route; extend `graph/nodes/topic_planning/contracts.py` with the result
  routes. The new files are registered in the canonical project-structure
  registry and generated `agent/AGENTS.md` block via the existing PRS-004 sync.
- **Typed state/checkpoint data affected:** bounded planner-owned topic data is
  added to `ResearchState`/`ResearchCheckpoint` under `WriterRole.PLANNER`
  ownership (a topic registry/coverage structure and refs; `topic_refs` is
  reused). These fields default to empty and are backward-compatible with
  version-2 checkpoints, so `RESEARCH_STATE_SCHEMA_VERSION` is **not bumped**.
  topic_planning reads the existing controller-owned profile short fields; it
  adds no raw runtime capability or large content to the checkpoint.
- **Graph nodes/components affected:** only `topic_planning` swaps from
  fake/sentinel to real in the mixed graph; every other phase remains fake.
  topic_planning stays a non-gated controller node that writes its own route.
  The normalized topology gains exactly `topic_planning --exhausted--> blocked`;
  existing `bootstrap/hitl1 -> topic_planning`, `topic_planning --next--> wave0`,
  and `rerun -> topic_planning` edges remain unchanged.
- **Node-agent roles used:** topic_planning calls `capabilities.run_agent()`
  exactly once per planning attempt, with at most one repair attempt after
  schema/coverage-invalid output. Each bridge invocation is a bounded
  one-model-call request with a constrained output schema and a zero-tool
  policy; it performs no web search, MCP, ACP, file read, or DeerFlow `task`
  subagent call. The agent cannot write checkpoint state, set the route,
  advance the phase, or produce `WorkSpec`.
- **Sandbox artifacts read/written:** none. topic_planning reads profile
  constraints from checkpoint short fields and writes bounded planner-owned
  checkpoint state. It does not read `request/profile.json` or the bootstrap
  marker, and creates no topic/seed/evidence/work/ledger file. Persisting
  topics as sandbox files for later phases is deferred to change 08.
- **DeerFlow extension surfaces:** the existing downstream reflection path
  `deerflow_deep_research.tool:deep_research_tool` and registered lifecycle
  handlers are unchanged. No `config.yaml` section, `extensions_config.json`
  key, public/custom skill, per-user Agent/SOUL, MCP, ACP, or lead-agent
  middleware surface is added or modified.
- **Diagnostics:** no new `ReadinessDiagnostic` dimension. Real topic planning
  depends on the existing runtime node-agent bridge; `topic_planning=real` is
  valid only with `bootstrap=real` and `hitl1=real`, because the planner consumes
  the real HITL1 profile constraints.
- **Reload boundary:** no runtime configuration, mount, or
  `reload_boundary.STARTUP_ONLY_FIELDS` value changes. Source changes are
  available on the next agent build; a running non-reload Gateway must be
  restarted/redeployed to import new Python source, but there is no additional
  configuration-mandated restart.
- **Dependencies:** no new third-party runtime dependency. The LLM call uses the
  existing `capabilities.run_agent()` bridge already available through the node
  wrapper and runtime projection.
- **Non-goals:** no Wave0 `WorkSpec` generation or source search (change 08);
  no rerun diff/invalidation planning (change 14); no HITL interrupt (topic
  planning never suspends); no real research worker, findings, or report; no
  topic artifacts written to the sandbox. No files under `backend/` or
  `frontend/` are modified.

New requirement IDs are TOP-001 through TOP-005 (`topic-planning-node`). Existing
REG and PRS requirements are modified narrowly to add the topic-planning
`exhausted` route, planner-owned topic checkpoint authority, and version-2
compatibility; supporting files are registered through the existing PRS-004
registry sync.
