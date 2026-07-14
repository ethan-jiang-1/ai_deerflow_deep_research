## Context

Change 05 delivered a real bootstrap node that atomically establishes the research
bundle and routes `needs_input → HITL1`. The fake HITL1 (`graph/nodes/hitl1/fake.py`)
already uses the real LangGraph `interrupt()` mechanism, real `PendingResearchInterrupt`/
`AcceptedHumanResponse` types, and real resume handling through `ResumeResearchHandler`.
Only the prompt content is a hardcoded fixture.

The HITL1 node is the first model-calling node in the graph. Unlike bootstrap (which
is a deterministic control node with zero model calls), HITL1 must call an LLM to
generate a structured brief from the user's original question, present it to the user
for confirmation and refinement, parse the human response, and store the resulting
profile for downstream phases.

The design must answer: what profile dimensions exist, how the LLM is prompted and
constrained, how the human response is parsed and validated, what state fields hold
the profile, and how incomplete answers trigger re-entrant follow-up without leaving
the HITL1 phase.

## Goals / Non-Goals

**Goals:**
- Define a frozen `ResearchProfile` with closed-enum dimensions that the model cannot
  silently substitute
- Generate a structured brief via a single bounded `run_agent` call with a constrained
  output schema
- Present the brief + profile dimensions through the existing `interrupt()` protocol
- Parse free-text human responses back into validated profile values
- Support re-entrant follow-up interrupts for incomplete answers (same checkpoint,
  same phase)
- Store the profile as both a sandbox `ContentRef` and short checkpoint fields
- Keep the `accepted`/`cancel` routes and the interrupt/resume wire format unchanged
- Swap into the mixed graph preserving the full-fake E2E path

**Non-Goals:**
- No topic generation or search execution (that is change 07)
- No structured choice/option UI mode — HITL1 uses `mode=TEXT` only (choice mode is
  reserved for HITL2)
- No HITL2 or scheduled auto-proceed
- No modification to the LangGraph `interrupt()` mechanism, `PendingResearchInterrupt`,
  `AcceptedHumanResponse`, or `InternalCancelDecision` wire format
- No new `NodeCapability` enum member — HITL1 uses the existing
  `capabilities.run_agent()` bridge
- No `backend/` or `frontend/` changes

## Decisions

### Decision 1: Profile as a frozen Pydantic model with closed enums

The `ResearchProfile` is a frozen Pydantic model (`extra="forbid"`) with these
dimensions:

| Dimension | Enum Type | Values |
|---|---|---|
| `depth` | `ResearchDepth` | `quick_overview`, `standard`, `deep_dive`, `exhaustive` |
| `audience` | `TargetAudience` | `layperson`, `practitioner`, `domain_expert`, `executive` |
| `format` | `OutputFormat` | `executive_brief`, `detailed_report`, `annotated_bibliography`, `faq` |
| `cost_tolerance` | `CostTolerance` | `minimal`, `moderate`, `extensive` |
| `time_budget` | `TimeBudget` | `very_quick`, `standard`, `thorough`, `overnight` |
| `must_answer` | `tuple[str, ...]` | User-supplied concrete questions (1–8, each ≤ 256 chars) |
| `scope_boundaries` | `str` | Free-text scope notes (≤ 2,048 chars) |
| `custom_notes` | `str` | Free-text additional context (≤ 1,024 chars) |

**Why closed enums over free text:** Later phases (topic planning, wave depth
selection, output formatting) branch on these values. If the model could invent
`depth="super_deep_bro"`, every downstream consumer would need a fallback path.
Closed enums make the contract explicit and testable.

**Why Pydantic over a TypedDict:** The profile must be serializable to JSON for
the sandbox `ContentRef` and validatable on parse. Pydantic gives us `model_validate`
with clear error messages for incomplete/malformed responses.

**Alternatives considered:**
- Store only free-text notes and let the topic planner infer everything — rejected
  because it moves the ambiguity downstream and the planner (change 07) shouldn't
  re-do HITL1's job.
- Use `HumanInputMode.CHOICE` with structured options — rejected for HITL1 because
  the user needs to express nuanced scope boundaries and must-answer questions;
  choice mode is a better fit for HITL2's constrained proceed/revise/rerun options.

### Decision 2: Single bounded run_agent call for brief generation

HITL1 calls `capabilities.run_agent()` exactly once per generation with:
- A system prompt that includes the original question and constrains the agent to
  produce a structured brief
- A constrained output schema (JSON Schema derived from a `StructuredBrief` pydantic
  model) so the agent returns machine-parseable dimensions plus human-readable
  commentary
- No tools, no web search, no MCP/ACP/DeerFlow-task access — the agent is a pure
  reasoning call

**Why single call, not iterative:** The brief is a draft for user confirmation.
The iteration happens through the human-in-the-loop (user refines in their
response), not through repeated model calls before the first interrupt.

**Why constrained output schema:** The model must produce structured dimensions
the node can validate before presenting to the user. If the model's output fails
schema validation, the node re-prompts once; a second failure is a terminal
`BLOCKED` route (fail closed rather than present unchecked model output to the
user).

### Decision 3: Re-entrant HITL1 through visit ordinal tracking

The fake HITL1 already tracks `completed_visits(state, "hitl1")` to compute the
interrupt `request_id`. The real HITL1 uses the same mechanism:

- **First visit (ordinal 1):** Generate the structured brief via LLM, present the
  full interrupt with all dimensions.
- **Re-entrant visits (ordinal > 1):** The previous human response was incomplete
  or ambiguous. Parse what we can, generate a follow-up prompt asking only for
  the missing/ambiguous dimensions, and re-interrupt with the same `request_id`
  prefix but an incremented ordinal.
- **Max re-entrant visits:** bounded at 3 total visits (ordinals 1, 2, 3). On the
  4th visit, accept the best-effort partial profile and route `accepted` with a
  `degraded_profile` marker.

**Why same-checkpoint re-entry rather than advancing and coming back:** The
topology has no edge from later phases back to HITL1 (unlike HITL2 which has
`revise_view → wave2_synthesis`). Re-entrant HITL1 keeps the graph simple and
the checkpoint consistent — the phase stays `hitl1` until the profile is
accepted or cancelled.

### Decision 4: Dual storage — ContentRef in sandbox + short fields in checkpoint

The full `ResearchProfile` is serialized to `workspace/deep-research/<rid>/request/profile.json`
and referenced via a `ContentRef` in `state["profile_ref"]`. Additionally, the
closed-enum values and must-answer questions are denormalized into short checkpoint
fields so the topic planner (change 07) can read them without a sandbox round-trip:

- `research_depth: str` (enum value)
- `target_audience: str` (enum value)
- `output_format: str` (enum value)
- `cost_tolerance: str` (enum value)
- `time_budget: str` (enum value)
- `must_answer_questions: tuple[str, ...]`

**Why dual storage:** The architecture rule is "large content stays out of the
checkpoint." The full profile (with `scope_boundaries` and `custom_notes` text)
belongs in the sandbox. But the topic planner needs the enum dimensions to
configure its agent prompts — forcing a sandbox read for every topic-planning
invocation adds latency and I/O coupling. The short enum fields (≤ 30 chars each)
are well within the checkpoint size budget and eliminate that dependency.

**Why not store the whole profile in the checkpoint:** `scope_boundaries` can be
up to 2,048 chars and `custom_notes` up to 1,024 — together they approach the
checkpoint size concern. The `ContentRef` pattern (already used by `synthesis_ref`,
`decision_brief_ref`, `report_refs`) is the established answer.

### Decision 5: Profile written by the node, not the agent

The `run_agent` call generates the structured brief and proposed dimensions, but
the **node** — not the agent — constructs the final `ResearchProfile` from the
validated human response. The agent's brief is advisory input to the user; the
user's response is the authority for the profile values.

**Why:** This follows the architecture rule "agents cannot write the profile to the
checkpoint, set the route, or advance the phase." The node is the controller; the
agent is a reasoning tool.

### Decision 6: Interrupt context carries structured JSON

The `HumanInputRequest.context` field (max 2,048 chars) carries a compact JSON
payload with:
- The LLM-generated brief summary (human-readable paragraph)
- The proposed dimension values (so the frontend can pre-fill if it supports
  structured rendering)
- The list of must-answer dimensions for validation

The frontend is not modified in this change; it continues to render `context` as
markdown text. The structured JSON is a forward-compatible payload that future
frontend changes can parse for a richer UI.

## Risks / Trade-offs

- **[Risk] LLM generates a brief that doesn't match the question** → The user
  sees the brief in the interrupt and can correct it in their response. The node
  validates the human-supplied dimensions, not the model's proposal.
- **[Risk] Human writes a response the parser cannot interpret** → The re-entrant
  follow-up asks specifically for the unparseable dimensions. After 3 attempts,
  best-effort partial profile is accepted.
- **[Risk] Profile dimensions evolve between changes** → The `ResearchProfile`
  model has a `schema_version` field. Future changes can add dimensions with a
  version bump and a migration path. The current version is 1.
- **[Risk] run_agent bridge fails (model unavailable, timeout)** → The node fails
  closed with a typed error. If the failure occurs before any interrupt, the
  lifecycle handler surfaces it as a terminal error (no partial state). If it
  occurs during re-entrant follow-up, the prior partial profile is preserved.
- **[Trade-off] Checkpoint fields duplicate sandbox data** → The enum fields are
  short (~30 chars each, ~200 bytes total). This is a deliberate trade-off to
  let the topic planner read profile dimensions without a sandbox I/O dependency,
  consistent with how `request_text` already lives in the checkpoint despite the
  original message being available in the thread history.
