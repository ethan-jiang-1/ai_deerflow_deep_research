## Context

The checked-in Wave0 and Wave1 phase recipes currently prove a three-way LangGraph
`Send` fan-out and reducer join in
`agent/src/deerflow_deep_research/graph/nodes/{wave0,wave1}/subgraph.py`. Their workers
return `BranchResult` fixtures and their phase wrappers invoke the child graph directly;
there is no immutable work envelope, attempt lifecycle, file validation, or accepted
evidence commit. Gate evaluation is already deterministic and remains the sole phase
routing authority after the phase node returns.

Change 02 reserved small checkpoint slots in `domain/state.py` for pending work, batch
cursor, work metadata/status, and accepted submission refs, and established
`domain/bundle.py` as the path-containment contract. `RuntimeAdapter` already holds the
trusted `workspace_host_path` and parent sandbox in a runtime-only
`TrustedRuntimeEnvelope`; neither value enters graph state or model input. `GraphHost`
serializes one checkpoint namespace only with process-local lock stripes, so that lock
cannot by itself protect a ledger shared by independent Gateway processes.

Two current boundaries require explicit correction rather than assumption. First,
`runtime/projection.py` currently derives phase-agent roots as
`<research_root>/attempts/<attempt_id>`, while the approved work-unit bundle is
`<research_root>/work/<work_id>/<attempt_id>`. Second, the public sandbox providers do
not all share `workspace_host_path`: LocalSandbox and local-container AIO use thread-data
mounts, while E2B, BoxLite, and provisioner-backed AIO report no such host mount. Direct
host I/O is therefore valid only after a runtime capability check proves that the parent
sandbox and host path are the same workspace.

This change implements the approved queue -> work unit -> candidate -> submit -> ledger
mapping with deterministic fixture workers. Later Wave0, Wave1, targeted-evidence, and
rerun changes need to replace only planner/worker content while retaining this kernel.
The public reflection path remains
`deerflow_deep_research.tool:deep_research_tool`; no DeerFlow configuration or upstream
source is changed.

## Goals / Non-Goals

**Goals:**

- Freeze versioned work, attempt, candidate, source/output ref, and submission contracts
  with controller-owned identity and canonical hashes.
- Execute stable bounded `Send` batches, deterministic fan-in, one-way terminal reducers,
  and a generic pending/in-flight drain check.
- Validate candidate identity, schema, path containment, artifact hashes, and source refs
  before a submission can become evidence authority.
- Store accepted records in a sandbox-backed, hash-chained JSONL ledger with one
  controller submit writer, atomic publication, cross-process per-research serialization,
  and deterministic replay across ledger/checkpoint crash windows.
- Exercise the kernel with at least three concurrent Wave0 and Wave1 fixture workers while
  preserving top-level nodes, edges, route labels, lifecycle actions, and mixed/full-fake
  coverage.
- Keep blocking filesystem and lock operations off the async event loop and keep trusted
  host paths inside `runtime/`.
- Fail readiness and runtime execution before mutation when the selected sandbox cannot
  prove the shared-workspace and POSIX transaction primitives required by the store.

**Non-Goals:**

- Real web search/fetch/cache behavior, real evidence extraction, or concrete wave
  evidence floors.
- DeerFlow `task` subagents, MCP, ACP, a second sandbox lifecycle, or a second delegated
  completion path.
- DPT queue/index/status control files, a 20-item active window, dynamic priorities,
  preemption, or late-submit winner semantics.
- A database ledger, distributed consensus across hosts whose shared filesystem does not
  honor POSIX locking/rename semantics, or Postgres-backed action coordination.
- Remote/non-mounted sandbox ledger support; such providers fail closed in this version
  rather than receiving a weaker second submission path.
- Changes to `config.yaml`, `extensions_config.json`, skills, per-user Agent/SOUL files,
  `backend/`, or `frontend/`.

## Decisions

### 1. Separate pure contracts, deterministic policy, graph orchestration, and trusted I/O

The implementation will use these ownership layers:

```text
domain/work_units.py
  frozen Pydantic contracts, enums, canonical hashes/JSONL chain codec, pure protocols

engine/work_units/
  ids.py         deterministic work/attempt allocation
  reducers.py    candidate/status/ref reducers
  validation.py pure validation plan and typed failure aggregation
  kernel.py      batch, submit decision, retry, and drain state machine

graph/components/work_units.py
  reusable internal LangGraph Send/fan-in/submit/drain component

runtime/work_unit_store.py
  workspace-capability check, contained reads, bounded locking, fsync, atomic publish
```

`domain/bundle.py` will add canonical paths for `work-spec.json`, `result.json`,
attempt outputs, `evidence/submissions.jsonl`, the ledger lock, and staging files.
`GraphInvocationContext` will gain two pure protocols: a per-work dependency resolver
that derives `NodeBuildDependencies` from controller-assigned work/attempt ids, and a
controller-only work-unit store capability. The existing phase dependency resolver stays
unchanged. Only the graph/controller component receives the submit/store capability; a
worker receives ordinary `NodeExecutionCapabilities` plus a work-unit-specific
`NodeAgentContext`. Store authority is never placed in that context, child agent state,
tool arguments, or model prompts.

The runtime store derives its host root only from
`TrustedRuntimeEnvelope.workspace_host_path` plus the validated research id, but it may
use that root only after a provider/workspace capability check proves the initialized
parent sandbox sees the same physical thread workspace. Public or model-provided paths
remain virtual refs. This does not create a second sandbox or expose a host path outside
`runtime/`. Canonical ledger encoding and chain verification live in `domain/`, so
`runtime/` does not import inward orchestration from `engine/`.

Alternative considered: let workers call a submit tool. Rejected because it gives an
agent a mutation surface over evidence authority and permits success to depend on prompt
compliance. Alternative considered: put file locking in `engine/`. Rejected because pure
engine code cannot own trusted host paths or blocking runtime I/O.

### 2. Use frozen canonical contracts and controller-generated monotonic ids

All four public work-unit contracts use Pydantic v2 with `frozen=True`,
`extra="forbid"`, explicit schema version 1, bounded strings/collections, and closed
enums. Their stable core is:

- `WorkSpec`: research id, generation, phase, work id, worker role, bounded scope,
  expected result schema/output contract, and `spec_hash`.
- `Attempt`: work id, attempt id, attempt ordinal, spec hash, active/terminal status,
  optional expiry, and controller timestamps.
- `CandidateResult`: repeated trusted identity, result ref/hash/schema, declared output
  refs/hashes, source refs, and a stable `candidate_hash`.
- `SubmissionRecord`: repeated identity/scope, candidate/result/output/source data,
  validator version/check list, submitted timestamp, previous record hash, and record
  hash.

Canonical JSON uses UTF-8, sorted keys, compact separators, explicit enum values, and no
NaN/Infinity. Hashes use SHA-256 with a type/version domain separator and the existing
`h_<base64url-no-padding>` representation. A spec hash excludes only `spec_hash`; a
candidate hash excludes only `candidate_hash`; a record hash excludes only
`record_hash`. The submitted timestamp and previous hash are controller fields, so
same-attempt replay compares a stable candidate fingerprint before considering those
ledger-assigned values.

The controller allocates deterministic ids from checkpointed generation/phase ordinals.
It allocates every attempt before dispatch, so parallel workers cannot race id creation.
A retry retains the original `WorkSpec` and spec hash but consumes the next attempt
ordinal. Workers receive identity as read-only input and may only return a candidate for
that exact attempt. `project_work_unit_agent()` derives the virtual attempt root as
`<research_root>/work/<work_id>/<attempt_id>` from validated controller ids; it does not
reuse the current phase-level `<research_root>/attempts/<id>` path.

Alternative considered: UUIDs generated inside each worker. Rejected because restart
would create new identities for the same graph step and make replay/conflict detection
ambiguous.

### 3. Extend ResearchState compatibly and keep the child batch bounded

Change 02 already reserved the work block. Change 04 keeps
`RESEARCH_STATE_SCHEMA_VERSION = 2` and adds only optional/defaulted fields, so existing
version-2 full-fake checkpoints remain readable. Unknown or truly incompatible schema
versions continue to return `schema_unsupported`; this is compatible schema evolution,
not silent reinterpretation. The parent carries small controller projections only:

- immutable `work_specs_by_id` metadata/hash refs;
- bounded `attempts_by_id` terminal/aggregate history and `work_status_by_id`;
- `batch_cursor`, `next_work_ordinal`, and `next_attempt_ordinal`;
- bounded terminal failure summaries and `accepted_submission_refs`.

The reusable child component uses a typed size-bounded `WorkUnitComponentState` for the
current replay unit, including pending work, in-flight/active attempts, and
`CandidateResult` refs reduced by `(work_id, attempt_id)`. Candidate bodies and output
bodies stay in the sandbox. Transient channels are discarded when the child returns, so
long research histories do not accumulate every candidate in the parent checkpoint.
Under the current builder, Wave subgraphs are
manually invoked inside the wrapped top-level node and do not receive the parent's saver.
Change 04 therefore compiles the child with checkpointing explicitly disabled and treats
the bounded Wave node as the replay unit; it does not claim durable nested candidate
checkpoints. The parent receives only the resulting controller update.

Field ownership becomes specific rather than treating controller and gate as one broad
authority set:

- controller planner: specs, pending work, id cursors, and new attempts;
- worker reducer: current-batch candidate channel only;
- deterministic submit controller: attempt terminal state and accepted refs;
- gate: route, gate feedback, gate attempts, repair budgets, and phase transition;
- planner/worker/repair agents: no checkpoint or ledger authority fields.

Reducers preserve same-hash idempotency, reject different-hash conflicts, forbid
terminal downgrade, and dedupe accepted refs. A single submit-node update changes the
attempt to submitted and adds its accepted ref together; no checkpoint is intentionally
written with only one of those fields.

Alternative considered: keep all candidate JSON in parent `ResearchState`. Rejected
because the checkpoint has a hard 64 KiB bound and candidate histories would grow with
every retry and wave.
Alternative considered: claim a phase-scoped child checkpoint while manually invoking
the compiled child. Rejected because the pinned LangGraph runtime only inherits a parent
checkpointer when the subgraph is directly composed as a graph node; the current wrapper
does not expose its saver to a manual child invocation.

### 4. Implement one reusable bounded batch state machine

The internal component has deterministic steps:

```text
load/verify ledger -> materialize deterministic specs -> allocate deterministic batch
                   -> reconcile allocated attempts -> Send only unaccepted workers
                   -> reduce candidates -> submit in stable order -> drain
                   -> next batch | return to phase gate
```

The construction-time policy supplies `max_concurrency`; the change-04 fixtures use 3.
The dispatcher selects stable pending order starting at `batch_cursor`, allocates active
attempts, and emits no more than the limit. Worker completion order is irrelevant because
the reducer sorts by identity before submit. Submit processes candidates in that same
stable order, but each ledger commit is independently idempotent.

Allocation is deterministic from the last parent checkpoint. If a process dies after a
ledger commit but before the parent state update, replay regenerates the same ids,
reconciles them against the ledger before any `Send`, and skips the accepted attempt. If
no record exists, the bounded step may re-execute that non-terminal attempt. Fixture
planning is deterministic in change 04; later model-backed planners must checkpoint
their immutable specs before handing them to this kernel.

`drain` is structural only: pending and in-flight must both be empty before the outer
phase wrapper invokes its existing gate. Failed/timed-out/cancelled attempts remain
visible to gate rules, so structural drain cannot create evidence or imply pass.

The current `_node_wrapper` evaluates gate rules against the input `state`, before
LangGraph applies the node's returned reducers. Change 04 adds a pure reducer-preview
function: it validates an explicit allowlist of gate-readable work/status/accepted-ref/
failure fields, applies their real reducers in memory, and passes that post-work view to
the gate. It deliberately excludes `phase`, `route`, `execution_trace`, fixture visit
counters, and gate-owned fields. Otherwise `FixtureSequenceRule.completed_visits()`
would observe the current trace too early and skip to the next fixture outcome. The
wrapper still returns one combined work plus gate update for a single checkpoint
transition. This prevents a one-step lag without mutating the checkpoint outside
LangGraph or changing fixture indexing.

Wave0 and Wave1 will consume the same component with different deterministic fixture
spec factories. Their top-level logical names and conditional edges remain unchanged.
Targeted evidence and rerun keep their current fake implementations in this change and
must adopt this component in their owning changes rather than introduce another path.

Alternative considered: a generic global queue service. Rejected because demand is
phase-local, control truth already belongs to the graph checkpoint, and a service would
add a second business-state authority.

### 5. Validate files through a runtime-owned read plan

The pure validator first builds an ordered validation plan from trusted state, the
canonical spec, active attempt, and candidate. The runtime store executes only the
requested contained reads and returns bytes/stat metadata; the pure validator then
checks hashes and schemas. Validation covers:

1. research/generation/phase/work/attempt/role identity;
2. contract and result schema versions;
3. `work-spec.json` canonical bytes and spec hash;
4. exact `result.json` placement and expected result schema;
5. every declared output under `outputs/`, non-empty, and hash-matching;
6. every source ref's canonical URL, contained cache/fetch ref, and matching hash;
7. candidate hash and uniqueness against accepted records.

Host path resolution uses the trusted workspace root, `Path.resolve()` containment, and
descriptor-relative/no-follow opens where the platform supports them. A symlink escape,
path swap detected by stat checks, missing/empty file, unsupported schema, or mismatch
returns a closed typed failure code. All blocking reads and hashing run in
`asyncio.to_thread`.

The controller writes canonical `work-spec.json` before dispatch. Fake workers write
only deterministic `result.json`, bounded outputs, and fixture source refs through a
worker-scoped artifact capability rooted at `work/<work_id>/<attempt_id>`. They do not
call sandbox research tools, models, web APIs, MCP, ACP, or DeerFlow `task`. Worker
summary text is ignored by submit.

Alternative considered: accept `NodeExecutionResult.artifact_refs` without rereading
files. Rejected because a ref proves only that a worker named a path; it does not prove
identity, containment, schema, or content hash.

### 6. Use a logically append-only JSONL hash chain with atomic whole-file publication

The ledger is
`workspace/deep-research/<research_id>/evidence/submissions.jsonl`. Each line is one
canonical `SubmissionRecord` plus `\n`. On every submit, the store acquires an exclusive
lock for that research, parses every existing line, validates schema and newline
termination, verifies the complete hash chain, and searches the work/attempt identity.
Hard per-record, record-count, and total-ledger byte limits are checked before parsing
and before constructing replacement bytes.

If no record exists, the store constructs the next record using an injected UTC clock,
writes `old_bytes + new_line` to a unique same-directory staging file with mode `0600`,
flushes and `fsync`s it, atomically replaces the ledger, and `fsync`s the evidence
directory before releasing the lock. This is logically append-only even though physical
publication rewrites the complete file. A reader observes either the previous complete
ledger or the next complete ledger, never a partial line. Stale staging files are
non-authoritative and are removed under the lock.

If the identity already exists, an equal stable candidate fingerprint returns the
existing record as idempotent replay. A different fingerprint is a conflict. Existing
records are never edited, truncated, reordered, or superseded.

Alternative considered: direct `O_APPEND` JSONL writes. Rejected because a process crash
can leave a partial final line and because append alone does not give compare-and-set
semantics for two processes. Alternative considered: a separate SQLite/Postgres ledger.
Rejected for this change because approved evidence/ledger storage is the sandbox file
system and a second database would couple evidence authority to deployment provider
configuration.

### 7. Bridge the ledger/checkpoint gap with an explicit replay matrix

The ledger and checkpoint deliberately remain separate authorities; no cross-store ACID
claim is made. The commit order is ledger first, then one graph state update. On each
replay, the store first verifies the ledger, deterministic controller allocation
recreates the current attempt identities, and reconciliation runs before worker dispatch
and again before submit.

| Durable state | Ledger state | Reconcile action |
| --- | --- | --- |
| regenerated/active attempt, no record | valid ledger without identity | execute or revalidate candidate and append once |
| regenerated/active attempt, matching record, no accepted ref | ledger ahead of checkpoint | skip worker, reuse record, publish missing submitted/ref update |
| submitted status and accepted ref, matching record | both agree | skip worker and submit idempotently |
| any state, same identity with different candidate fingerprint | divergent replay | fail closed with conflict |
| submitted status or accepted ref, no matching valid record | checkpoint ahead/corrupt evidence | fail closed; never recreate from state alone |
| staging file only | no published record | ignore/clean staging and treat as no record |

Fault injection points are named around: after the last parent checkpoint/before
accepted-ref publication, before staging write, after staging fsync, after atomic ledger
replace, after directory fsync, before submit-node return, and after returned state
update. Tests assert the matrix rather than depending on timing.

An already accepted attempt is never re-executed. A non-terminal attempt with no
accepted record may replay the same graph step and produce the same candidate. Explicit
failure, timeout, cancellation, or expiry closes that attempt; repair allocates a new id.
Late candidates for a closed attempt fail closed.

Alternative considered: checkpoint accepted intent before ledger publication and repair
the ledger from checkpoint. Rejected because it would let control state mint evidence
without revalidating the artifact authority.

### 8. Serialize independent processes with a per-research POSIX lock

`runtime/work_unit_store.py` uses a stable lock file in the research evidence directory
and `fcntl.flock(LOCK_EX)` around ledger read, chain validation, identity comparison,
staging cleanup, and atomic publication. The lock path is derived from the trusted host
root and validated research id; caller input cannot choose it. Separate research roots
therefore proceed independently.

Lock acquisition uses `LOCK_NB` retry with an injected monotonic deadline and returns a
typed `work_unit_store_busy`; it never leaves an indefinitely blocked worker thread.
Acquisition and the size-bounded commit execute off the event loop. Once atomic commit
work starts, cancellation waits for that bounded section to release the lock and then
re-raises `CancelledError`; if the ledger committed, replay repairs the absent checkpoint
update. The process-local `GraphHost` namespace lock remains useful but is not treated as
the cross-process guarantee.

The supported first-version race contract is multiple independent processes sharing a
POSIX workspace where advisory locks, same-directory atomic rename, and directory fsync
are honored. Runtime initialization verifies both those primitives and that the parent
sandbox uses the same physical thread workspace as the trusted host path. LocalSandbox
and locally mounted AIO are eligible; E2B, BoxLite, provisioner-backed AIO, custom
providers, and filesystems without verifiable semantics fail closed in this version.
Doctor includes this in `runtime_ready`. A distributed/remote store adapter remains
future work.

`WorkUnitStoreError` is a runtime-owned typed exception. The reflected tool catches it
alongside existing runtime/host errors and projects two new
`InfrastructureResultCode` values: `work_unit_storage_unavailable` for an unsupported
workspace contract, and retryable `work_unit_store_busy` for lock-deadline exhaustion.
Neither path writes graph state or converts the failure into a gate/business terminal.
Provider/checkpointer resources still close through the existing `GraphHost` context.

Alternative considered: rely on `GATEWAY_WORKERS=1` and the existing lock stripe.
Rejected because tests and operational races can involve separate process instances, and
the plan requires the same research/attempt to have at most one accepted winner now.

### 9. Preserve graph, gate, and extension boundaries

Only Wave0 and Wave1 internal recipes change. Their plan/dispatch/worker/submit/drain
steps remain internal components, not entries in `LOGICAL_NODES` or the node registry.
The existing gate adapter runs only after drain and still writes `route`; `_route()` and
all top-level conditional edges remain unchanged. Gate rules receive a pure
reducer-previewed post-work state so current submissions and terminal failures are
visible in the same transition. Full-fake and mixed graphs continue to use the same
`start | resume | status | cancel` lifecycle handlers.

Fixture execution now has bounded file side effects: controller-assigned attempt
artifacts, the validated submission ledger, and its lock/staging files. It still creates
no fetched cache, synthesis, review, or final report and performs no API/model calls.
Tests use temporary trusted workspaces and remove them as fixtures.

No extension surface changes: `config.yaml -> tools[name=deep_research]`,
`config.yaml -> tool_groups[name=deep-research-control]`,
`extensions_config.json -> skills.deep-research-controller.enabled`, the public skill,
the per-user Agent/SOUL, MCP, ACP, and lead-agent middleware are untouched. This is a
source-only next-agent-build change. No `reload_boundary.STARTUP_ONLY_FIELDS` value,
mount, package import path, or dependency changes. There is no configuration-mandated
restart, but a running non-reload Gateway must restart/redeploy to import the new Python
modules.

## Risks / Trade-offs

- [Whole-file ledger publication is O(n)] -> The first-version fixture and early real
  workloads are bounded; validate size and record-count limits. A later capability may
  introduce a versioned database/segment adapter without changing submission semantics.
- [POSIX lock/rename semantics vary on distributed filesystems] -> Fail store
  initialization and doctor readiness when workspace identity or primitives cannot be
  established; claim only the tested shared-POSIX mounted-workspace contract.
- [Cancellation can occur while a worker thread is committing] -> Shield/wait for the
  bounded atomic section, release the lock, re-raise cancellation, and rely on ledger-
  ahead replay if publication completed.
- [A malicious worker may try symlink or path-swap attacks] -> Resolve against the
  trusted root, use no-follow/descriptor-relative reads and stat verification, and fail
  closed on any ambiguity.
- [Additive state fields could accidentally reinterpret an old checkpoint] -> Keep schema
  version 2 only because every new field is optional/defaulted and old fake nodes never
  wrote overlapping meanings; add old-checkpoint resume fixtures and continue to reject
  unknown/incompatible versions.
- [Manual child invocation cannot inherit the parent checkpointer] -> Make the Wave node
  the explicit replay unit, disable child checkpointing, use deterministic allocation,
  and reconcile the ledger before redispatch rather than claiming unsupported durability.
- [Stale staging or lock files may remain after process death] -> They are never evidence
  authority; clean staging under the next acquired lock and retain the stable lock file.
- [Controller timestamps make raw record bytes non-repeatable] -> Compare the stable
  candidate fingerprint before record construction and inject the clock in tests; replay
  returns the existing timestamp/hash.

## Migration Plan

1. Add red unit/contract tests for schemas, hashes, reducers, validation denials, replay
   matrix, atomic publication, process races, cancellation, and drain behavior.
2. Add `domain/work_units.py`, compatibly extend version-2 `ResearchState`, declare every
   new field's writer/reader/reducer, align work-unit projection, and extend bundle paths.
3. Implement pure domain ledger encoding/verification, engine
   allocation/reducer/validation logic, provider/workspace readiness classification, and
   the runtime-owned bounded store with fault-injection seams.
4. Build the reusable internal component, integrate Wave0 then Wave1 fixture workers,
   and preserve the topology snapshot and gate routes.
5. Run full fake and mixed graph suites, durability/race tests, viability tests, format,
   architecture/spec/requirement governance, and update `agent/README.md`,
   `agent/AGENTS.md`, and the project-structure registry/generated block.

Deployment is source-only and takes effect on the next agent build; restart/redeploy a
running non-reload Gateway to import it. Existing version-2 full-fake checkpoints remain
readable because new fields default empty and retain prior meanings. Rollback code ignores
those optional fields but cannot interpret the new fixture ledger as completed old-style
branch work; rollback therefore uses a fresh research run and leaves ledger files intact
for diagnosis rather than deleting evidence authority.

## Open Questions

No blocking decision remains for change 04. Later changes may decide whether production
scale warrants a segmented/database ledger adapter, whether a non-POSIX distributed
or non-mounted sandbox needs an external transaction service, and what phase-specific
evidence floors apply; none changes the first-version mounted-workspace submit authority
or replay contract.
