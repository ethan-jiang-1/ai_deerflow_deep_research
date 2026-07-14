## ADDED Requirements

> req: HIN-001, HIN-002, HIN-003, HIN-004, HIN-005

### Requirement: HITL1 generates a structured brief from the original question

The real HITL1 node SHALL call `capabilities.run_agent()` exactly once per generation
to produce a structured brief draft derived from `state["request_text"]`. The agent
call SHALL use a constrained output schema derived from a frozen `StructuredBrief`
model with closed-enum profile dimensions (`ResearchDepth`, `TargetAudience`,
`OutputFormat`, `CostTolerance`, `TimeBudget`). The node SHALL validate the model
output against the schema; on validation failure it SHALL re-prompt once, and on a
second failure it SHALL route `exhausted` to a terminal `BLOCKED` lifecycle. The
agent SHALL have no tool, web-search, MCP, ACP, or DeerFlow-task access. The
structured brief SHALL be advisory input presented to the user for confirmation; the
user's response, not the model's proposal, is the authority for the final profile
values.

#### Scenario: Successful brief generation
- **WHEN** HITL1 enters with `state["request_text"]` = "Compare renewable energy storage technologies for grid-scale deployment" and a `FakeToolCallingModel` that returns a valid `StructuredBrief` JSON matching the output schema
- **THEN** the node calls `run_agent` once, validates the output, and proceeds to the interrupt with the brief embedded in `HumanInputRequest.context`

#### Scenario: Model output fails schema validation once
- **WHEN** the first `run_agent` call returns JSON missing a required dimension (e.g., `depth` is absent) and the retry returns valid JSON
- **THEN** the node re-prompts exactly once without presenting the invalid output to the user, and proceeds with the valid retry output

#### Scenario: Model output fails schema validation twice
- **WHEN** both the initial `run_agent` call and the retry return invalid output (malformed or missing required dimensions)
- **THEN** the node SHALL set `phase_status=TERMINAL`, `terminal_status=BLOCKED`, `terminal_reason=GATE_BLOCKED`, and `route=exhausted` without calling `interrupt()`

#### Scenario: run_agent call raises an unhandled exception
- **WHEN** `capabilities.run_agent()` raises a runtime error (e.g., model unavailable)
- **THEN** the node SHALL propagate the error to the handler denial path without writing a partial profile or calling `interrupt()`

### Requirement: HITL1 presents structured brief and profile dimensions to the user via interrupt

The real HITL1 node SHALL present the structured brief and profile dimensions to the
user through the existing `interrupt(PendingResearchInterrupt(…))` mechanism with
`mode=TEXT`. The `HumanInputRequest.context` field SHALL carry a compact JSON payload
containing the LLM-generated brief summary, the proposed dimension values, and the
list of must-answer dimensions. The `request_id` SHALL be derived from
`make_hitl_request_id(research_id, phase="hitl1", generation, ordinal)` matching the
fake HITL1 format. The `suspension_cursor` SHALL reference the last consumed message
id. The interrupt payload SHALL be versioned (`PendingResearchInterrupt` schema
unchanged from change 01).

#### Scenario: First-visit interrupt with full brief
- **WHEN** HITL1 visits a research for the first time (ordinal=1) and brief generation succeeds
- **THEN** the node calls `interrupt()` with a `PendingResearchInterrupt` containing `phase="hitl1"`, `generation=<state generation>`, and `mode=TEXT`, and the graph suspends at the HITL1 checkpoint

#### Scenario: Interrupt request_id includes correct ordinal
- **WHEN** HITL1 is visited for the second time (re-entrant, ordinal=2) on the same research
- **THEN** the `request_id` encodes `ordinal=2` and is distinct from the first visit's `request_id`, and `completed_visits(state, "hitl1")` returns 1 at entry time

#### Scenario: Interrupt carries structured context
- **WHEN** the interrupt is called with a generated brief
- **THEN** the `HumanInputRequest.context` string contains valid JSON with at minimum `brief_summary`, `proposed_dimensions`, and `required_dimensions` keys, and the total context length does not exceed 2,048 characters

### Requirement: HITL1 parses and validates the human response against profile dimensions

On resume, the real HITL1 node SHALL parse the human response text (from
`AcceptedHumanResponse.value`) to extract profile dimension values. The parser SHALL
validate that each extracted dimension matches its closed enum or format constraints.
The node SHALL reject a response whose `request_id` does not match the pending
interrupt's `request_id`. On `InternalCancelDecision`, the node SHALL route `cancel`
to a terminal `CANCELLED` lifecycle, matching the fake HITL1 behavior exactly.

#### Scenario: Complete valid response accepted
- **WHEN** a resume delivers a human response containing recognizable values for all required dimensions (`depth=standard`, `audience=practitioner`, `format=detailed_report`, `cost_tolerance=moderate`, `time_budget=standard`, plus at least one must-answer question)
- **THEN** the node extracts all values, constructs a valid `ResearchProfile`, writes it to state, and routes `accepted → topic_planning`

#### Scenario: Response with only some dimensions filled
- **WHEN** a resume delivers a human response that specifies `depth=quick_overview` and `audience=layperson` but does not address `format`, `cost_tolerance`, `time_budget`, or must-answer questions
- **THEN** the node constructs a partial profile with the supplied values, generates a follow-up prompt asking only for the missing dimensions, and re-interrupts with ordinal incremented (re-entrant HITL1)

#### Scenario: Response with unrecognizable dimension value
- **WHEN** a resume delivers a human response stating `depth=superficial` (not a valid `ResearchDepth` enum member)
- **THEN** the node treats `depth` as unset, and the follow-up prompt includes a clarification that valid options are `quick_overview`, `standard`, `deep_dive`, or `exhaustive`

#### Scenario: Response request_id mismatch
- **WHEN** a resume delivers `AcceptedHumanResponse.request_id` that does not match the pending interrupt's `request_id`
- **THEN** the node SHALL raise a `ValueError("response_mismatch")` (matching fake HITL1 behavior), and the lifecycle handler SHALL surface this as `ResultCode.RESPONSE_MISMATCH`

#### Scenario: Cancel decision during HITL1 interrupt
- **WHEN** a resume delivers `InternalCancelDecision` (e.g., from a cancel action while suspended at HITL1)
- **THEN** the node SHALL route `cancel` with `terminal_status=CANCELLED` and `terminal_reason=USER_CANCELLED`, matching the fake HITL1 behavior

#### Scenario: Re-entrant visits bounded at 3
- **WHEN** HITL1 has been visited 3 times (ordinals 1, 2, 3) and the human response on the 3rd visit is still incomplete
- **THEN** the node SHALL accept the best-effort partial profile, set a `degraded_profile` marker in the checkpoint, and route `accepted` rather than issuing a 4th interrupt

### Requirement: HITL1 stores the validated profile in state and sandbox

The real HITL1 node SHALL write the validated `ResearchProfile` to the sandbox as
`workspace/deep-research/<research_id>/request/profile.json` referenced via a new
`profile_ref: ContentRef | None` checkpoint field. It SHALL additionally write the
closed-enum dimension values as short string fields in the checkpoint
(`research_depth`, `target_audience`, `output_format`, `cost_tolerance`, `time_budget`,
`must_answer_questions: tuple[str, ...]`). The `profile_ref` and dimension fields SHALL
be owned by `WriterRole.CONTROLLER`. The node SHALL NOT bump
`RESEARCH_STATE_SCHEMA_VERSION` (all new fields default to `None`/empty and are
backward-compatible). The profile SHALL be written atomically: either all fields are
set and the route is `accepted`, or none are and the interrupt is re-issued.

#### Scenario: Profile written to sandbox ContentRef
- **WHEN** a complete valid human response is accepted
- **THEN** the node writes `profile.json` to the bundle's `request/` subtree, creates a `ContentRef` with `sandbox_path`, `content_hash`, `schema_version=1`, and `short_summary`, and sets `state["profile_ref"]` to that `ContentRef`

#### Scenario: Short enum fields written to checkpoint
- **WHEN** a complete valid human response with `depth=deep_dive`, `audience=domain_expert`, `format=annotated_bibliography`, `cost_tolerance=extensive`, `time_budget=overnight`, and `must_answer=["Q1", "Q2"]` is accepted
- **THEN** the checkpoint fields `research_depth`, `target_audience`, `output_format`, `cost_tolerance`, `time_budget`, and `must_answer_questions` are set to the corresponding values and are readable by downstream nodes without a sandbox read

#### Scenario: Cancel route writes no profile
- **WHEN** the user cancels at the HITL1 interrupt
- **THEN** no `profile_ref`, dimension fields, or `profile.json` are written to the checkpoint or sandbox

#### Scenario: Existing version-2 checkpoints remain readable
- **WHEN** a checkpoint created before this change (without `profile_ref` or dimension fields) is loaded
- **THEN** `ResearchCheckpoint` validation succeeds with `profile_ref=None` and all dimension fields at their defaults

### Requirement: HITL1 integrates into the mixed graph preserving the full-fake path

The real HITL1 SHALL replace the fake HITL1 in the mixed implementation map when
`hitl1=real` while every other non-bootstrap phase remains `fake`. The normalized
topology SHALL be unchanged: `hitl1 --accepted--> topic_planning` and `hitl1 --cancel-->
cancelled`. The full-fake map (all `fake`) SHALL be unchanged and SHALL complete the
E2E lifecycle path without calling `run_agent`. The lifecycle result SHALL remain
`implementation_mode=full_fake` because HITL1 produces no research findings or report.
No `NodeCapability` member SHALL be added; HITL1 SHALL use the existing
`capabilities.run_agent()` bridge. `backend/` and `frontend/` SHALL NOT be modified.

#### Scenario: Mixed graph with real HITL1
- **WHEN** the implementation map sets `bootstrap=real`, `hitl1=real`, and all other phases `fake`
- **THEN** the graph compiles, the real HITL1 factory is selected (no unavailable sentinel), and an E2E run goes `bootstrap → hitl1 → (interrupt) → resume → topic_planning → ... → completed` with HITL1 calling `run_agent` exactly once per generation

#### Scenario: Full-fake graph unchanged
- **WHEN** the implementation map sets all phases to `fake`
- **THEN** the graph compiles identically to the pre-change full-fake graph, the fake HITL1 presents its hardcoded fixture message, and the E2E path completes without calling `run_agent`

#### Scenario: HITL1 node spec declares no new capability
- **WHEN** the HITL1 `NodeSpec` is loaded
- **THEN** `NodeCapability.BOOTSTRAP_BUNDLE` is NOT in its `capabilities` frozenset, and the node wrapper does not attach `bootstrap_bundle` to its `NodeBuildDependencies`

#### Scenario: No backend or frontend files modified
- **WHEN** the change is applied
- **THEN** `git diff -- backend/ frontend/` is empty
