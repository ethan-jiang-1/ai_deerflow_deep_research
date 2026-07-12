## Context

### Verified current behavior

- Change 00 is archived. `agent/src/deerflow_deep_research/runtime/graph_host.py`
  provides a generic action registry, same-namespace lock striping, startup-fingerprint
  verification, and one official checkpointer context per action.
- `agent/src/deerflow_deep_research/runtime/probe.py` registers only
  `infra_probe`; `agent/src/deerflow_deep_research/tool.py` currently accepts only an
  optional `probe_id` and returns lifecycle actions as unavailable.
- `RuntimeAdapter` produces a runtime-only `TrustedRuntimeEnvelope` and
  `runtime/projection.py` can derive a pure `GraphContextView` only after a registered
  handler validates an opaque research id.
- `domain/node_spec.py` already fixes the public node surface: one `NODE_SPEC`, a
  real and fake factory accepting `NodeBuildDependencies`, private typed contracts,
  and explicit registry loading.
- DeerFlow's pinned LangChain/LangGraph stack exposes `ToolRuntime.tool_call_id`,
  accepts tools returning public `Command` values, supports `interrupt()` and
  `Command(resume=...)`, and preserves `ToolMessage.artifact` plus
  `HumanMessage.additional_kwargs` through the Gateway message normalizer.
- The existing Web UI human-input contract is generic. It recognizes a version-1
  `artifact.human_input` request on any `ToolMessage` and returns a real
  `HumanMessage` carrying `additional_kwargs.human_input_response`; no frontend change
  is required.
- The default reflected dispatch currently constructs a fresh probe `GraphHost` per
  invocation. Tests can inject one retained host, but lifecycle actions and memory-mode
  same-process resume require one process-local combined host in normal dispatch.

### Constraints

- Source and tests stay under `agent/`; `backend/` and `frontend/` remain unchanged.
- The `infra_probe` topology, namespace, and public behavior remain independently
  available.
- The graph recipe may be cached, but trusted envelopes, reduced dependencies,
  capabilities, user/thread values, research ids, and checkpointer resources may not
  be cached or checkpointed.
- File-SQLite is the required restart-durable backend. Memory and SQLite memory mode
  are same-process only. Postgres, live Docker verification, launch wrappers, and
  multi-worker coordination remain deferred.
- This change is zero-API: no model, web, MCP, ACP, DeerFlow `task` subagent, or
  sandbox research tool is invoked.
- Full `ResearchState`, work units, evidence, submission authority, and report
  delivery belong to later changes. The skeleton state must be intentionally small
  and replaceable without becoming a second business-state authority.

## Goals / Non-Goals

### Goals

- Freeze one stable logical topology and one implementation-selection mechanism before
  any real node exists.
- Exercise every phase, pass/repair/rerun/stop route, two real LangGraph interrupts,
  deterministic `Send` fan-out/fan-in, lifecycle control action, and terminal state.
- Bridge a nested interrupt to DeerFlow's existing outer human-input card contract and
  resume only from the matching latest `HumanMessage` in trusted runtime state.
- Prove checkpoint isolation, duplicate/replay defenses, status/cancel semantics,
  same-process memory behavior, and file-SQLite process-restart recovery.
- Keep the graph recipe request-independent and keep all request authority outside
  checkpointed state.

### Non-Goals

- No real research logic, embedded node-agent role, LLM call, web access, evidence,
  cache, ledger, report, or sandbox output.
- No final long-term `ResearchState` or migration framework; change 02 owns those.
- No true concurrent cross-process cancellation. `cancel` terminates a checkpointed
  suspended lifecycle; cancellation of a currently executing outer action remains the
  existing DeerFlow/asyncio cancellation path.
- No new config key, mount, database provider, launcher, Docker live smoke, Postgres
  profile, worker-count support, or startup-only reload field.
- No modifications under `backend/` or `frontend/`.

## Decisions

### 1. One explicit topology owns logical phase order

`graph/topology.py` will declare the stable logical nodes and edges. The expected
control flow is:

```text
START -> bootstrap -> hitl1 -> topic_planning -> wave0
                                              ^       |
                                              | repair|
                                              +-------+
wave0(pass) -> wave1 -> wave2_synthesis
                            | targeted-needed
                            v
                    targeted_evidence --repair--> wave2_synthesis
                            |
                            v
                          hitl2
             approve ------+------ rerun ------> rerun -> topic_planning
                |           |
                v           +------ stop -------> END(stopped)
            readiness
            |       |
       repair       ready
            |       |
            v       v
 targeted_evidence  final_delivery -> END(completed)
```

`graph/routing.py` reads typed verdict fields only. It never performs model judgment,
filesystem inspection, or hidden mutable bookkeeping. The topology explicitly lists
package roots; it does not discover nodes from the filesystem.

Alternative considered: let each fake node decide and call its successor. Rejected
because routing would disappear into implementation code and later fake/real swaps
could silently change the workflow.

### 2. Phase packages are real structural surfaces even though behavior is fake

The change creates the eleven canonical node packages, each with `__init__.py`,
`node.py`, `fake.py`, and `contracts.py`; Wave0/Wave1 may additionally own
`subgraph.py`. The package root exports only `NODE_SPEC`.

The implementation map defaults every logical node to `fake`. Selecting `real` for a
node whose later change has not supplied an implementation fails during graph binding
with a typed `implementation_unavailable` error. Mixed-mode tests provide an explicit
test-owned NodeSpec/factory override; production code does not pretend an unavailable
real node exists.

Alternative considered: omit `node.py` or real factories until later. Rejected because
it violates the permanent node-package grammar and would force structural churn on
every replacement change.

### 3. Request-independent graph recipe, request-scoped invocation context

The cached `StateGraph` recipe uses a public LangGraph `context_schema`. Generic node
wrappers read a domain-owned, frozen invocation context containing only:

- the pure `GraphContextView`;
- one reduced `NodeBuildDependencies` entry per logical node/attempt;
- deterministic fake fixture controls;
- protocol-typed capabilities (unused by the fakes).

The research action handler constructs that context after `RuntimeAdapter` and
`project_research_scope()` validate the trusted scope, then passes it through the
public `context=` invocation argument. It is not part of graph state and is therefore
not checkpointed. At node execution, the wrapper selects the implementation, invokes
the NodeSpec factory with that node's reduced dependencies, and calls the resulting
node callable.

`TrustedRuntimeEnvelope`, AppConfig, parent sandbox objects, host paths, raw identity,
outer run ids, and internal checkpoint keys never enter the invocation context.

Alternative considered: rebuild a request-specific graph per action. Rejected because
it discards the request-independent topology cache promised by change 00 and makes
topology identity harder to snapshot. Alternative considered: put dependencies in
graph state. Rejected because they are runtime authority and are not serializable
business state.

### 4. A minimal versioned skeleton state, not the final ResearchState

`domain/skeleton_state.py` will define only fields needed to prove control flow:

- `schema_version`, opaque `research_id`, lifecycle `status`, current `phase`;
- `generation`, bounded repair/rerun counters, deterministic route fixture keys;
- reducer-backed Wave0/Wave1 branch result tuples;
- pending HITL descriptor (`request_id`, phase, generation, input mode/options, and
  the opaque outer-human-message cursor at suspension);
- consumed response request/message ids for replay defense;
- typed terminal reason and a bounded logical execution trace.

No source body, user identity, host path, sandbox handle, AppConfig, checkpointer key,
evidence payload, or report body is stored. Unknown schema versions fail closed before
resume or mutation. Change 02 may replace/extend this schema under an explicit
migration design.

Alternative considered: implement the full planned ResearchState now. Rejected because
its reducers, artifact references, and persistence contract are the explicit scope of
change 02.

### 5. Wave phases prove parallel semantics inside phase-local subgraphs

Wave0 and Wave1 each own a deterministic phase-local subgraph with one dispatcher,
three `Send` branches, a reducer-backed result collection, and one join. The top-level
logical topology still sees only `wave0` and `wave1`; dispatch/join workers are internal
components and never become top-level phases.

The fake branch result contains only a stable branch id and fixture verdict. Result
ordering is normalized before it re-enters the parent state so scheduling order cannot
make snapshots flaky. Phase-local subgraphs use no independent persistent business
state or checkpointer; restart durability in this change is proven at graph-owned HITL
boundaries. Durable work-unit execution remains change 04.

Alternative considered: add dispatcher/join names to the top-level topology. Rejected
because those are reusable implementation components rather than logical phases and
would make later internal worker changes a breaking topology change.

### 6. Nested HITL uses LangGraph interrupt plus DeerFlow's existing message contract

Each HITL node calls public `interrupt()` with a deterministic, versioned request
descriptor. LangGraph checkpoints the suspension before the handler returns control.
The handler then projects the pending descriptor into a `ToolMessage` whose:

- `tool_call_id` is `ToolRuntime.tool_call_id`;
- stable message id equals the research HITL request id;
- `name` is `deep_research`;
- `artifact.human_input` is the existing version-1 `human_input_request` schema with
  source `deep_research`.

The reflected tool returns `Command(update={"messages": [...]}, goto=END)` so the
current lead-agent turn ends after the nested checkpoint is durable. An early
viability test must prove the reflected async tool's `Command`, `ToolMessage`, and
artifact survive the pinned ToolNode/runtime path. Failure of that gate stops the
change and triggers a design revision; upstream code is not edited.

On resume, tool arguments contain only `action` and `research_id`. The handler scans
trusted runtime-state messages from newest to oldest for the latest actual
`HumanMessage` after the suspension cursor. A structured
`human_input_response` payload, when present, must use source `deep_research` and match
the pending request id; its `value` is accepted only because it is attached to that
actual HumanMessage. For a non-card client, a newer visible HumanMessage without
structured metadata may provide its normalized text. Tool arguments, AI messages,
ToolMessages, hidden summaries/dynamic context, pre-suspension messages, mismatched
request ids, empty values, and already-consumed message ids are rejected.

The accepted value is supplied through `Command(resume=...)`. Duplicate or stale
resume calls never advance a second interrupt.

Alternative considered: accept an `answer` tool argument. Rejected because the model
could forge it. Alternative considered: reuse `ask_clarification`. Rejected because
phase agents are forbidden to own HITL and the nested graph needs its own checkpointed
suspension/correlation semantics.

### 7. Four lifecycle actions share one research namespace

The strict tool schema remains `extra="forbid"` and uses bounded action-specific
validation:

- `infra_probe`: optional `probe_id`, no `research_id`;
- `start`: neither id is caller-supplied; the server generates at least 128 bits of
  URL-safe entropy for `research_id`;
- `resume | status | cancel`: require one bounded opaque `research_id` and reject
  `probe_id`;
- unknown bounded actions still return redacted `action_unavailable` before adapter or
  sandbox access.

All research handlers derive the same versioned namespace from trusted user, outer
thread, and research id. `start` refuses an existing namespace rather than resetting
it. `status` uses `aget_state()` only. `resume` requires one pending interrupt.
`cancel` resumes a pending HITL with an internal typed cancel decision so normal graph
routing records a terminal `cancelled` state; completed/stopped/cancelled calls are
idempotent reads, while missing or unsupported states fail closed.

Same-namespace actions remain serialized by GraphHost's single-worker lock. If an outer
tool task is actively executing, DeerFlow run cancellation/ordinary asyncio
`CancelledError` remains the mechanism that aborts it; the control `cancel` action does
not claim cross-task or cross-worker preemption.

Alternative considered: let cancel rewrite checkpoint values with `aupdate_state()`.
Rejected because it could bypass the topology and create a state the graph never
transitioned through.

### 8. One process-local combined GraphHost preserves memory semantics

`runtime/control.py` will build a combined host registering `InfraProbeHandler` plus
the four research handlers. `tool.py` resolves one lazily created process-local host by
default; tests may still inject isolated hosts. The host caches only request-independent
recipes and its memory saver. SQL saver contexts remain per action and close exactly as
in change 00.

This also makes the existing same-process memory revisit claim true for ordinary
reflected `infra_probe` dispatch. The host is not a distributed singleton and does not
change the one-worker readiness rule.

Alternative considered: construct a host per tool invocation. Rejected because memory
checkpoints would be discarded between actions and `resume/status/cancel` could not
work in the supported same-process memory mode.

### 9. Snapshot and E2E contracts are deterministic

`graph/topology.py` exposes a normalized node/edge representation used both to build
the graph and to render a committed Mermaid/text snapshot. Contract tests reject
unreachable nodes, duplicate logical names, implicit node discovery, unexpected edge
changes, or internal Wave dispatch components appearing as top-level phases.

E2E tests run the same public handler/tool surfaces with fixtures for:

1. happy path with two HITL suspensions;
2. Wave0 repair then pass;
3. HITL2 rerun to a second generation;
4. HITL2 stop;
5. durable cancel;
6. stale/wrong-thread/replayed response denial;
7. file-SQLite subprocess restart between interrupt and resume.

Memory tests remain same-process and explicitly assert that restart recovery is not
claimed. No Postgres or Docker daemon is required.

### 10. Entry/configuration impact stays within existing surfaces

No `config.yaml` or `extensions_config.json` key changes. The reflection path remains
`deerflow_deep_research.tool:deep_research_tool`; MCP, ACP, `task` subagents, phase
skills, and DPT bundle files remain unused. The public skill and Agent/SOUL text gain
only lifecycle usage guidance and take effect on the next agent build. Python package
changes use the existing change-00 source-loading/restart boundary. No new
`reload_boundary.STARTUP_ONLY_FIELDS` value is affected.

## Risks / Trade-offs

- **[Risk] Public ToolNode `Command` behavior differs from the focused tool test.** →
  Make reflected-command/artifact propagation the first hard viability gate and stop
  before topology work if it fails.
- **[Risk] Latest HumanMessage selection consumes hidden synthetic context.** → Filter
  summary/dynamic-context markers, require post-suspension ordering, prefer matching
  structured response metadata, and record consumed message ids.
- **[Risk] Phase-local Send subgraphs do not prove crash recovery mid-wave.** → State
  this boundary explicitly; change 04 owns durable work units. Change 01 proves Send
  semantics and restart only at graph-owned HITL checkpoints.
- **[Risk] Minimal skeleton state becomes accidental long-term schema.** → Name and
  version it as skeleton-only, exclude business payloads, and make change 02 explicitly
  own replacement/migration.
- **[Risk] Process-local host/locks are mistaken for multi-worker coordination.** → Keep
  the worker-count readiness gate at exactly one and document no cross-process cancel or
  exclusion claim.
- **[Risk] A real implementation is selected before it exists.** → Resolve the full
  implementation map before invocation and fail closed with the logical node name;
  never fall back silently to fake.
- **[Risk] Topology snapshots become formatting-noise tests.** → Snapshot a normalized
  semantic node/edge representation and generate diagrams from it, not from unstable
  LangGraph debug formatting.

## Migration Plan

1. Add red viability tests for reflected `Command`/human-input artifacts and retained
   process-local host behavior.
2. Add the minimal skeleton contracts, implementation map, topology model, and
   structural registry entries; regenerate the controlled `agent/AGENTS.md` block.
3. Add node packages and deterministic phase-local Wave subgraphs.
4. Add the research graph recipe, lifecycle handlers, latest-HumanMessage correlation,
   and combined host/tool schema.
5. Update public skill/Agent guidance and run unit/contract/graph/integration/E2E,
   file-SQLite subprocess restart, lint/format/lock, architecture, requirement, spec,
   and strict OpenSpec validation.

There is no persistent production migration because no deployed research graph exists.
Rollback removes the active change's new downstream source and entry-text changes; the
change-00 infra probe and main specs remain valid. A checkpoint written with the
skeleton namespace/schema is development-only until this change is archived; unknown
or removed schema versions fail closed rather than being reinterpreted.

## Open Questions

None. The first viability gate may invalidate the chosen outer `Command` bridge; if it
does, implementation stops and this design is revised before any topology work.
