> req: TOP-001, TOP-002, TOP-003, TOP-004, TOP-005

## ADDED Requirements

### Requirement: Real topic planning generates a validated structured topic plan from the confirmed profile

The real topic planning node SHALL call `capabilities.run_agent()` exactly once per
planning attempt to produce a structured topic plan derived from the checkpointed
HITL1 profile constraints (`request_text`, `research_depth`, `target_audience`,
`output_format`, `cost_tolerance`, `time_budget`, `must_answer_questions`, and
`degraded_profile`) read directly from `ResearchState`. When `must_answer_questions`
is empty (possible only with a degraded profile whose completeness check was
skipped), the node SHALL treat `request_text` as a synthetic must-answer question
for coverage binding. When `degraded_profile` is True, the prompt SHALL instruct the
model to plan broader, more conservative topics. The node SHALL build a bounded
`NodeExecutionRequest` whose objective carries those profile constraints and whose
expected output is one JSON object matching the `TopicPlan` schema. The node SHALL
validate the agent result's `summary` as that JSON object before recording any
state.

The `TopicPlan` schema SHALL be a frozen extra-forbid Pydantic contract containing
a bounded tuple (at most eight) of `ResearchTopic` values, each with a bounded
title, scope, must-answer bindings, search dimensions, and exclusions, plus a
`schema_version=1`. The schema SHALL reject unknown fields, malformed JSON,
missing required fields, oversized text, out-of-range topic counts, and unbound
free text. The agent's proposal SHALL be advisory only; topic ids and slugs SHALL
be derived by the materializer, never copied verbatim from model output.

If the first model result fails validation, the node SHALL re-prompt once with a
repair instruction carrying only validation failure metadata and the original
profile constraints. If validation fails twice, or `run_agent` raises or returns a
non-success result, the node SHALL fail closed before any state write with
`route=exhausted`, `phase_status=TERMINAL`, `terminal_status=BLOCKED`, and
`terminal_reason=GATE_BLOCKED`.

#### Scenario: Valid profile yields a validated topic plan
- **WHEN** real topic planning runs after real HITL1 accepted a complete profile and the model returns one valid `TopicPlan` JSON object
- **THEN** the node validates it, derives stable topic ids/slugs, and records the bounded planner-owned topic registry without calling a model a second time

#### Scenario: Invalid model output is repaired once
- **WHEN** the first model result is malformed JSON or violates the `TopicPlan` schema
- **THEN** the node re-prompts once with compact failure metadata, and on a valid second result records the plan, while an invalid second result never reaches state or Wave0

#### Scenario: Repeated invalid output fails closed before Wave0
- **WHEN** the model returns schema-invalid output twice or `run_agent` raises or returns a non-success result
- **THEN** the node writes no topic state, sets `route=exhausted` with terminal `BLOCKED`/`GATE_BLOCKED`, and the lifecycle does not advance to Wave0

#### Scenario: The agent cannot mutate control state
- **WHEN** the planning bridge is inspected
- **THEN** it runs under a zero-tool, one-model-call policy with no web, MCP, ACP, file-read, or DeerFlow `task` access, and cannot set `phase`, `route`, `topic_refs`, profile fields, or produce a `WorkSpec`

### Requirement: A deterministic materializer owns topic stability and the coverage map

A pure deterministic materializer (not the LLM) SHALL convert the validated
`TopicPlan` into a stable topic registry and a must-answer coverage map. It SHALL
derive each topic id and slug deterministically from the validated title and scope,
SHALL deduplicate topics by slug, SHALL reject overlapping scopes, and SHALL bind
every root `must_answer` question to at least one topic. The materializer SHALL be
the only producer of the registry serialization; the model SHALL NOT author ids,
slugs, or the registry format.

#### Scenario: Topic ids and slugs are stable and model-independent
- **WHEN** the same validated plan is materialized twice
- **THEN** both registries have identical ids, slugs, and ordering, and no id or slug is the raw model-proposed string

#### Scenario: Duplicate or overlapping topics are rejected
- **WHEN** the validated plan contains two topics that materialize to the same slug or have overlapping scopes
- **THEN** the materializer rejects the plan with a typed validation failure and no registry is recorded

#### Scenario: The coverage map binds every root question
- **WHEN** a validated plan is materialized
- **THEN** each `must_answer` question maps to at least one topic, and the bounded coverage map is recorded alongside the registry

### Requirement: Topic coverage and expansion are bounded and fail closed

The materializer SHALL enforce hard checks that reject empty coverage (a plan
covering no root question), uncovered root questions, and over-expansion beyond the
bounded topic count (at most eight). On a coverage or expansion failure the node
SHALL re-prompt the planner once with the specific failures, and on a second failure
SHALL fail closed to `route=exhausted` with terminal `BLOCKED`. A valid plan SHALL
cover every root `must_answer` question without exceeding the topic bound.

#### Scenario: Empty or uncovered coverage is rejected and retried
- **WHEN** a plan covers no root question or leaves a `must_answer` question unbound
- **THEN** the node re-prompts once with the missing-coverage failure, and records no registry until a covering plan validates

#### Scenario: Over-expansion is rejected
- **WHEN** a plan proposes more than the bounded topic count
- **THEN** the materializer rejects it, the node re-prompts once, and a still-over-expanded second result fails closed to terminal `blocked`

#### Scenario: A bounded covering plan is accepted
- **WHEN** a plan covers every root question within the topic bound with no duplicate or overlapping topics
- **THEN** the node records the registry and routes `next` toward Wave0

### Requirement: Topic planning records bounded planner-owned checkpoint state from checkpoint profile fields

Real topic planning SHALL record the validated topic registry and coverage map as
bounded planner-owned fields in `ResearchState`/`ResearchCheckpoint`
(`topic_refs` and `topic_registry`), declared with explicit writer, reader, and
reducer entries under `WriterRole.PLANNER`. It SHALL read profile constraints only from the checkpoint
short fields; it SHALL NOT read `request/profile.json`, SHALL NOT declare
`NodeCapability.REQUEST_BUNDLE`, `BOOTSTRAP_BUNDLE`, or `WORK_UNIT_CONTROLLER`,
SHALL produce no `WorkSpec`, and SHALL write no sandbox artifact. The new fields
SHALL default to empty and be backward-compatible with version-2 checkpoints, so
`RESEARCH_STATE_SCHEMA_VERSION` SHALL NOT be bumped.

#### Scenario: Topic registry is bounded planner-owned checkpoint data
- **WHEN** real topic planning accepts a valid plan
- **THEN** the checkpoint contains the bounded planner-owned topic registry and coverage map, downstream nodes can read them from state, and no topic file is written to the sandbox

#### Scenario: Existing version-2 checkpoint defaults topic fields
- **WHEN** status, resume, or cancel reads a version-2 checkpoint created before real topic planning fields existed
- **THEN** validation succeeds with empty topic fields and does not reset, auto-migrate, or reinterpret any existing field

#### Scenario: Profile is read from checkpoint, not the bundle
- **WHEN** real topic planning builds its planning objective
- **THEN** it reads `request_text`, depth/audience/format/cost/time enums, `must_answer_questions`, and `degraded_profile` from `ResearchState`, declares no request-bundle capability, and never opens `request/profile.json`

#### Scenario: Empty must-answer questions fall back to request text
- **WHEN** `must_answer_questions` is empty and `degraded_profile` is True
- **THEN** the planner uses `request_text` as a synthetic must-answer question, generates topics covering the original request, and the materializer validates coverage against that synthetic question

#### Scenario: Non-planner writers cannot mutate topic authority
- **WHEN** a controller, worker, repair agent, or model-derived update attempts to set the topic registry or coverage map
- **THEN** reducer ownership rejects the update and the prior planner-owned topic authority is preserved

### Requirement: Real topic planning integrates into the mixed graph off real HITL1

Real topic planning SHALL be selectable only in the mixed implementation map and
SHALL require `bootstrap=real` and `hitl1=real`, because the planner consumes the
real HITL1 profile constraints. Selecting `topic_planning=real` without real HITL1
SHALL fail closed before graph invocation. The normalized topology SHALL add exactly
`topic_planning --exhausted--> blocked/END` and keep the existing
`topic_planning --next--> wave0` and inbound edges unchanged. topic_planning SHALL
remain a non-gated controller node that writes its own route labels and SHALL NOT
import LangGraph or interrupt. The full-fake topic planning path and every other
fake phase SHALL remain unchanged, and the lifecycle result SHALL remain
`implementation_mode=full_fake`.

#### Scenario: Real topic planning requires the real profile chain
- **WHEN** a recipe selects `topic_planning=real` without `hitl1=real` (and thus without `bootstrap=real`)
- **THEN** recipe construction fails with a typed dependency error before the graph is compiled or invoked

#### Scenario: The exhausted route is explicit and minimal
- **WHEN** the mixed graph selects real topic planning
- **THEN** the builder carries a conditional edge `topic_planning -> {next: wave0, exhausted: END}`, topology validation recognizes `exhausted` as terminal `blocked`, and no other topic_planning edge changes

#### Scenario: Full-fake topic planning remains unchanged
- **WHEN** the full-fake graph reaches topic planning
- **THEN** fake topic planning routes `next` without calling a model, writing topic state, or taking the real `exhausted` route, and the topology snapshot is unchanged

#### Scenario: The mixed graph completes through real topic planning
- **WHEN** the mixed graph runs real bootstrap, real HITL1, and real topic planning followed by fake Wave0 onward
- **THEN** a valid plan routes `next` into fake Wave0 and the lifecycle completes with `implementation_mode=full_fake` and no findings or report side effects
