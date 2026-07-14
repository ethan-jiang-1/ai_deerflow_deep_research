## Why

The HITL1 node is still the change-01 fake: its interrupt presents a hardcoded fixture
message and accepts any text as if it were a valid profile. Every later real phase
(topic planning, research waves, synthesis, HITL2) depends on HITL1 having *actually*
collected a structured research profile — depth, audience, scope boundaries,
must-answer questions, and cost/time preferences — that the topic planner and workers
can use as a constraint envelope. Without a real HITL1, topic planning cannot
generate well-scoped topics, and the research waves cannot target their depth or
format to the user's needs. This change upgrades only the HITL1 node to real; the
interrupt/resume protocol and the `accepted`/`cancel` routes are unchanged.

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
  `TimeBudget`) to the domain layer. The profile is the sole HITL1 artifact written
  to the sandbox as a `ContentRef` and to a new `profile_ref` checkpoint field; the
  raw profile values also enter the checkpoint as short enum strings so the topic
  planner can read them without a sandbox round-trip.
- Present the structured brief plus profile dimensions to the user through the
  existing `interrupt(PendingResearchInterrupt(…))` mechanism with `mode=TEXT`;
  a schema-versioned `HumanInputRequest.context` carries the LLM-generated brief
  and dimension options as structured JSON so the frontend can render them.
- Parse and validate the human text response against the profile dimension enums
  and the must-answer question list. On an incomplete or ambiguous answer, generate
  a follow-up interrupt on the same checkpoint (re-entrant HITL1 with the same
  `request_id` and an incremented ordinal) asking only for the missing fields.
- Write the validated `ResearchProfile` to a sandbox `ContentRef` and to the
  checkpointed `profile_ref` plus short enum-string fields, then route
  `accepted → topic_planning`. The cancel route and `InternalCancelDecision`
  handling are unchanged from the fake.
- Record the structured brief and final profile in the research bundle under the
  `request/` subtree (alongside the bootstrap marker) so the bundle is
  self-describing for later phases and diagnostics.
- Swap the real HITL1 into the mixed implementation map in place of the fake while
  every other non-bootstrap phase remains fake, preserving the normalized topology
  and the full-fake lifecycle end-to-end path. The lifecycle result remains
  `implementation_mode=full_fake` because HITL1 produces no research findings or
  report.
- `backend/` and `frontend/` are not modified.

## Capabilities

### New Capabilities

- `hitl1-node`: Real HITL1 node behavior — LLM-generated structured brief from the
  original question with closed-enum profile dimensions, user-facing interrupt
  carrying the brief and dimension options, parse/validate of the human response
  with re-entrant follow-up on incomplete answers, profile storage as a sandbox
  `ContentRef` plus short checkpoint fields, and the `accepted`/`cancel` routes
  into the existing topology. Requirement IDs: HIN-001 through HIN-005.

### Modified Capabilities

None. The new supporting files are registered in the canonical project-structure
registry and the generated `agent/AGENTS.md` block through the existing PRS-004
mechanical sync; no `project-structure`, `research-graph-lifecycle`, `gate-kernel`,
or `work-unit-kernel` requirement text changes. Identity derivation and
start/resume/status/cancel semantics (REG-004), the bundle layout and
path-containment contract (REG-010), and the interrupt/resume wire protocol
(`PendingResearchInterrupt`, `AcceptedHumanResponse`, `InternalCancelDecision`)
are unchanged.

## Impact

- **Source:** add a frozen `ResearchProfile` contract and closed-enum
  `ProfileDimension` types under `agent/src/deerflow_deep_research/domain/profile.py`;
  add an LLM-prompt template for structured-brief generation under
  `agent/src/deerflow_deep_research/graph/nodes/hitl1/prompts.py`; replace the
  `UNAVAILABLE_REAL_FACTORY` sentinel in `graph/nodes/hitl1/node.py` with the real
  factory that calls `capabilities.run_agent()` and performs the
  interrupt/parse/validate/store cycle; extend `graph/nodes/hitl1/contracts.py`
  with the profile dimensions carried in the `HumanInputRequest.context`; add a
  `profile_ref: ContentRef` and short enum-string profile fields to
  `ResearchState`/`ResearchCheckpoint`. The new files are registered in the
  canonical project-structure registry and the generated `agent/AGENTS.md` block
  via the existing PRS-004 mechanical sync. No new capability enum member is needed
  on `NodeCapability` (HITL1 uses the existing `capabilities.run_agent()` path,
  not a new store protocol).
- **Typed state/checkpoint data affected:** a new `profile_ref: ContentRef | None`
  and short enum-string fields (`research_depth`, `target_audience`, `output_format`,
  `cost_tolerance`, `time_budget`, `must_answer_questions: tuple[str, ...]`) are
  added to `ResearchState`/`ResearchCheckpoint` under `WriterRole.CONTROLLER`
  ownership. `RESEARCH_STATE_SCHEMA_VERSION` is **not bumped** because all new
  fields default to `None`/empty and are backward-compatible with existing version-2
  checkpoints. Large content (the full structured brief text and the serialized
  profile) stays in the sandbox via `ContentRef`; only short enum strings and the
  content ref enter the checkpoint.
- **Graph nodes/components affected:** only `hitl1` swaps from fake to real in the
  mixed graph; every other phase remains fake. HITL1 stays a non-gated control node;
  the real node calls `run_agent` for brief generation, performs inline profile
  validation, and sets the route directly. The normalized topology is unchanged
  (`hitl1 --accepted--> topic_planning`, `hitl1 --cancel--> cancelled`); no new
  edge is added. Targeted evidence and rerun are not implemented here.
- **Node-agent roles used:** HITL1 calls `capabilities.run_agent()` exactly once
  per generation for structured-brief generation. The agent is a bounded
  single-turn call with a constrained output schema; it performs no web search,
  MCP, ACP, or DeerFlow `task` subagent call. The agent cannot write the profile
  to the checkpoint, set the route, or advance the phase. Planners, workers, and
  repair roles are unchanged.
- **Sandbox artifacts read/written:** the HITL1 node reads the bootstrap marker
  (for the original question context) and writes a `profile.json` under the
  canonical `request/` subtree via a `ContentRef`. It may optionally read the
  marker for request-digest confirmation. No evidence ledger, work-spec, result,
  or DPT queue/index/status bundle file is created.
- **DeerFlow extension surfaces:** the existing downstream reflection path
  `deerflow_deep_research.tool:deep_research_tool` and registered lifecycle
  handlers are unchanged. No `config.yaml` section, `extensions_config.json` key,
  public/custom skill, per-user Agent/SOUL, MCP, ACP, or lead-agent middleware
  surface is added or modified.
- **Diagnostics:** no new `ReadinessDiagnostic` dimension. HITL1 has no new
  infrastructure dependency beyond the existing `capabilities.run_agent()` bridge
  already proven by the fake graph.
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

New requirement IDs are HIN-001 through HIN-005 (`hitl1-node`). No existing
requirement is modified; the new supporting files are registered through the
existing PRS-004 registry sync.
