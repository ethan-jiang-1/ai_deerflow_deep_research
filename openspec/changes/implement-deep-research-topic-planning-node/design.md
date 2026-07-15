## Context

Change 06 delivered a real HITL1 node that records a validated research profile as
checkpoint short fields (`research_depth`, `target_audience`, `output_format`,
`cost_tolerance`, `time_budget`, `must_answer_questions`, `degraded_profile`) plus a
`profile_ref`. The topic planning node (`graph/nodes/topic_planning/`) is still the
change-01 stub: `node.py` is the `UNAVAILABLE_REAL_FACTORY` sentinel
(`domain/node_spec.py:68`) and `fake.py` returns a hardcoded `route="next"`. Its
`NODE_SPEC` declares no capabilities, its `contracts.py` only models
`route="next"`, and there is no `prompts.py`.

Real topic planning is the second model-calling node. It must turn the confirmed
profile into a stable topic registry and a must-answer coverage map that Wave0
(change 08) can consume, without letting the model author the registry format,
mutate state, or produce work units.

The hard parts are boundary and convergence: topics must be deterministic and
stable, coverage must be provable, the planner must consume the profile without a
new read authority, and the topology must represent the blocked path without
inventing a gate that does not fit this node.

Two verified facts reshape the original plan:
- topic_planning is **non-gated** today (`engine/gate_fixtures.py:179-184`
  explicitly excludes it), with a single direct `topic_planning -> wave0` edge
  (`graph/builder.py:161`). There is no repair edge and no `GateDefinition`.
- There is **no profile read-capability**: `RequestBundleStoreProtocol`
  (`domain/profile.py:130`) is write-only, and change-06 Decision 6 deliberately
  left topic planning to read checkpoint short fields instead of `profile.json`.

## Goals / Non-Goals

**Goals:**
- Generate a validated structured topic plan through the existing
  `capabilities.run_agent()` protocol from the checkpointed profile.
- Deterministically materialize a stable, bounded topic registry and a
  must-answer coverage map; enforce id/slug stability, dedup, overlap, empty
  coverage, and over-expansion.
- Bound repair to one re-prompt and fail closed to a terminal route on
  non-convergence.
- Store the validated topic registry as bounded planner-owned checkpoint state
  that Wave0 can read without a sandbox round-trip.
- Swap real topic planning into the mixed graph while preserving the full-fake
  path, the three-authority boundary, and the version-2 checkpoint.
- Keep `backend/`, `frontend/`, config examples, extensions config, skills,
  Agent/SOUL, MCP, ACP, and lead-agent middleware unchanged.

**Non-Goals:**
- No Wave0 `WorkSpec` generation or source search (change 08); topic planning
  produces no `WorkSpec` and declares no `WORK_UNIT_CONTROLLER`.
- No rerun diff/invalidation planning (change 14).
- No HITL interrupt — topic planning never suspends and imports no LangGraph.
- No topic/seed artifacts written to the sandbox in this change.
- No reading of `request/profile.json`; `scope_boundaries`/`custom_notes` are not
  consumed by the planner in v1 (deferred).
- No change to `PendingResearchInterrupt`, the reflection tool path, identity
  derivation, or the request-bundle profile writer.

## Decisions

### Decision 1: Non-gated controller node with bounded inline repair, not a gate

topic_planning stays non-gated and writes its own route, exactly like bootstrap
and HITL1. The real factory calls `run_agent`, validates/materializes the plan,
and on failure re-prompts once; a second failure fails closed to `exhausted`.

Why not a gate: the gate kernel (`engine/gate_kernel.py`, `domain/gate.py`) is
shaped around work-unit completion, fixture-sequence indexing, and
repair-budget/fatigue semantics for gated phases (wave0/wave1/...). topic_planning
is excluded from `build_fixture_gate_defs()` and has no `WorkUnitGateView`. Adding
a `GateDefinition` here would pull in repair-budget/attribution machinery that
does not map to "the model emitted a bad topic plan." The hitl1 precedent
(`hitl1/node.py` `_generate_brief`, one repair then `_exhausted_update`) is the
correct, minimal pattern.

Alternative considered: add a real `GateDefinition` for topic_planning plus a
`repair` self-edge. Rejected — wrong semantics, larger topology churn, and it
would entangle planner validation with gate-attempt/fatigue state.

### Decision 2: Read profile constraints from checkpoint short fields, not profile.json

The planner objective is built from the controller-owned fields already in
`ResearchState`: `request_text`, the profile enum short fields
(`research_depth`, `target_audience`, `output_format`, `cost_tolerance`,
`time_budget`), `must_answer_questions`, and `degraded_profile`.
topic_planning reads them off the `state` mapping passed to `run(state)`, the
way `hitl1/node.py:152` reads `request_text`. `request_text` is included so the
planner has the original research question for context beyond the structured
profile dimensions.

**Empty `must_answer_questions` fallback:** `ResearchProfile.must_answer` has
`min_length=1`, so a non-degraded profile always has ≥1 question. However, when
`degraded_profile=True` the model validator skips the completeness check
(`profile.py:120-127`), and `must_answer_questions` may be empty. In that case
the planner SHALL treat `request_text` as a synthetic single must-answer
question for coverage binding, so the materializer can still validate a
covering plan. The prompt SHALL include a note that the profile is degraded and
the original request text is the authoritative question.

**`degraded_profile` handling:** When `degraded_profile=True`, the prompt SHALL
instruct the model to plan broader, more conservative topics that do not
depend on precise profile completeness. The planner SHALL still produce a
valid `TopicPlan` bound by the same hard checks; degraded mode relaxes only
the model's internal assumptions, not the structural validation.

Why: `RequestBundleStoreProtocol` is write-only by design (change-06 Decision 6
reserved checkpoint reads for change 07 to avoid a sandbox round-trip and a second
read authority). topic_planning therefore declares **no** `REQUEST_BUNDLE` and
needs no new read method. `scope_boundaries`/`custom_notes` live only in
`profile.json` and are intentionally not consumed in v1 (surfacing them would
require either a new short field or a read capability — deferred).

Alternative considered: add `read_profile()` to the request-bundle protocol.
Rejected — widens authority against the approved design and adds a sandbox
round-trip the architecture explicitly avoids.

### Decision 3: Validated topic registry is bounded planner-owned checkpoint state, not a file

The materialized topic registry and coverage map are stored as bounded
planner-owned fields in `ResearchState`/`ResearchCheckpoint` (`topic_refs` and
`topic_registry`, under PLANNER ownership). No sandbox file is
written and no `ContentRef` is fabricated.

Why: topics are small control/planning data, not large research content, so the
checkpoint is the correct authority (the "large content out of checkpoint" rule
targets web pages/reports, not a bounded topic plan). This avoids three costs the
change-06 archive exposed: fabricating a `ContentRef` for a file (forbidden),
introducing a new writer capability/store, and adding a bundle subtree. Wave0 reads
topics from state with no round-trip. If a later phase needs topic files, change 08
can materialize them from the checkpointed plan.

Alternative considered: write `request/topics.json` through a new narrow
planning-bundle writer. Rejected — unnecessary new authority and artifact for v1.

### Decision 4: One model call per attempt, one repair, then fail closed

Each planning attempt is one `run_agent` invocation under a zero-tool, one-model-call
`ExecutionPolicy` mirroring HITL1's (`runtime/research.py:148-172`:
`max_model_calls=1`, empty `allowed_tool_names`, small token/wall-time budget). On
schema/coverage validation failure the node re-prompts once with compact failure
metadata and the original profile constraints; on a second failure, or if
`run_agent` raises/returns non-success, the node fails closed before any state
write with `route=exhausted`, `phase_status=TERMINAL`, `terminal_status=BLOCKED`,
`terminal_reason=GATE_BLOCKED`. Invalid model output never reaches Wave0 or the
checkpoint.

`terminal_reason=GATE_BLOCKED` is reused from change-04's gate-fatigue semantics
even though topic_planning is non-gated. This is the established pattern for
non-gated controller nodes that exhaust their bounded repair: HITL1 already uses
`GATE_BLOCKED` for brief-generation exhaustion (change-06 Decision 5).
`REPAIR_EXHAUSTED` is retained in the enum for compatibility but is no longer
produced; `GATE_BLOCKED` is the canonical terminal reason for any bounded-repair
exhaustion regardless of whether the node uses the gate kernel.

### Decision 5: Deterministic materializer owns stability and hard checks

A pure function (not the LLM) converts the validated `TopicPlan` into the registry:
it derives a stable slug from each topic's validated title/scope, deduplicates by
slug, rejects overlapping scopes, and builds a must-answer coverage map binding
each root question to ≥1 topic. Hard checks reject empty coverage, duplicate
topics, scope overlap, and over-expansion beyond a bounded topic count (≤8). The
model never selects ids/slugs or serializes the registry; it only proposes scoped
topics, which the materializer normalizes.

### Decision 6: Closed topic contracts under domain/topics.py

Frozen extra-forbid Pydantic contracts (matching `domain/profile.py`): a
`ResearchTopic` (bounded title/scope, must-answer bindings, search dimensions,
exclusions) and a `TopicPlan` (bounded topic tuple + schema version). Unknown
fields, oversized text, missing required fields, and out-of-range counts are
rejected at validation. A deterministic parser validates the model `summary` into a
`TopicPlan`, the same way `parse_brief_output` validates a `StructuredBrief`.

### Decision 7: Real topic planning only in the mixed recipe, chained off real HITL1

`ResearchGraphRecipe.create` (`runtime/research.py:122-145`) gains
`topic_planning_real` detection and rejects `topic_planning=real` unless
`hitl1=real` (which already requires `bootstrap=real`), because the planner
consumes the real profile that only real HITL1 records.

Since `topic_planning=real` always implies `hitl1=real`, the existing
`requires_node_agent_bridge` flag is already True and the single
`RuntimeNodeAgentBridge` created in `_context()` (`runtime/research.py:280-315`)
serves both nodes. The bridge's `ExecutionPolicy` (zero-tool, one-model-call,
bounded tokens/wall-time) is a shared upper bound; hitl1's brief generation and
topic_planning's plan generation both fit within it. The policy name
(`"hitl1-structured-brief"`) is retained as-is; it accurately reflects the
policy's origin while remaining a valid enforcement envelope for topic planning.
If a later change needs materially different policy parameters for the two
nodes, the recipe can construct separate bridges keyed by logical node name.

Full-fake and fake-topic-planning recipes keep unavailable/test capabilities
and never call `run_agent`.

Alternative considered: allow real topic planning with fake HITL1. Rejected — fake
HITL1 records no profile, so there are no real constraints to plan from.

### Decision 8: Minimal topology change — add only `topic_planning --exhausted--> blocked`

The single direct edge `topic_planning -> wave0` (`graph/builder.py:161`) becomes a
conditional edge `{next: wave0, exhausted: END}`, and `NORMALIZED_EDGES`
(`graph/topology.py`) gains exactly `topic_planning --exhausted--> blocked`.
Inbound edges (`bootstrap/hitl1 -> topic_planning`, `rerun -> topic_planning`) and
the `next` route are unchanged. This mirrors change-06 Decision 10 (explicit,
minimal route addition).

When `rerun` (change 14) routes back to `topic_planning` in a later generation,
the planner re-executes against the same profile. The new plan overwrites the old
via `last_write_wins` on `topic_refs` and `topic_registry`. Since the profile is
unchanged, re-planning is deterministic enough: the coverage and bounds are
re-validated, and the materializer guarantees stable ids/slugs for identical
topic proposals. Rerun diff/invalidation logic (which topics changed, which
Wave0 work to redo) is deferred to change 14.

### Decision 9: No new NodeCapability

topic_planning needs only the existing `NodeExecutionCapabilities.run_agent()`. It
keeps `capabilities=frozenset()` (as today) and declares no `REQUEST_BUNDLE`,
`BOOTSTRAP_BUNDLE`, or `WORK_UNIT_CONTROLLER`. The node-wrapper guards
(`graph/builder.py:53-76`) ensure an undeclared store is never injected and a
declared-but-missing one fails closed — so the planner cannot accidentally receive
the request-bundle or work-unit controller.

### Decision 10: Single planner authority; no second controller

topic_planning is the sole `WriterRole.PLANNER` writer of topic registry/coverage
state. Profile fields stay controller-owned, work status stays work-unit-owned, and
the submission ledger stays the sole evidence authority. No second phase cursor,
status file, or persistent business-state authority is introduced; the bounded
topic data is the only new planner-owned checkpoint surface.

## Risks / Trade-offs

- **LLM produces overlapping or low-coverage topics:** the materializer's hard
  checks reject exact scope duplication and require full must-answer coverage;
  semantic overlap (different scope strings describing the same research area)
  is not detected in v1. One repair re-prompts with the specific failures, then
  the node fails closed to `exhausted`. → No structurally invalid plan reaches
  Wave0; residual semantic overlap is bounded by the topic cap and must-answer
  bindings and can be handled by downstream dedup in Wave0.
- **Over-expansion:** a bounded topic cap (≤8) plus per-topic text bounds keeps
  the checkpoint small and the plan focused. → Hard reject past the cap.
- **Unstable topic ids across repair:** ids/slugs are derived deterministically by
  the materializer, not chosen by the model. → Stable registry per validated plan.
- **Checkpoint growth:** the topic structure is bounded (count + per-field caps)
  and stays well under the existing checkpoint-size bound; schema version is
  unchanged. → New fields default empty for old checkpoints.
- **Real topic planning selected without a real profile:** the recipe rejects
  `topic_planning=real` unless `hitl1=real`. → Fails before graph invocation.
- **Repair never converges:** bounded to one retry, then terminal `blocked`. → No
  infinite loop; lifecycle remains resumable/cancelable.
- **Degraded profile with empty must-answer questions:** when `degraded_profile=True`
  and `must_answer_questions` is empty (allowed by `ResearchProfile`'s degraded-path
  validator skip), the planner falls back to `request_text` as a synthetic
  must-answer question for coverage binding. → The prompt instructs the model to
  plan broader topics, and coverage is validated against the synthetic question.
  Generation quality degrades gracefully rather than failing closed.

## Migration Plan

None. This extends the zero-API `implementation_mode=full_fake` skeleton. New
checkpoint fields default to empty/false and are backward-compatible with
version-2 checkpoints; no data migration, no config change, no restart beyond
importing new Python source on the next agent build. Rollback is `git revert` of
the change; the full-fake path is never altered.

## Open Questions

- Whether Wave0 (change 08) will need topics persisted as sandbox files rather
  than checkpoint state. Deferred — v1 uses checkpoint; change 08 can materialize
  files from the checkpointed plan if needed.
- Whether `scope_boundaries`/`custom_notes` should reach the planner. Deferred —
  would require a new short field or a profile read capability; not needed for v1
  coverage/dimension-based planning.
