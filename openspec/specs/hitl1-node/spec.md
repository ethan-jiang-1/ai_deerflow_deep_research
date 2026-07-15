# hitl1-node Specification

> req: HIN-001, HIN-002, HIN-003, HIN-004, HIN-005

## Purpose

The real HITL1 node is the first model-calling node in the Deep Research graph. It
generates a validated structured research brief from the original question through the
runtime node-agent bridge using closed-enum profile dimensions and fail-closed schema
validation, presents the brief and follow-up prompts through the existing graph-owned
interrupt protocol with bounded compact context and deterministic request ordinals,
parses JSON or free-text human responses deterministically with restart-durable
partial-profile accumulation and bounded follow-up rounds, records the validated profile
as request-bundle `profile.json` plus checkpoint short fields and a `ContentRef` without
bumping the `ResearchState` schema version, and integrates into the mixed graph with
explicit follow-up and blocked routes while preserving full-fake behavior and the
backend/frontend boundary.
## Requirements
### Requirement: HITL1 generates a validated structured brief from the original question

The real HITL1 node SHALL call `capabilities.run_agent()` exactly once per brief
generation attempt to produce a structured brief draft derived from
`state["request_text"]`. The node SHALL build a bounded `NodeExecutionRequest` whose
objective includes the original question and whose expected output is one JSON object
matching the `StructuredBrief` schema. The node SHALL validate the agent result's
`summary` as that JSON object before presenting anything to the user.

The `StructuredBrief` schema SHALL be a frozen extra-forbid Pydantic contract containing
a human-readable brief summary, proposed closed-enum profile dimensions
(`ResearchDepth`, `TargetAudience`, `OutputFormat`, `CostTolerance`, `TimeBudget`),
`must_answer` draft questions, `scope_boundaries`, `custom_notes`, and
`schema_version=1`. The schema SHALL reject unknown enum values, malformed JSON,
missing required fields, oversized text, and extra fields. The agent's proposal SHALL be
advisory only; the final recorded profile SHALL be derived from the validated human
response, not silently copied from model output.

If the first model result fails schema validation, the node SHALL re-prompt once with a
repair instruction that includes only validation failure metadata and the original
question. If the second model result fails schema validation, HITL1 SHALL fail closed
with `terminal_status=BLOCKED`, `terminal_reason=GATE_BLOCKED`, and `route=exhausted`
without calling `interrupt()` or writing profile state. If `run_agent()` raises or
returns a non-success `NodeExecutionResult`, the node SHALL fail closed before
interrupting and SHALL NOT write a partial profile.

The HITL1 `NodeSpec` SHALL continue to use the existing node-agent capability protocol;
no new model/tool capability enum member is added for brief generation. The runtime
recipe that selects real HITL1 SHALL inject a real `RuntimeNodeAgentBridge` whose policy
allows no tools and at most one model call per bridge invocation; HITL1 may invoke it a
second time only for structured-brief schema repair. Fake and full-fake paths SHALL keep
using unavailable or test capabilities and SHALL never call a model.

#### Scenario: Successful brief generation
- **WHEN** HITL1 enters with `state["request_text"]` = "Compare renewable energy storage technologies for grid-scale deployment" and a fake node-agent capability returns a valid `StructuredBrief` JSON in `NodeExecutionResult.summary`
- **THEN** the node calls `run_agent` once with a bounded request that includes the original question, validates the JSON, and proceeds to the user interrupt with the validated brief embedded in `HumanInputRequest.context`

#### Scenario: Model output fails schema validation once
- **WHEN** the first `run_agent` call returns JSON missing a required dimension and the retry returns valid JSON
- **THEN** the node re-prompts exactly once, never presents the invalid output, and proceeds with the valid retry output

#### Scenario: Model output fails schema validation twice
- **WHEN** both the initial `run_agent` call and the retry return malformed or schema-invalid output
- **THEN** the node sets `phase_status=TERMINAL`, `terminal_status=BLOCKED`, `terminal_reason=GATE_BLOCKED`, and `route=exhausted`, and no interrupt or profile artifact is produced

#### Scenario: Runtime injects the real node-agent bridge only for real HITL1
- **WHEN** the mixed implementation recipe selects `hitl1=real`
- **THEN** `RuntimeNodeDependencyResolver` provides a real `RuntimeNodeAgentBridge` with no allowed tools and a one-model-call-per-invocation budget for HITL1, while the full-fake recipe keeps unavailable capabilities and any fake HITL node call to `run_agent` fails the test

#### Scenario: Agent failure does not create partial state
- **WHEN** `capabilities.run_agent()` raises or returns a non-success `NodeExecutionResult`
- **THEN** HITL1 fails before `interrupt()`, leaves `pending_profile`, `profile_ref`, and all dimension fields unset, and does not consume a human response

### Requirement: HITL1 presents structured brief and profile dimensions through durable interrupts

The real HITL1 node SHALL present the validated structured brief and profile dimensions
through the existing `interrupt(PendingResearchInterrupt(...))` mechanism with
`mode=TEXT`. The wire schemas for `PendingResearchInterrupt`,
`HumanInputRequest`, `AcceptedHumanResponse`, and `InternalCancelDecision` SHALL remain
version-compatible with the existing lifecycle contract. The `HumanInputRequest.context`
string SHALL be bounded to 2,048 characters and SHALL contain a compact JSON object with
at minimum:

- `context_schema_version: 1`
- `brief_summary`
- `proposed_dimensions`
- `required_dimensions`
- `missing_dimensions`
- `valid_options`
- `instructions`

The `request_id` SHALL be derived with `make_hitl_request_id(research_id,
phase="hitl1", generation, ordinal)`. The ordinal SHALL come from the checkpointed
logical HITL1 visit count, so first visit uses ordinal 1 and each durable re-entrant
follow-up uses the next ordinal. The `suspension_cursor` SHALL reference the latest
consumed message id, falling back to the start message id.

HITL1 SHALL not store a duplicate mutable pending descriptor in `ResearchState`; the
LangGraph checkpoint interrupt remains the only pending-request authority. Durable
follow-up state that is needed to build the next prompt SHALL be stored separately as
bounded profile-progress state, never as a pending interrupt copy.

#### Scenario: First-visit interrupt with full brief
- **WHEN** HITL1 visits a research for the first time and brief generation succeeds
- **THEN** the node calls `interrupt()` with a `PendingResearchInterrupt` containing `phase="hitl1"`, the current generation, `mode=TEXT`, and compact structured context for all required dimensions

#### Scenario: Follow-up interrupt has a new ordinal
- **WHEN** a prior incomplete response has been consumed and HITL1 loops back to ask only for missing dimensions
- **THEN** the next `request_id` encodes ordinal 2, is distinct from the first visit's `request_id`, and `completed_visits(state, "hitl1")` returns 1 at entry time

#### Scenario: Interrupt context is bounded and parseable
- **WHEN** the interrupt is constructed from a generated brief or follow-up prompt
- **THEN** `HumanInputRequest.context` is valid compact JSON, includes the required keys, advertises stable enum machine values, and does not exceed 2,048 characters

#### Scenario: No duplicate pending authority
- **WHEN** a lifecycle is suspended at HITL1
- **THEN** the only pending request descriptor is the LangGraph interrupt task; checkpoint fields may contain bounded profile progress but not another mutable copy of the pending request

### Requirement: HITL1 parses, validates, and durably accumulates human profile answers

On resume, the real HITL1 node SHALL validate that `AcceptedHumanResponse.request_id`
matches the pending HITL1 request id. A mismatch SHALL raise
`ValueError("response_mismatch")`, preserving the existing lifecycle correlation
behavior. `InternalCancelDecision` SHALL route `cancel` to terminal `CANCELLED` with
`terminal_reason=USER_CANCELLED` and SHALL NOT write profile fields.

The parser SHALL accept either a compact JSON object or free text. Recognized profile
dimension values SHALL be accepted only when they match the closed enum machine values
or an explicitly documented synonym that maps deterministically to one enum value.
Unrecognized values SHALL be treated as unset, not coerced by model judgment. The parser
SHALL return a frozen partial-profile/progress contract that permits missing dimensions
while still enforcing bounds for supplied values. A complete `ResearchProfile` SHALL be
constructible only when all required closed-enum dimensions and at least one
`must_answer` question are present, unless the bounded follow-up policy degrades the
profile after the final allowed attempt.

Incomplete responses SHALL be durable across process restart. HITL1 SHALL write bounded
profile-progress fields into `ResearchState` before routing back to HITL1 with
`route=needs_followup`; it SHALL NOT rely on Python closure state. The graph SHALL then
enter HITL1 again, compute the next ordinal from the checkpointed trace, and issue a
follow-up interrupt asking only for missing or invalid dimensions. HITL1 SHALL allow at
most three user-answer rounds (ordinals 1, 2, 3). If the third answer is still
incomplete, the node SHALL record the best-effort profile with `degraded_profile=True`
and route `accepted`.

#### Scenario: Complete valid response accepted
- **WHEN** a resume delivers recognizable values for all required dimensions (`depth=standard`, `audience=practitioner`, `format=detailed_report`, `cost_tolerance=moderate`, `time_budget=standard`) plus at least one must-answer question
- **THEN** the node constructs a complete `ResearchProfile`, writes profile state and artifact data, consumes the response ids, and routes `accepted -> topic_planning`

#### Scenario: Free-text response is parsed deterministically
- **WHEN** the human writes "standard depth, for practitioners, detailed report, moderate cost, standard time; must answer Q1 and Q2"
- **THEN** the parser extracts only those stable machine values and must-answer questions, and no LLM is called to reinterpret the answer

#### Scenario: Response with only some dimensions filled
- **WHEN** a resume specifies `depth=quick_overview` and `audience=layperson` but omits `format`, `cost_tolerance`, `time_budget`, or must-answer questions
- **THEN** HITL1 stores durable profile progress, consumes the response ids, routes `needs_followup` back to HITL1, and the next interrupt asks only for the missing fields

#### Scenario: Restart resumes a follow-up
- **WHEN** a process commits the partial profile progress and the follow-up interrupt, then a fresh process resumes with the matching follow-up response
- **THEN** the node loads progress from the checkpoint, merges only newly valid fields, and can route `accepted` without relying on in-memory closure data

#### Scenario: Response with unrecognizable dimension value
- **WHEN** a resume states `depth=superficial`
- **THEN** the parser treats `depth` as unset, preserves any other valid fields, and the follow-up context lists valid `depth` options `quick_overview`, `standard`, `deep_dive`, and `exhaustive`

#### Scenario: Response request_id mismatch
- **WHEN** a resume delivers `AcceptedHumanResponse.request_id` that does not match the pending interrupt's `request_id`
- **THEN** the node raises `ValueError("response_mismatch")`, the lifecycle handler surfaces `ResultCode.RESPONSE_MISMATCH`, and the checkpoint and pending interrupt remain unchanged

#### Scenario: Cancel decision during HITL1
- **WHEN** a resume delivers `InternalCancelDecision`
- **THEN** the node routes `cancel` with `terminal_status=CANCELLED` and `terminal_reason=USER_CANCELLED`, and no profile progress or final profile fields are written

#### Scenario: Follow-up rounds are bounded
- **WHEN** HITL1 receives the third user-answer round and required fields are still missing
- **THEN** the node records the best-effort profile, sets `degraded_profile=True`, clears transient profile-progress fields, and routes `accepted` rather than issuing another interrupt

### Requirement: HITL1 stores the recorded profile as checkpoint fields and request-bundle content

The real HITL1 node SHALL write the final recorded profile to the request bundle as
`workspace/deep-research/<research_id>/request/profile.json` through a runtime-owned
request-bundle write capability, and SHALL reference that artifact via
`state["profile_ref"]`. The request-bundle capability SHALL be attached only when the
selected real factory declares it. It SHALL reuse the established bootstrap bundle root,
perform host-side path containment, write atomically, compute the content hash from the
canonical JSON bytes, and return a bounded `ContentRef`. Nodes SHALL receive only the
pure protocol, not host paths or raw runtime authority.

The checkpoint SHALL additionally store short, bounded fields needed by topic planning:
`research_depth`, `target_audience`, `output_format`, `cost_tolerance`, `time_budget`,
`must_answer_questions`, and `degraded_profile`. To support durable re-entrant
follow-up, the checkpoint SHALL also store bounded transient progress fields
`pending_profile` and `profile_followup_round`; those fields SHALL be cleared when
HITL1 accepts or cancels. `profile_ref`, the short final fields, and transient progress
fields SHALL be owned by `WriterRole.CONTROLLER`, listed in `OWNERSHIP_TABLE`, and
protected by controller-authorized reducers and the local authority-writer guard used by
`apply_research_update`.

`RESEARCH_STATE_SCHEMA_VERSION` SHALL NOT be bumped. Existing version-2 checkpoints
without the new fields SHALL validate with `profile_ref=None`, empty short fields,
`pending_profile=None`, `profile_followup_round=0`, and `degraded_profile=False`.
Final profile publication SHALL be atomic from the graph perspective: on `accepted`, the
artifact write and all checkpoint profile fields are produced together; on follow-up,
only transient progress fields are written; on cancel or brief-generation failure, no
final profile fields are written.

#### Scenario: Profile written to request-bundle ContentRef
- **WHEN** a complete valid human response is accepted
- **THEN** HITL1 writes canonical `profile.json` under the bundle's `request/` subtree, receives a `ContentRef` with `sandbox_path`, `content_hash`, `schema_version=1`, and `short_summary`, and sets `state["profile_ref"]` to that ref

#### Scenario: Short enum fields written to checkpoint
- **WHEN** a valid response records `depth=deep_dive`, `audience=domain_expert`, `format=annotated_bibliography`, `cost_tolerance=extensive`, `time_budget=overnight`, and `must_answer=["Q1", "Q2"]`
- **THEN** the corresponding checkpoint fields are set to those machine values and are readable by downstream nodes without loading `profile.json`

#### Scenario: Partial progress is not final profile state
- **WHEN** the first answer is incomplete
- **THEN** `pending_profile` and `profile_followup_round` are written, but `profile_ref`, final short dimension fields, and `profile.json` are not written until an accepted final profile exists

#### Scenario: Cancel route writes no profile
- **WHEN** the user cancels at HITL1
- **THEN** no final profile fields, `profile_ref`, or `profile.json` are written, and any transient profile progress is cleared

#### Scenario: Existing version-2 checkpoints remain readable
- **WHEN** a checkpoint created before this change lacks profile fields
- **THEN** `ResearchCheckpoint` validation succeeds with default profile values and no schema-version bump

### Requirement: HITL1 integrates into the mixed graph with explicit lifecycle and governance updates

The real HITL1 SHALL replace the fake HITL1 in the mixed implementation map when
`bootstrap=real` and `hitl1=real` while every other non-bootstrap phase remains fake.
Selecting `hitl1=real` without `bootstrap=real` SHALL fail closed during recipe or graph
binding because real HITL1 requires the established request bundle root for
`profile.json`. The full-fake map (all `fake`) SHALL be unchanged and SHALL complete the
existing E2E lifecycle path without calling `run_agent` or writing request profile
artifacts.

Because real HITL1 can fail closed before user interruption and can perform durable
follow-up rounds, this change SHALL update the normalized topology and graph builder to
include exactly two new HITL1 route labels: `needs_followup -> hitl1` and
`exhausted -> blocked/END`. Existing HITL1 routes `accepted -> topic_planning` and
`cancel -> cancelled/END` SHALL remain unchanged. The committed topology snapshot and
route-contract tests SHALL be regenerated or updated in the same change. No route may
silently fall back to fake behavior.

The HITL1 node-local contracts SHALL include `accepted`, `cancel`, `needs_followup`, and
`exhausted` result routes. The project-structure governance SHALL be updated so a real
graph-owned HITL node module may import exactly public `langgraph.types.interrupt`,
matching the existing fake exception without opening ordinary nodes to LangGraph
imports. New production paths and capability declarations SHALL be registered in
`project-structure.toml` and the generated `agent/AGENTS.md` block.

The lifecycle result SHALL remain `implementation_mode=full_fake` for the mixed
bootstrap/HITL1 path because no topic generation, evidence collection, synthesis, or
report is real. `backend/`, `frontend/`, root config examples, extensions config, public
skills, per-user Agent/SOUL, MCP, ACP, and lead-agent middleware surfaces SHALL NOT be
modified.

#### Scenario: Mixed graph with real HITL1
- **WHEN** the implementation map sets `bootstrap=real`, `hitl1=real`, and every later phase `fake`
- **THEN** the graph compiles, selects both real factories, can run `bootstrap -> hitl1 -> interrupt -> resume -> topic_planning -> ... -> completed`, and HITL1 calls the node-agent bridge exactly once per brief generation attempt

#### Scenario: Real HITL1 requires real bootstrap
- **WHEN** the implementation map sets `hitl1=real` but does not set `bootstrap=real`
- **THEN** recipe creation or graph binding fails closed before graph invocation with a diagnostic naming the invalid real-HITL1/bootstrap dependency, and no node-agent bridge or request-bundle writer is constructed

#### Scenario: Follow-up loop is explicit and bounded
- **WHEN** the first HITL1 response is incomplete
- **THEN** the graph follows `hitl1 --needs_followup--> hitl1`, issues a second interrupt with ordinal 2, and can later route `accepted` or `exhausted` through declared edges only

#### Scenario: HITL1 blocked route is explicit
- **WHEN** brief generation fails schema validation twice before the first interrupt
- **THEN** the graph follows `hitl1 --exhausted--> END`, the lifecycle result is typed `blocked`, and no pending interrupt exists

#### Scenario: Full-fake graph unchanged
- **WHEN** the implementation map sets all phases to `fake`
- **THEN** the graph compiles identically to the pre-change full-fake path, fake HITL1 presents its hardcoded fixture message, and no node-agent bridge or request-profile bundle writer is used

#### Scenario: Governance accepts the real HITL interrupt boundary
- **WHEN** the architecture checker scans `graph/nodes/hitl1/node.py`
- **THEN** an import of exactly `langgraph.types.interrupt` is accepted for the real HITL node, while other ordinary node modules remain forbidden from importing LangGraph directly

#### Scenario: No upstream or UI files modified
- **WHEN** the change is applied
- **THEN** `git diff -- backend/ frontend/ config.example.yaml extensions_config.example.json` is empty

