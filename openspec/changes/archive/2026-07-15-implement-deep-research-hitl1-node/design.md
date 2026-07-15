## Context

Change 05 delivered a real bootstrap node that atomically establishes the minimal
research bundle and routes `needs_input -> hitl1`. The fake HITL1
(`graph/nodes/hitl1/fake.py`) already uses the real LangGraph `interrupt()` mechanism,
real `PendingResearchInterrupt` / `AcceptedHumanResponse` types, and real resume
handling through `ResumeResearchHandler`. Only the prompt content and acceptance logic
are fake.

Real HITL1 is the first model-calling node in the graph. It must call the existing
runtime-owned node-agent bridge to generate a structured brief from the original user
question, present that brief to the user through the existing HITL wire protocol, parse
the human response deterministically, and publish a recorded research profile for
downstream planning.

The hard parts are not the question text itself. The hard parts are authority and
durability: partial profile answers must survive checkpoint restart, `profile.json`
must be a real request-bundle artifact rather than an invented `ContentRef`, real HITL1
must receive a real node-agent capability while full-fake stays zero-model, and the
topology must explicitly represent follow-up and blocked paths.

## Goals / Non-Goals

**Goals:**
- Define closed-enum profile contracts that the model cannot silently extend or
  reinterpret.
- Generate a structured brief through the existing `capabilities.run_agent()` protocol.
- Present HITL1 prompts through `interrupt(PendingResearchInterrupt(...))` with the
  existing version-1 human-input wire schemas.
- Parse JSON or free-text human responses deterministically into validated profile
  progress.
- Support restart-durable follow-up interrupts for incomplete answers.
- Write the final profile to `request/profile.json` and checkpoint short fields needed
  by topic planning.
- Swap real HITL1 into the mixed graph while preserving the full-fake E2E path.
- Keep `backend/`, `frontend/`, config examples, extensions config, skills, Agent/SOUL,
  MCP, ACP, and lead-agent middleware unchanged.

**Non-Goals:**
- No topic generation or search execution; change 07 consumes the recorded profile.
- No structured choice UI for HITL1; HITL1 remains `HumanInputMode.TEXT`.
- No HITL2 or scheduled auto-proceed.
- No change to `PendingResearchInterrupt`, `HumanInputRequest`,
  `AcceptedHumanResponse`, or `InternalCancelDecision` wire schemas.
- No new model-execution capability enum member; brief generation uses the existing
  `NodeExecutionCapabilities.run_agent()` protocol.

## Decisions

### Decision 1: Separate final profile from durable partial progress

Use frozen extra-forbid Pydantic contracts in `domain/profile.py`:

| Contract | Purpose |
|---|---|
| `StructuredBrief` | Validated model output for the user-facing draft brief. |
| `PartialResearchProfile` | Durable parsed progress while HITL1 is asking follow-ups. |
| `ResearchProfile` | Final recorded profile written to `profile.json` and checkpoint fields. |

Closed dimensions:

| Dimension | Enum Type | Values |
|---|---|---|
| `depth` | `ResearchDepth` | `quick_overview`, `standard`, `deep_dive`, `exhaustive` |
| `audience` | `TargetAudience` | `layperson`, `practitioner`, `domain_expert`, `executive` |
| `format` | `OutputFormat` | `executive_brief`, `detailed_report`, `annotated_bibliography`, `faq` |
| `cost_tolerance` | `CostTolerance` | `minimal`, `moderate`, `extensive` |
| `time_budget` | `TimeBudget` | `very_quick`, `standard`, `thorough`, `overnight` |

Shared bounded text fields:

- `must_answer`: 1 to 8 concrete questions, each at most 256 chars.
- `scope_boundaries`: at most 2,048 chars.
- `custom_notes`: at most 1,024 chars.
- `schema_version=1`.

`ResearchProfile` may carry missing closed dimensions only when
`degraded_profile=True`. Otherwise the final profile validator requires all closed
dimensions and at least one `must_answer` question. This keeps normal downstream
planning simple while preserving a bounded escape hatch after repeated incomplete
answers.

### Decision 2: Structured brief generation uses `NodeExecutionResult.summary`

HITL1 calls `capabilities.run_agent()` once per brief-generation attempt, with at most
one repair attempt after schema-invalid model output. It builds a bounded
`NodeExecutionRequest` whose objective includes `state["request_text"]` and whose
expected output instructs the agent to return exactly one `StructuredBrief` JSON object
in `NodeExecutionResult.summary`.

The node validates `summary` as JSON with `StructuredBrief.model_validate`. If validation
fails once, HITL1 re-prompts once with failure metadata and the original question. If
validation fails twice, or if `run_agent()` raises / returns a non-success result, HITL1
fails closed before user interruption with:

- `phase_status=TERMINAL`
- `terminal_status=BLOCKED`
- `terminal_reason=GATE_BLOCKED`
- `route=exhausted`

The invalid model output is never presented to the user, written to the checkpoint, or
stored in the bundle.

### Decision 3: Real HITL1 gets real runtime capabilities only in the mixed recipe

The existing full-fake runtime resolver injects `FakeUnavailableCapabilities`, which is
correct for fake nodes. Real HITL1 needs the existing `RuntimeNodeAgentBridge`:

- `ResearchGraphRecipe` records whether the selected implementation map contains
  `hitl1=real` and rejects `hitl1=real` unless `bootstrap=real` is also selected.
- `ResearchActionHandler._context()` constructs a real `RuntimeNodeAgentBridge` only
  when real HITL1 is selected.
- Each bridge invocation uses a zero-tool, one-model-call `ExecutionPolicy`, a small
  wall-time budget, and no web, MCP, ACP, or DeerFlow `task` access. HITL1 may invoke
  the bridge a second time only for structured-brief schema repair.
- The request-bundle writer is constructed only when the real bootstrap bundle root is
  required and established for the same research id.
- Full-fake and fake-HITL1 recipes keep unavailable/test capabilities, and tests assert
  they never call `run_agent`.

This keeps raw model/runtime authority in `runtime/`. HITL1 sees only the pure
`NodeExecutionCapabilities` protocol.

### Decision 4: Follow-up is a checkpointed self-route, not closure state

Incomplete answers cannot be stored in a Python closure because closures do not survive
SQLite restart, process restart, or graph recompilation. HITL1 uses explicit checkpoint
state instead:

1. First visit generates the brief and interrupts with ordinal 1.
2. Resume validates the request id and parses the answer.
3. If incomplete, the node writes `pending_profile` and `profile_followup_round`,
   consumes the response ids, and routes `needs_followup`.
4. The graph follows `hitl1 --needs_followup--> hitl1`.
5. The next visit loads `pending_profile`, computes ordinal 2 from checkpointed
   `execution_trace`, and interrupts with a compact follow-up asking only for missing
   fields.

HITL1 permits at most three user-answer rounds (ordinals 1, 2, 3). If the third answer
is still incomplete, HITL1 records a best-effort `ResearchProfile` with
`degraded_profile=True`, clears `pending_profile`, and routes `accepted`.

### Decision 5: Human response parsing is deterministic and closed

`parse_profile_response(text)` accepts either:

- A compact JSON object with stable machine values, or
- Free text containing explicit machine values or documented deterministic synonyms.

The parser never calls an LLM. Unknown enum values are treated as unset, not coerced. A
value becomes part of `PartialResearchProfile` only if it maps to a closed enum member
or to an explicit custom/free-text field such as `scope_boundaries` or `custom_notes`.

This preserves the requirement that profile values must come from closed enums or an
explicit custom payload, never from model substitution.

### Decision 6: Final profile storage is dual-authority by design

The full final profile is serialized as canonical JSON and written to:

```text
workspace/deep-research/<research_id>/request/profile.json
```

The checkpoint stores only:

- `profile_ref: ContentRef | None`
- `research_depth: str`
- `target_audience: str`
- `output_format: str`
- `cost_tolerance: str`
- `time_budget: str`
- `must_answer_questions: tuple[str, ...]`
- `degraded_profile: bool`
- Transient follow-up fields `pending_profile` and `profile_followup_round`

`profile_ref`, final short fields, and transient progress fields are controller-owned
state. They are listed in `ResearchState`, `ResearchCheckpoint`, `OWNERSHIP_TABLE`, and
controller-authorized reducer checks; they use the local authority-writer guard where
the existing `domain/state.py` policy requires it. `RESEARCH_STATE_SCHEMA_VERSION` stays
at 2 because all new fields have backward-compatible defaults.

### Decision 7: `profile.json` is written by a narrow request-bundle capability

HITL1 must not fabricate a `ContentRef` for a file that does not exist. This change adds
a narrow runtime-owned request-bundle protocol backed by
`agent/src/deerflow_deep_research/runtime/request_bundle.py`:

```text
write_profile(profile: ResearchProfile) -> ContentRef
```

The implementation:

- Reuses the established bootstrap bundle root.
- Writes only under the current research `request/` subtree.
- Uses atomic same-directory replace and content hashing.
- Returns a bounded `ContentRef` with the canonical sandbox path.
- Keeps host paths, locks, file descriptors, parent sandbox, and AppConfig out of node
  contracts, model prompts, and checkpoint state.

The capability is attached only when the selected real HITL1 factory declares it and the
recipe also selects `bootstrap=real`. It is not available to full-fake nodes or later
fake phases.

### Decision 8: HITL1 context is compact JSON inside existing text mode

`HumanInputRequest.context` remains a string capped at 2,048 chars. HITL1 fills it with
compact JSON containing:

- `context_schema_version: 1`
- `brief_summary`
- `proposed_dimensions`
- `required_dimensions`
- `missing_dimensions`
- `valid_options`
- `instructions`

The frontend is not changed. Existing clients can display the JSON/text as plain
context; future clients can parse it for richer controls.

### Decision 9: Real HITL1 uses the same public interrupt exception as HITL fakes

Current architecture policy allows the HITL fake to import exactly
`langgraph.types.interrupt`. Real HITL1 has the same graph-owned reason to call the
public interrupt API. This change extends the exception to graph-owned HITL node
modules while keeping ordinary node modules forbidden from importing LangGraph directly.

The checker should still reject broader LangGraph imports from ordinary node files,
node-to-runtime imports, node-to-agent imports, and sibling-node imports.

### Decision 10: Topology change is explicit and minimal

Real HITL1 adds exactly two route labels:

```text
hitl1 --accepted------> topic_planning
hitl1 --cancel--------> END/cancelled
hitl1 --needs_followup-> hitl1
hitl1 --exhausted-----> END/blocked
```

`needs_followup` is the durable same-phase loop. `exhausted` is for pre-interrupt
brief-generation failure or unrecoverable validation failure. Both are controller routes
from a non-gated node. Gate-kernel route ownership remains unchanged for gated phases.

## Risks / Trade-offs

- **LLM generates a poor brief:** The user can correct it, and the final profile comes
  from validated human input, not the model proposal.
- **Human response remains incomplete:** Follow-up prompts ask only for missing fields;
  after three rounds HITL1 records a degraded best-effort profile.
- **Partial profile lost on restart:** Partial progress is checkpointed before the
  self-route; no closure is used as authority.
- **Request-bundle writer widens authority:** The node receives only a narrow pure
  protocol. Runtime owns host paths and atomic I/O.
- **Topology snapshot changes:** The change explicitly owns the HITL1 self-edge and
  blocked edge, and the snapshot/tests must be updated in the same task group.
- **Checkpoint duplicates short profile data:** The enum fields are small and let change
  07 read planning constraints without loading `profile.json`.
