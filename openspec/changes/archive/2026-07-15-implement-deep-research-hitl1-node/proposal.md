## Why

The HITL1 node is still the change-01 fake: its interrupt presents a hardcoded fixture
message and accepts any text as if it were a valid profile. Every later real phase
(topic planning, research waves, synthesis, HITL2) depends on HITL1 having *actually*
collected a structured research profile — depth, audience, scope boundaries,
must-answer questions, and cost/time preferences — that the topic planner and workers
can use as a constraint envelope. Without a real HITL1, topic planning cannot
generate well-scoped topics, and the research waves cannot target their depth or
format to the user's needs. This change upgrades HITL1 to the first real
model-calling node while preserving the existing interrupt/resume wire protocol and
full-fake path.

## What Changes

- Replace the fake HITL1 fixture message with an LLM-generated structured brief
  draft that proposes a research profile (depth, audience, format, scope, must-answer
  questions, cost/time preferences) derived from the original question, using
  `capabilities.run_agent()` — the same injected agent capability used by research
  workers. The LLM prompt constrains the agent to produce a structured output with
  closed-enum values; the model cannot invent new enum members or silently substitute
  user-supplied values.
- Add a frozen `ResearchProfile` contract and a closed-enum `ProfileDimension`
  model (`ResearchDepth`, `TargetAudience`, `OutputFormat`, `CostTolerance`,
  `TimeBudget`) to the domain layer. The final recorded profile is the only persistent
  HITL1 request artifact written to the sandbox as a `ContentRef` and to a new
  `profile_ref` checkpoint field; the raw profile values also enter the checkpoint as
  short enum strings so the topic planner can read them without a sandbox round-trip.
- Present the structured brief plus profile dimensions to the user through the
  existing `interrupt(PendingResearchInterrupt(…))` mechanism with `mode=TEXT`;
  a schema-versioned `HumanInputRequest.context` carries the LLM-generated brief
  and dimension options as structured JSON so the frontend can render them.
- Parse and validate the human text response against the profile dimension enums
  and the must-answer question list. On an incomplete or ambiguous answer, write a
  bounded partial-profile progress field to `ResearchState`, route
  `needs_followup -> hitl1`, and issue a follow-up interrupt with an incremented
  ordinal asking only for the missing fields. This is restart-durable; no Python
  closure state is used as authority.
- Write the validated `ResearchProfile` to a request-bundle `profile.json` through
  a runtime-owned narrow write capability, return a `ContentRef`, and update
  `profile_ref` plus short enum-string checkpoint fields atomically with the
  `accepted → topic_planning` route. The cancel route and `InternalCancelDecision`
  handling are unchanged from the fake.
- Carry the structured brief in the HITL context and record the final profile in the
  research bundle under the `request/` subtree (alongside the bootstrap marker) so the
  bundle is self-describing for later phases and diagnostics.
- Swap the real HITL1 into the mixed implementation map in place of the fake while
  every other non-bootstrap phase remains fake. Add explicit HITL1 conditional edges
  for `needs_followup -> hitl1` and `exhausted -> blocked/END`; keep existing
  `accepted` and `cancel` routes and preserve the full-fake lifecycle end-to-end
  path. The lifecycle result remains `implementation_mode=full_fake` because HITL1
  produces no research findings or report.
- `backend/` and `frontend/` are not modified.

## Capabilities

### New Capabilities

- `hitl1-node`: Real HITL1 node behavior — LLM-generated structured brief from the
  original question with closed-enum profile dimensions, user-facing interrupt
  carrying the brief and dimension options, parse/validate of the human response
  with restart-durable re-entrant follow-up on incomplete answers, profile storage as
  request-bundle `profile.json` plus a checkpoint `ContentRef` and short fields, and
  explicit `accepted`/`cancel`/`needs_followup`/`exhausted` routes. Requirement IDs:
  HIN-001 through HIN-005.

### Modified Capabilities

- `research-graph-lifecycle`: add the two real-HITL1-only route labels
  `needs_followup` and `exhausted` to the normalized topology and builder while
  preserving the full-fake route behavior, start/resume/status/cancel semantics
  (REG-004), and the existing HITL wire protocol; extend the typed checkpoint,
  reducer ownership, ContentRef, three-authority, request-bundle path, and version-2
  compatibility contracts for the new HITL1 profile fields and `request/profile.json`
  artifact (REG-006 through REG-011).
- `project-structure`: permit a real graph-owned HITL node module, not only a HITL
  fake, to import exactly public `langgraph.types.interrupt`; register new production
  paths and the request-bundle capability surface through the PRS-004 mechanical sync.

The `PendingResearchInterrupt`, `AcceptedHumanResponse`, and
`InternalCancelDecision` wire schemas remain unchanged. Identity derivation and
scope checks remain owned by REG-004/RUI; the request-bundle write reuses REG-010 path
containment and exposes only a pure protocol to graph nodes.

## Impact

- **Source:** add a frozen `ResearchProfile` contract and closed-enum
  `ProfileDimension` types under `agent/src/deerflow_deep_research/domain/profile.py`;
  add an LLM-prompt template for structured-brief generation under
  `agent/src/deerflow_deep_research/graph/nodes/hitl1/prompts.py`; replace the
  `UNAVAILABLE_REAL_FACTORY` sentinel in `graph/nodes/hitl1/node.py` with the real
  factory that calls `capabilities.run_agent()` and performs the
  interrupt/parse/validate/store cycle; extend `graph/nodes/hitl1/contracts.py`
  with the route and context contracts; add request-profile path helpers under
  `domain/bundle.py`; add a narrow request-bundle write protocol to the domain
  capability surface and a runtime implementation in
  `agent/src/deerflow_deep_research/runtime/request_bundle.py` that writes
  `profile.json` under the established bundle's `request/` subtree; wire
  `RuntimeNodeAgentBridge` and the
  request-bundle writer only for the mixed real-HITL1 recipe; add `profile_ref`, short
  enum-string profile fields, and bounded transient `pending_profile` /
  `profile_followup_round` fields to `ResearchState`/`ResearchCheckpoint`. The new
  files and capability surfaces are registered in the canonical project-structure
  registry and generated `agent/AGENTS.md` block via the existing PRS-004 mechanical
  sync. No new `NodeCapability` member is needed for brief generation; the request
  bundle writer is a narrow runtime capability declared and attached only for real
  HITL1.
- **Typed state/checkpoint data affected:** a new `profile_ref: ContentRef | None`
  and short enum-string fields (`research_depth`, `target_audience`, `output_format`,
  `cost_tolerance`, `time_budget`, `must_answer_questions: tuple[str, ...]`,
  `degraded_profile: bool`) plus transient `pending_profile` and
  `profile_followup_round` are added to `ResearchState`/`ResearchCheckpoint` under
  `WriterRole.CONTROLLER` ownership. `RESEARCH_STATE_SCHEMA_VERSION` is **not bumped**
  because all new fields default to `None`/empty/false and are backward-compatible
  with existing version-2 checkpoints. Large content (the serialized final profile)
  stays in the sandbox via `ContentRef`; only short enum strings, durable progress,
  and refs enter the checkpoint.
- **Graph nodes/components affected:** only `hitl1` swaps from fake to real in the
  mixed graph; every other phase remains fake. HITL1 stays a non-gated control node;
  the real node calls `run_agent` for brief generation, performs inline profile
  validation, and sets the route directly. The normalized topology gains exactly
  `hitl1 --needs_followup--> hitl1` and `hitl1 --exhausted--> blocked/END`; existing
  `hitl1 --accepted--> topic_planning` and `hitl1 --cancel--> cancelled` remain
  unchanged. Targeted evidence and rerun are not implemented here.
- **Node-agent roles used:** HITL1 calls `capabilities.run_agent()` exactly once
  per brief generation attempt, with at most one repair attempt after schema-invalid
  model output. Each bridge invocation is a bounded one-model-call request with a
  constrained output schema and a zero-tool policy; it performs no web search, MCP,
  ACP, or DeerFlow `task` subagent call. The agent cannot write the profile to the
  checkpoint, set the route, or advance the phase. Planners, workers, and repair roles
  are unchanged.
- **Sandbox artifacts read/written:** the HITL1 node reads the bootstrap marker
  only if needed for binding confirmation and writes `profile.json` under the
  canonical `request/` subtree via the request-bundle write capability. No evidence
  ledger, work-spec, result, or DPT queue/index/status bundle file is created.
- **DeerFlow extension surfaces:** the existing downstream reflection path
  `deerflow_deep_research.tool:deep_research_tool` and registered lifecycle
  handlers are unchanged. No `config.yaml` section, `extensions_config.json` key,
  public/custom skill, per-user Agent/SOUL, MCP, ACP, or lead-agent middleware
  surface is added or modified.
- **Diagnostics:** no new `ReadinessDiagnostic` dimension. HITL1 depends on the
  existing runtime node-agent bridge for brief generation and the new narrow
  request-bundle writer for `profile.json`; both are bound only for real HITL1 start
  or resume actions. `hitl1=real` is valid only with `bootstrap=real`, because the
  request-bundle writer must bind to the established bootstrap bundle root.
- **Reload boundary:** no runtime configuration, mount, or
  `reload_boundary.STARTUP_ONLY_FIELDS` value changes. Source changes are
  available on the next agent build; a running non-reload Gateway must be
  restarted/redeployed to import new Python source, but there is no additional
  configuration-mandated restart.
- **Dependencies:** no new third-party runtime dependency. The LLM call uses the
  existing `capabilities.run_agent()` bridge already available through the node
  wrapper and runtime projection.
- **Non-goals:** no topic generation or search execution; no HITL2 or scheduled
  auto-proceed; no modification to the LangGraph interrupt mechanism or the
  `PendingResearchInterrupt`/`AcceptedHumanResponse` wire format; no real research
  worker, source fetching, findings, or report generation. No files under
  `backend/` or `frontend/` are modified.

New requirement IDs are HIN-001 through HIN-005 (`hitl1-node`). Existing REG and PRS
requirements are modified narrowly to add HITL1 follow-up/blocked route labels, profile
state and request-bundle authority, version-2 compatibility, and the real-HITL import
exception; supporting files are registered through the existing PRS-004 registry sync.
