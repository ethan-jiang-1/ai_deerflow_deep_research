## Why

Wave0 and Wave1 currently prove three-branch `Send` fan-out/fan-in, but their fake
workers and submit steps do not establish the production authority boundary between a
worker candidate and accepted evidence. Every later real research phase needs one
shared, crash-replayable work-unit kernel before it can safely treat delegated output as
gate-readable evidence.

## What Changes

- Define frozen, versioned `WorkSpec`, `Attempt`, `CandidateResult`, and
  `SubmissionRecord` contracts. The controller assigns logical work and attempt ids and
  the immutable spec hash; planners, workers, and repair agents cannot allocate or
  rewrite those identities.
- Replace the fixed fake join with a reusable phase-local work-unit component that owns
  typed pending, in-flight, terminal, batch-cursor, and concurrency-limit state. It
  dispatches bounded LangGraph `Send` batches, reduces candidates deterministically,
  and creates a fresh attempt id for every retry.
- Add deterministic submit validation for research/generation/phase/work/attempt
  identity, immutable spec hash, candidate schema/version, attempt-root containment,
  result and output file existence/hash, and source-reference integrity. Worker text
  without the declared result and files is rejected.
- Select a sandbox-backed append-only JSONL ledger with a hash chain as the evidence
  authority. The controller submit path is its sole writer; accepted references are
  published to checkpointed `ResearchState` only for validated records, and gates read
  accepted submissions rather than worker text, file presence, or run events.
- Make ledger publication atomic under a per-research cross-process file lock, with
  idempotent reconciliation for crashes between ledger publication and checkpoint
  publication. Same-record replay repairs missing checkpoint refs; divergent replay or
  checkpoint refs without a matching ledger record fail closed.
- Require a verified shared-workspace capability before host-side atomic ledger I/O:
  the trusted thread workspace and parent sandbox must expose the same physical files
  and the filesystem must honor bounded POSIX locking, same-directory replace, and
  durability sync. Unsupported remote/non-mounted providers fail readiness and runtime
  submission before work starts instead of splitting worker content from ledger truth.
  Runtime refusal uses explicit `work_unit_storage_unavailable`; bounded lock contention
  uses retryable `work_unit_store_busy`. Both return without checkpoint mutation.
- Enforce one-way attempt lifecycle semantics for failure, timeout, cancellation, and
  expiry. Expired attempts reject late submission in the first version; crash replay
  skips already accepted attempts and may redispatch work whose attempt never reached
  accepted terminal state.
- Add a generic drain predicate: a phase may enter its gate only when both pending and
  in-flight work are empty. Integrate the kernel into the existing Wave0 and Wave1 fake
  subgraphs with at least three concurrent fixture workers while preserving the
  top-level topology and mixed/full-fake lifecycle paths.
- Extend the current `ResearchState` schema compatibly with defaulted optional
  work/attempt fields already reserved by change 02. Existing version-2 full-fake
  checkpoints remain readable; unsupported schema versions still fail closed and no
  incompatible payload is silently migrated.
- `backend/` and `frontend/` are not modified.

## Capabilities

### New Capabilities

- `work-unit-kernel`: Controller-owned work/attempt allocation, bounded parallel
  dispatch, candidate reduction and validation, atomic submission-ledger authority,
  crash replay, cross-process serialization, and phase drain semantics. Requirement
  IDs: WOU-001 through WOU-008.

### Modified Capabilities

- `research-graph-lifecycle`: Wave0/Wave1 fake fan-out now exercises the real work-unit
  and submit authority using deterministic fixture content; state reducers, restart
  recovery, three-authority semantics, and bundle paths are tightened around accepted
  submissions while the normalized top-level topology and route labels remain
  unchanged.
- `deployment-configuration`: runtime readiness additionally verifies that the selected
  sandbox/workspace combination can support the work-unit store's shared-filesystem
  transaction contract; unsupported remote or non-mounted providers fail closed without
  changing configuration schema.

## Impact

- **Source:** add frozen contracts and the pure bounded ledger codec under
  `agent/src/deerflow_deep_research/domain/` and deterministic allocation, reducer,
  validation, retry, and drain policy under `engine/work_units/`; add a runtime-owned capability-checked
  ledger store under `runtime/` and a reusable non-phase component under
  `graph/components/`; update `domain/state.py`, `domain/bundle.py`,
  `domain/invocation.py`, `runtime/projection.py`, `runtime/research.py`, runtime
  diagnostics, `domain/lifecycle.py`/`tool.py` infrastructure error projection, and the existing
  `graph/nodes/wave0/subgraph.py` and `graph/nodes/wave1/subgraph.py`. Update the
  canonical project-structure registry and generated `agent/AGENTS.md` block with the
  exact added paths. No second delegated-completion path is introduced.
- **Typed state/checkpoint data affected:** parent `ResearchState` stores small
  `work_specs_by_id` metadata, batch/id cursors, bounded attempt/status history, and
  `accepted_submission_refs`; a separate bounded non-checkpointed child state owns the
  current replay unit's pending/in-flight/candidate reducers. Every field declares its
  writer, reader, and reducer. New parent fields are optional/defaulted under the current
  compatible schema version. Large candidates and outputs remain sandbox refs; no
  evidence bodies enter checkpoints, and incompatible versions remain fail-closed.
- **Graph nodes/components affected:** Wave0 and Wave1 plan/worker/submit/drain portions
  use the shared component; their existing gate and repair routing remains owned by the
  gate kernel. Targeted evidence and rerun do not gain a second implementation here and
  will consume the same component in their owning changes. Top-level topology is
  unchanged.
- **Node-agent roles used:** planners return bounded work intent, workers return typed
  candidates, and repair roles may request a retry; deterministic controller code alone
  materializes `WorkSpec` identity and attempts. A work-unit-specific runtime projection
  derives each worker's virtual root as `work/<work_id>/<attempt_id>`. Agents cannot
  write the ledger, accepted refs, work identity, or phase/gate state. Fixture workers
  remain deterministic and make no model, web, MCP, ACP, or DeerFlow `task` subagent
  calls. Submit and drain are deterministic controller code.
- **Sandbox artifacts read/written:**
  controller code writes `work/<work_id>/<attempt_id>/work-spec.json`; the assigned
  fixture worker writes only `result.json` and declared `outputs/...`; deterministic
  submit writes `evidence/submissions.jsonl` plus a research-scoped lock/staging file
  used only for atomic publication. No DPT queue/index/status bundle files are added.
- **DeerFlow extension surfaces:** the existing downstream reflection path
  `deerflow_deep_research.tool:deep_research_tool` and registered lifecycle handler are
  unchanged. No `config.yaml` section, `extensions_config.json` key, public/custom
  skill, per-user Agent/SOUL, MCP, ACP, or lead-agent middleware surface is added or
  modified.
- **Reload boundary:** no runtime configuration, mount, or
  `reload_boundary.STARTUP_ONLY_FIELDS` value changes. Source changes are available on
  the next agent build; a running non-reload Gateway must be restarted/redeployed to
  import new Python source, but there is no additional configuration-mandated restart.
- **Dependencies:** no new third-party runtime dependency; filesystem serialization
  uses platform/stdlib primitives only on verified mounted-workspace local/default-Docker
  paths. Provisioner/remote/non-mounted sandbox modes fail closed in this version.
- **Non-goals:** no real web worker, source fetching, late-submit winner, 20-item active
  window, dynamic priority preemption, concrete wave evidence floor, or real
  targeted-evidence/rerun implementation. No files under `backend/` or `frontend/` are
  modified.

New requirement IDs are WOU-001 through WOU-008 (`work-unit-kernel`). Existing
requirements REG-002, REG-009, and REG-010 are modified under
`research-graph-lifecycle`, and DEC-005 is modified under
`deployment-configuration`.
