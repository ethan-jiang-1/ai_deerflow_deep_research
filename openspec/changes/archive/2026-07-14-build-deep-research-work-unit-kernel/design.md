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
- Multi-Gateway checkpoint fencing or newest-attempt priority under split-brain control
  snapshots; cross-process guarantees in this change cover ledger compare-and-set, not a
  distributed transaction with the LangGraph checkpointer.
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
  contained reads, bounded locking, ledger compare-and-set, fsync, atomic publish

runtime/work_unit_storage.py
  shared config classifier, host primitive probe, runtime mount/alias verifier, reasons
```

The architecture contract treats `graph/components/` as reusable orchestration rather
than a top-level node package. Graph components may depend on pure engine policy, while
only a node package's `subgraph.py` may import them. Ordinary `node.py`, `fake.py`, and
`contracts.py` modules still cannot import graph implementation code, and graph
components cannot import nodes, agents, or runtime.

The exact added production paths are `domain/work_units.py`,
`engine/work_units/{__init__,ids,reducers,validation,kernel}.py`,
`graph/components/{__init__,work_units}.py`, and
`runtime/{work_unit_storage,work_unit_store}.py`. Existing files are extended only where
listed in the proposal impact. Diagnostics and the concrete store both import
`runtime/work_unit_storage.py`; the classifier/verifier does not import diagnostics or
the store, preventing a readiness/I/O cycle.

`domain/bundle.py` will add canonical paths for `work-spec.json`, `result.json`,
attempt outputs, `evidence/submissions.jsonl`, the stable
`evidence/.submissions.lock`, and randomized same-directory
`evidence/.submissions.<32-lowercase-hex>.tmp` staging files.
`NodeSpec` gains a closed `NodeCapability` set whose only new value is
`WORK_UNIT_CONTROLLER`; its default is empty. Change 04 declares that capability only on
Wave0 and Wave1. `GraphInvocationContext` gains one non-checkpointed
`WorkUnitControllerDependencies` bundle containing the store protocol and per-work
dependency resolver. `_node_wrapper` projects that bundle into
`NodeBuildDependencies.work_units` only when the current `NodeSpec` declares the
capability; every other node receives `None`, and a declaration/runtime mismatch fails
before factory construction.

The work resolver accepts the trusted logical node, a fully validated `WorkSpec`, its
validated active `Attempt`, and `PolicyRef`. The controller component obtains that spec
from the just-materialized object or, on replay, reads canonical attempt `a00`'s derived
`work-spec.json` through the runtime store, validates canonical bytes/schema, and matches
its hash/identity/role to `WorkSpecRef` before resolver use. It writes/verifies a byte-
identical copy at the active retry attempt path before dispatch.

The resolver returns `WorkUnitWorkerDependencies` containing the immutable `WorkSpec`
and `Attempt`, ordinary `NodeBuildDependencies` whose own `work_units` field is forced to
`None`, plus the optional fixture-only `AttemptArtifactWriter`. Thus a worker receives
normal `NodeExecutionCapabilities`, its work-specific `NodeAgentContext`, and its exact
spec/attempt input, never the controller store/resolver or nested delegation authority.
Store authority is never placed in model context, child agent state, tool arguments, or
prompts.

For deterministic fixtures, the controller store may mint a separate
`AttemptArtifactWriter` narrowed to one canonical work/attempt root and result/output
operations. It exposes no ledger read/append, accepted-ref, id-allocation, or arbitrary
research-root write method. Real node agents continue to write through their bounded
sandbox tool policy rather than receiving this fixture capability.

The runtime store derives its host root only from
`TrustedRuntimeEnvelope.workspace_host_path` plus the validated research id, but it may
use that root only after a provider/workspace capability check proves the initialized
parent sandbox sees the same physical thread workspace. Public or model-provided paths
remain virtual refs. This does not create a second sandbox or expose a host path outside
`runtime/`. Canonical ledger encoding and chain verification live in `domain/`, so
`runtime/` does not import inward orchestration from `engine/`.

Store/verifier construction is asynchronous because sandbox file APIs and host probes
must run off the event loop. `RuntimeAdapter.adapt` gains an explicit trusted
`initialize_parent_sandbox` flag selected by the reflected tool after argument/action
validation: `start`/`resume` and `infra_probe` retain initialization, while `status` and
`cancel` pass false and receive `TrustedRuntimeEnvelope.parent_sandbox = None`.
`ResearchActionHandler` builds the controller-capable invocation context asynchronously
immediately before a start/resume `graph.ainvoke` that may enter Wave0/Wave1. Status and
cancel remain checkpoint-only and do not initialize or require a parent sandbox or work-
unit store; cancel resumes with a context whose optional work-unit dependency is `None`,
so a malformed route into a declaring Wave node still fails the capability check before
factory construction. A storage error bubbles through `GraphHost`; its saver context
still closes in `finally`, and the tool boundary alone converts the typed error to a
control result.

Alternative considered: let workers call a submit tool. Rejected because it gives an
agent a mutation surface over evidence authority and permits success to depend on prompt
compliance. Alternative considered: put file locking in `engine/`. Rejected because pure
engine code cannot own trusted host paths or blocking runtime I/O.

### 2. Use frozen canonical contracts and controller-generated monotonic ids

All public work-unit contracts use Pydantic v2 with `frozen=True`, `extra="forbid"`,
explicit schema version 1, bounded strings/collections, timezone-aware UTC datetimes,
and closed enums. The field contract is intentionally exact so implementation does not
have to invent wire shape:

| Model | Required fields | Bounds / normalization |
| --- | --- | --- |
| `WorkSpec` | `schema_version`, `research_id`, `generation`, `phase`, `work_id`, `work_ordinal`, `worker_role`, `scope`, `result_contract`, `result_schema_version`, `required_outputs`, `spec_hash` | schema/result schema 1; generation `0..2`; work ordinal `0..9999`; role `1..64` ASCII identifier chars; scope `1..16` strings of `1..512` chars; required output paths `0..16`, unique and bytewise-sorted, relative beneath `outputs/`, each at most 256 chars; canonical model at most 16 KiB |
| `Attempt` | `schema_version`, `research_id`, `generation`, `phase`, `work_id`, `attempt_id`, `attempt_ordinal`, `spec_hash`, `status`, `created_at`, `started_at`, `expires_at`, `terminal_at`, `terminal_code` | schema 1; attempt ordinal `0..99`; timestamp/status combinations follow the transition table in Decision 7; terminal code is closed, never free-form model text |
| `OutputRef` | `path`, `content_hash`, `schema_version`, `byte_count` | schema 1; canonical relative bundle path; `1..8 MiB` per output; unique and sorted by path in containing collections |
| `SourceRef` | `source_id`, `canonical_url`, `content_ref`, `content_hash`, `byte_count` | source id `1..128`; canonical HTTP(S) URL at most 2048 chars; contained canonical relative content ref; `1..8 MiB`; unique and sorted by `(source_id, canonical_url)` |
| `CandidateResult` | `schema_version`, repeated research/generation/phase/work/attempt/role identity, `spec_hash`, `result_contract`, `result_ref`, `result_hash`, `result_schema_version`, `result_byte_count`, `output_refs`, `source_refs`, `candidate_hash` | schema/result schema 1; result `1..256 KiB`; `0..16` outputs; `0..32` sources; total referenced bytes at most 32 MiB; canonical model at most 48 KiB; collections must already be canonical, sorted, and duplicate-free |
| `SubmissionRecord` | `schema_version`, work scope plus all candidate identity/content fields including `candidate_hash`, `validator_version`, `passed_checks`, `submitted_at`, `previous_record_hash`, `record_hash` | schema 1; integer validator version `1..32`; `1..32` unique bytewise-sorted stable check ids of at most 64 chars; canonical encoded record at most 64 KiB |
| `FixtureResultDocument` | `schema_version`, repeated research/generation/phase/work/attempt/role identity, `spec_hash`, `result_contract`, `fixture_marker`, `output_paths`, `source_ids` | schema 1; contract `fixture.work-unit`; marker `non_research_fixture`; output paths exactly equal `WorkSpec.required_outputs`; source ids empty in change 04 |

`required_outputs` is a tuple of canonical paths relative to the attempt's `outputs/`
directory, so an entry is `claims.json`, not `outputs/claims.json` and not a full bundle
path. Relative paths are canonical only when non-empty ASCII POSIX paths contain no
backslash, NUL, empty/`.`/`..` segment, leading slash, or trailing slash. `worker_role`
matches `[a-z][a-z0-9_]{0,63}`, `source_id` matches
`[A-Za-z0-9][A-Za-z0-9._:-]{0,127}`, and validator check ids match
`[a-z][a-z0-9_.-]{0,63}`. Result contract ids use that same pattern. `result_ref`, `OutputRef.path`, and
`SourceRef.content_ref` are persisted as
canonical bundle-relative paths, not worker-relative strings. Fields that are optional by
lifecycle state remain present with explicit `null` values in canonical model dumps; a
missing field and an explicit `null` are not two encodings of the same object.

Source URL canonicalization accepts only absolute HTTP(S) URLs without userinfo. It
lowercases scheme and ASCII host, removes port 80 from HTTP and 443 from HTTPS, maps an
empty path to `/`, removes a trailing slash only from a non-root path, strips the
fragment, and otherwise preserves path percent-octets and query bytes. Non-ASCII hosts
must arrive in ASCII IDNA form; the validator does not perform network-dependent or
locale-dependent rewriting.

Change 04 writes `validator_version = 1` and the exact sorted successful check tuple
`("artifact_hashes", "candidate_hash", "identity", "logical_work_unique", "paths",
"result_contract", "source_refs", "work_spec")`. Every check id is present even when the
candidate has zero optional outputs or sources: the validator records that the empty
collection was validated. Later validator versions may define another exact tuple but
never rewrite existing records.

`AttemptTerminalCode` is exactly
`accepted | worker_failed | validation_failed | candidate_conflict |
deadline_exceeded | expired | cancelled | superseded`.
`submitted` requires `accepted`; `failed` permits
`worker_failed | validation_failed | candidate_conflict`;
`timed_out` permits `deadline_exceeded | expired`; and `cancelled` permits
`cancelled | superseded`. Pending/running attempts have null `terminal_at` and
`terminal_code`; terminal attempts require both. `created_at` is always present,
`started_at` is required after `pending -> running`, and a direct
`pending -> cancelled` keeps it null.
Every timestamp is timezone-aware and canonicalized to UTC;
`created_at <= started_at <= terminal_at` for started attempts,
`created_at <= terminal_at` for direct cancellation, and `expires_at > created_at` when
present. An `expired` terminal requires `terminal_at >= expires_at`; submit rejects any
candidate when the injected current UTC time is at or after `expires_at`.

Canonical JSON uses UTF-8, sorted keys, compact separators, explicit enum values, UTC
timestamps normalized to `YYYY-MM-DDTHH:MM:SS.ffffffZ`, and no NaN/Infinity. Hashes use
SHA256 with the exact ASCII-plus-NUL domain prefixes
`deerflow-deep-research:work-spec:v1\0`,
`deerflow-deep-research:candidate-result:v1\0`, and
`deerflow-deep-research:submission-record:v1\0` prepended to canonical JSON bytes.
Failure detail uses exact domain prefix
`deerflow-deep-research:terminal-failure-detail:v1\0` over the bounded object defined in
Decision 3. Every hash uses the existing `h_<base64url-no-padding>` representation. A
spec hash excludes only `spec_hash`; a
candidate hash excludes only `candidate_hash`; a record hash excludes only
`record_hash`. `candidate_hash` is the sole replay fingerprint and therefore covers the
complete candidate identity, spec hash, result ref/hash/schema/size, canonical output
contract/refs, and canonical source refs. Duplicate, unsorted, or non-canonical set-like
collections are rejected before hashing rather than silently normalized. Replay equality
does not compare ledger-assigned `submitted_at`, `validator_version`, `passed_checks`,
`previous_record_hash`, ledger position, or `record_hash`; those fields cannot turn one
candidate into another.

All persisted path refs use the existing canonical relative bundle representation
`workspace/deep-research/<research_id>/...` from `domain/bundle.py` and `ContentRef`.
`NodeAgentContext` alone exposes `/mnt/user-data/workspace/...` to tools/models. The
runtime boundary converts canonical relative refs to that virtual form or to a contained
host path; neither virtual absolute paths nor host paths enter spec/candidate/record
hashes. This gives replay one byte representation across local and Docker launches.

The controller allocates deterministic ids from checkpointed generation/phase ordinals:

```text
work_id    = g<generation>_<phase>_w<four-digit-work-ordinal>
attempt_id = <work_id>_a<two-digit-attempt-ordinal>
```

Examples are `g0_wave0_w0000` and `g0_wave0_w0000_a00`. The work ordinal is scoped to
one `(generation, phase)` epoch and the attempt ordinal is scoped to one logical work.
IDs derive only from trusted generation, phase, and cursors, never scope text or planner
content. Replaying the same cursor position recreates the same id; if the regenerated
spec differs, the unchanged identity exposes a spec-hash conflict instead of minting a
new identity. The controller allocates every attempt before dispatch, so parallel
workers cannot race id creation. A retry retains the original `WorkSpec` and spec hash
but consumes that work's next attempt ordinal. Workers receive identity as read-only
input and may only return a candidate for that exact attempt. `project_work_unit_agent()`
derives the virtual attempt root as
`<research_root>/work/<work_id>/<attempt_id>` from validated controller ids; it does not
reuse the current phase-level `<research_root>/attempts/<id>` path.

Retry is reserved for a logical work with no accepted record whose prior attempt ended
failed or timed out. A `cancelled` terminal with code `cancelled` belongs to the research
cancellation path and does not authorize redispatch; code `superseded` proves another
attempt already won and likewise forbids retry. Once a logical work is accepted it is
immutable and can never receive another attempt. If a gate requests better/revised
evidence after acceptance, deterministic planning allocates a new logical work id and
spec; change 04 does not add a mutable replacement or predecessor-lineage field.

Alternative considered: UUIDs generated inside each worker. Rejected because restart
would create new identities for the same graph step and make replay/conflict detection
ambiguous.

### 3. Extend ResearchState compatibly and keep the child batch bounded

Change 02 already reserved the work block. Change 04 keeps
`RESEARCH_STATE_SCHEMA_VERSION = 2` and adds only optional/defaulted fields, so existing
version-2 full-fake checkpoints remain readable. Unknown or truly incompatible schema
versions continue to return `schema_unsupported`; this is compatible schema evolution,
not silent reinterpretation. The parent carries small controller projections only:

- `work_specs_by_id: work_id -> WorkSpecRef`, where the validated key carries generation,
  phase, and work ordinal while the value contains only worker role and spec hash, not
  scope/output-contract bodies or a derivable path;
- `attempts_by_id: attempt_id -> AttemptRef` and the compatibility-named
  `work_status_by_id: attempt_id -> WorkStatus`; neither mapping is keyed by logical work;
- `active_attempt_by_work_id: work_id -> attempt_id`, with at most one non-terminal
  attempt for each logical work;
- `batch_cursor` and `next_work_ordinal`, scoped to the current `(generation, phase)`
  epoch, plus `next_attempt_ordinal_by_work_id`;
- bounded `terminal_failures_by_attempt_id` summaries and deduplicated record hashes in
  `accepted_submission_refs`.

The compact parent values are also frozen and extra-forbid:

| Projection | Fields |
| --- | --- |
| `WorkSpecRef` value keyed by `work_id` | `worker_role`, `spec_hash` |
| `AttemptRef` value keyed by `attempt_id` | `created_at`, `started_at`, `expires_at`, `terminal_at`, `terminal_code` |
| `TerminalFailureSummary` value keyed by `attempt_id` | closed `failure_code`, `detail_hash` |

Map keys are validated canonical ids and carry the generation/phase/work/attempt ordinal
identity; compact values SHALL NOT duplicate fields derivable from those keys.
`detail_hash` fingerprints only the bounded deterministic object
`{"terminal_code": <enum>, "validation_codes": [<ordered enums>]}` using the canonical
JSON rules and the `terminal-failure-detail` hash domain defined below. The validation-
code list is empty for non-validation terminals; arbitrary worker/model prose and raw
validation detail are not checkpointed. Gate classification is derived from the existing
closed `FailureCode` registry and is not duplicated in the checkpoint. Attempt status
remains in
`work_status_by_id`, while an attempt's work id, attempt ordinal, and spec hash are derived
from its key plus `work_specs_by_id`, so `AttemptRef` does not duplicate them.
The canonical first-spec ref is also derived, not stored: `domain/bundle.py` maps the
trusted research id and work id to attempt `a00`'s `work-spec.json`. Every retry receives
a byte-identical copy at its own attempt-derived path, while only worker role and spec
hash remain in parent state.

`terminal_failures_by_attempt_id` is a current gate projection, not attempt-history
authority. It contains at most one summary per logical work: the accepted attempt has no
failure, otherwise the selected highest terminal attempt may have one. The submit/
reconcile controller writes the complete validated mapping with LastValue replacement
semantics when that selection changes. Replacing a work's selected summary is not silent
history eviction because the old attempt, status, timestamps, and terminal code remain
immutably present in `attempts_by_id` and `work_status_by_id`.

The compact Pydantic models are validation authorities, not opaque checkpoint objects.
Parent reducers accept either an instance or a JSON mapping, validate/coerce through the
frozen extra-forbid model, and persist only `model_dump(mode="json")` plain mappings with
canonical UTC strings. `ResearchCheckpoint` load performs the same validation and
normalization. The work-block budget and replay equality therefore use the exact same
plain-JSON representation and do not depend on LangGraph/Pydantic object serialization.

The parent work window is bounded to 32 logical works, 64 attempts, 32 terminal failure
summaries, and 64 accepted record hashes. A phase transition may clear the active
spec/attempt/status/cursor window only after drain and gate completion; accepted record
hashes remain until a later owning change introduces an explicit ledger-backed evidence
index/compaction contract. The canonical JSON object containing exactly the work-unit
parent fields has an independent 40,960-byte ceiling. Its exact sorted field set is
`pending_work_ids`, `batch_cursor`, `next_work_ordinal`,
`next_attempt_ordinal_by_work_id`, `work_specs_by_id`, `attempts_by_id`,
`work_status_by_id`, `active_attempt_by_work_id`,
`terminal_failures_by_attempt_id`, and `accepted_submission_refs`; no caller chooses or
omits fields from the budget object. State serialization still applies the existing
whole-checkpoint 65,536-byte hard limit. The controller must reject an update that
exceeds a collection, work-block, or whole-checkpoint bound; truncation and silent
eviction are forbidden.

These are not arbitrary fixture minima. With three work items, at most three gate visits
per Wave, two integrated Waves, and generations `0..2`, the current fake lifecycle can
produce at most 54 accepted refs while each active phase holds at most 9 logical works
and 27 attempts. The 32/64/64 collection bounds therefore cover every current
repair/rerun path with explicit headroom; generic 32-work construction can retain an
initial attempt plus one retry for every work before the active-window bound fails
closed. A maximum-shape golden fixture SHALL prove the compact 32-work/64-attempt/
32-failure/64-ref independent-field upper envelope fits 40,960 bytes. A separate legal
all-terminal fixture at those four collection maxima, with empty pending/active maps and
the maximum bounded single-byte ASCII request text, SHALL fit 65,536 bytes. The existing
whole-state bound continues to reject any other request/control combination whose
serialized form is larger; these fixtures do not widen the request contract.

The prior 32-work/96-attempt/32-failure/128-ref draft with identity duplicated inside map
values was rejected by an implementation-feasibility spike: its maximum-shape work block
serialized to 65,841 bytes before ordinary checkpoint fields and 82,959 bytes after
adding the maximum request text. The key-derived 32/64/32/64 independent-field work-block
upper envelope serialized to 31,776 bytes. A legal all-terminal shape at the same four
collection maxima serialized to 47,136 bytes with that request. These measurements are
review evidence, not replacement limits; the normative tests enforce the 40,960- and
65,536-byte ceilings.

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

`WorkUnitComponentState` has exactly six channels: sorted
`planned_work_ids: tuple[str, ...]` (max 32), `pending_work_ids: tuple[str, ...]` (max
32), `batch_cursor: int`, `in_flight_by_attempt_id: dict[attempt_id, work_id]` (max 16),
`candidates_by_attempt_id: dict[attempt_id, CandidateResult]` (max 16), and
`terminal_updates_by_attempt_id: dict[attempt_id, AttemptTerminalUpdate]` (max 64).
`AttemptTerminalUpdate` contains exactly `attempt_id`, terminal `status`, UTC
`terminal_at`, `terminal_code`, and optional closed `validation_codes` in registry order.
`validation_failed` requires a non-empty ordered validation-code tuple; every other
terminal code requires the tuple to be empty. This makes the failure-detail hash input
and primary failure selection total rather than optional convention.
The in-flight, candidate, and terminal-update maps use pure keyed reducers: the same
value is idempotent and a different value for one attempt conflicts. The single deferred
submit node runs only after all current `Send` workers finish, sorts candidate keys,
writes terminal updates, and returns LangGraph `Overwrite({})` for only the in-flight and
candidate batch maps before refill. It never returns the aggregated candidate mapping as
a normal reducer update and never clears terminal updates. Terminal updates accumulate
only the bounded phase history needed to construct the returned parent update; candidate
bodies remain bounded to one batch.

The manually invoked child uses `checkpointer=False` and an internal
`recursion_limit=128`. The limit is derived from the worst supported 32-work,
concurrency-1 allocate/Send/submit loop plus drain and is not inherited from or selected
by public/root invocation config.

Field ownership becomes specific rather than treating controller and gate as one broad
authority set. `WriterRole` gains the closed value `SUBMIT`; this is deterministic code,
not a model/agent role:

- controller materializer: specs, pending work, id cursors, active-attempt mapping, and
  new attempts;
- worker reducer: current-batch candidate channel only;
- deterministic submit controller: attempt transition, terminal failure summary,
  active-attempt removal, and accepted refs;
- gate: route, gate feedback, gate attempts, repair budgets, and phase transition;
- planner/worker/repair agents: no checkpoint or ledger authority fields.

In particular, ordinary `CONTROLLER` may materialize specs/attempts but cannot append an
accepted ref, and `GATE` may read the validated view but cannot mutate specs, attempts,
statuses, failure projections, or accepted refs. Reconciliation that catches up a ledger
record executes under `SUBMIT` ownership.

Writer authorization is applied to trusted partial operations before they are combined,
not inferred from the final mapping: materialization calls the controller-authorized
kernel path, submit/reconcile calls the `SUBMIT` path against the controller-previewed
state, and gate uses its existing gate-authorized conversion. Worker/model output is only
a `CandidateResult` in child state and is never accepted as a parent `ResearchState`
delta. The component then validates one cross-field final parent projection before
returning it.

Reducers preserve same-hash idempotency, reject different-hash conflicts, forbid
terminal downgrade, reject a second active attempt for one work, and dedupe accepted
refs. A retry appends a fresh `AttemptRef` and status entry and never rewrites or
downgrades the old terminal attempt. A single submit-node update changes the attempt to
submitted, removes it from `active_attempt_by_work_id`, and adds its accepted ref
together; no checkpoint is intentionally written with only a subset of those fields.

The strict `pending -> running -> terminal` table applies to the internal kernel
operations. Because the manually invoked child is one atomic parent graph node, the next
parent checkpoint may first observe a newly allocated attempt already terminal, or may
observe a previously non-terminal attempt after multiple validated internal transitions.
This is a coalesced projection, not a skipped lifecycle transition. Before return, the
pure parent-projection validator checks the final `AttemptRef`, status, active map,
selected failure, and accepted ref together. Parent LangGraph reducers therefore enforce
key identity, exact replay, and terminal monotonicity, but do not try to reconstruct every
uncheckpointed intermediate child transition from one field in isolation.

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

The construction-time policy supplies `max_concurrency` in `1..16`; the change-04
fixtures use exactly 3. Planned work is ordered by work ordinal (equivalently by its
zero-padded work id). `batch_cursor` is a zero-based index of the next undispatched work
in that ordered phase list. Allocation selects
`ordered[batch_cursor:batch_cursor + max_concurrency]`, creates attempts in that order,
and advances the cursor by the emitted count before `Send`; completion never moves the
cursor. At most one active attempt per selected work enters `in_flight_by_attempt_id`.
Worker completion order is irrelevant because the reducer sorts by identity before
submit. Submit processes candidates in that same stable order, but each ledger commit is
independently idempotent.

Allocation is deterministic from the last parent checkpoint. If a process dies after a
ledger commit but before the parent state update, replay regenerates the same ids,
reconciles them against the ledger before any `Send`, and skips the accepted attempt. If
no record exists, the bounded step may re-execute that non-terminal attempt. Fixture
planning is deterministic in change 04; later model-backed planners must checkpoint
their immutable specs before handing them to this kernel.

`drain` is structural only: pending and in-flight must both be empty before the outer
phase wrapper invokes its existing gate. Failed/timed-out/cancelled attempts remain
visible to gate rules, so structural drain cannot create evidence or imply pass.

Wave0 and Wave1 `GateDefinition` values prepend a shared pure
`WorkUnitCompletionRule`. It verifies that the child is drained, every planned logical
work has one terminal outcome, every submitted outcome appears in the bounded pure
accepted-coverage view produced by the controller's immediately preceding ledger
reconciliation, and the selected terminal failure remains present. The rule performs no
I/O, consumes only already mapped `FailureCode` values, and never treats the derived view
as a fourth authority; it is discarded after the gate transition. Validation-code
mapping happens once in the deterministic submit projection: the first code in the
closed collect-all precedence is selected as primary, the full ordered code tuple is
covered by `detail_hash`, and the exact primary mapping is
`work_spec_missing -> MISSING_WORK_SPEC`;
`identity_mismatch | spec_hash_mismatch -> IDENTITY_MISMATCH`;
`schema_version_unsupported -> SCHEMA_VERSION_UNSUPPORTED`;
`result_contract_unsupported | invalid_output_schema | path_not_canonical |
path_not_contained | artifact_missing | artifact_empty | source_ref_invalid ->
INVALID_OUTPUT_SCHEMA`; `content_hash_mismatch | candidate_hash_mismatch ->
CONTENT_HASH_MISMATCH`; and `candidate_conflict -> WORK_FAILED`. Non-validation terminal
codes map once at the same boundary: `worker_failed | candidate_conflict -> WORK_FAILED`,
`deadline_exceeded | expired -> WORK_TIMED_OUT`, and `cancelled | superseded ->
WORK_CANCELLED`; a submitted/accepted attempt has no failure summary. The fixture rule
still runs collect-all after the completion rule. Thus valid fixtures preserve every
prior route, while fixture `pass` cannot mask invalid work.

The reconciler constructs a frozen bounded `WorkUnitGateView` domain value containing
exactly `drained: bool`, bytewise-sorted `planned_work_ids: tuple[str, ...]`,
`terminal_attempt_by_work_id: dict[work_id, attempt_id]`,
`accepted_record_by_work_id: dict[work_id, record_hash]`, and ordered
`failure_summaries: tuple[WorkUnitGateFailure, ...]`. The ephemeral
`WorkUnitGateFailure` contains exactly `work_id`, `attempt_id`, `failure_code`, derived
`classification`, and `detail_hash`; it is not the compact checkpoint value. The view
bounds are 32 planned works,
32 terminal mappings, 32 accepted mappings, and 32 failure summaries; it contains no
scope, artifact path, candidate body, ledger record, cursor, phase, route, fixture count,
or host/virtual path. Because accepted refs alone cannot recover record-to-work identity
without ledger I/O, a declaring Wave controller returns the view under the exact reserved
mapping key `__work_unit_gate_view__` alongside its state delta. `_node_wrapper`
immediately copies the result, pops and type-checks that value, and rejects the reserved
key from every non-controller node. It inserts the view only into the in-memory gate-
preview mapping under the same key, then strips it from the final returned update. The key
is not a `ResearchState` field, so it is never reduced/checkpointed and cannot become a
fourth authority.

For each planned work, the terminal map selects the accepted attempt when one exists;
otherwise it selects the highest attempt ordinal. Failure summaries contain at most one
entry per planned work for that selected terminal attempt and are ordered by work id.
Validation is deliberately two-stage. Before the child returns and discards its detailed
reconciliation values, the component validator proves that view planned ids exactly equal
the child `planned_work_ids`, every `work_id -> record_hash` pair matches the reconciled
`SubmissionRecord` work/attempt/hash association, terminal selection follows the rule
above, and the view agrees with the complete final parent projection. This is the only
stage capable of detecting swapped accepted-record hashes without another ledger read.

Before gate evaluation, the wrapper validator then proves transport consistency against
the reducer-previewed checkpoint fields available to it: planned ids are sorted/unique,
belong to the previewed current-phase spec map, and exactly key the terminal map;
every terminal attempt exists, derives the mapped work id, and has the previewed terminal
status; an accepted work selects a submitted attempt and names a hash present in
`accepted_submission_refs`, while an unaccepted work does not select submitted; and every
selected failure matches `terminal_failures_by_attempt_id`. The wrapper does not claim it
can reconstruct record-to-work identity from hashes. Either-stage mismatch raises stable
internal `work_unit_gate_view_inconsistent` before fixture/business rules rather than
becoming a repairable gate failure.

The current `_node_wrapper` evaluates gate rules against the input `state`, before
LangGraph applies the node's returned reducers. Change 04 adds a pure reducer-preview
function with an exact allowlist: `work_specs_by_id`, `attempts_by_id`,
`work_status_by_id`, `active_attempt_by_work_id`,
`terminal_failures_by_attempt_id`, and `accepted_submission_refs`. It shallow-copies the
input, applies the same explicit domain reducers used by those channels, injects the
already reconciled typed view extracted from `__work_unit_gate_view__`, and passes that
post-work mapping to the gate. It does not reconstruct accepted identity from hashes or
reflect over LangGraph channel internals. The original input and stripped state delta
stay unchanged; the wrapper returns that original state delta, not the merged preview, so
LangGraph applies every reducer exactly once.

The preview deliberately excludes `phase`, `route`, `execution_trace`, cursor fields,
fixture visit counters, and gate-owned fields. Otherwise
`FixtureSequenceRule.completed_visits()` would observe the current trace too early and
skip to the next fixture outcome. Before combining updates, the wrapper asserts that the
node delta and gate update have disjoint keys; overlap fails with a typed
`node_gate_write_conflict`. The wrapper then returns one combined work plus gate update
for a single checkpoint transition. This prevents a one-step lag without mutating the
checkpoint outside LangGraph, double-applying reducers, or changing fixture indexing.

Wave0 and Wave1 will consume the same component with different deterministic fixture
spec factories. Their top-level logical names and conditional edges remain unchanged.
On a fixture gate repair after a fully accepted batch, the next visit allocates new work
ordinals; it does not retry or replace the already accepted logical work. Only an
unaccepted failed or timed-out item reuses its work id with a new attempt ordinal.
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
4. exact `result.json` placement and the registered `(result_contract, version)` schema;
5. exact equality between required output paths, fixture-result output paths, and
   candidate output refs, with every file under `outputs/`, non-empty, and hash-matching;
6. every source ref's canonical URL, contained cache/fetch ref, and matching hash;
7. candidate hash and uniqueness against accepted records.

`SubmissionValidationCode` is closed and emitted in exactly this precedence order:

```text
identity_mismatch
work_spec_missing
spec_hash_mismatch
schema_version_unsupported
result_contract_unsupported
invalid_output_schema
path_not_canonical
path_not_contained
artifact_missing
artifact_empty
content_hash_mismatch
source_ref_invalid
candidate_hash_mismatch
candidate_conflict
```

Collect-all results are deduplicated by code and retain that registry order, never file
iteration or scheduler order. Symlink escape/path swap maps to `path_not_contained`;
missing `work-spec.json` alone maps to `work_spec_missing`; all other missing files map
to `artifact_missing`.

Host path resolution uses the trusted workspace root, `Path.resolve()` containment, and
descriptor-relative/no-follow opens where the platform supports them. A symlink escape,
path swap detected by stat checks, missing/empty file, unsupported schema, or mismatch
returns a closed typed failure code. All blocking reads and hashing run in
`asyncio.to_thread`.

The controller writes canonical `work-spec.json` before dispatch. Fake workers write
only deterministic `result.json` and bounded outputs through a worker-scoped artifact
capability rooted at `work/<work_id>/<attempt_id>`; their `source_refs` collection is
empty because change 04 performs no fetch/cache work. The source-ref contract is still
validated for later kernel consumers, but this fixture does not invent source artifacts.
The fixture result document uses the exact `fixture.work-unit` schema above and remains
machine-identifiable as `non_research_fixture`. The pure validator owns a closed result-
contract registry; this change registers only `(fixture.work-unit, 1)`, and later phase
changes add their schema validators without branching the store or submit authority.
Workers do not call sandbox research tools, models, web APIs, MCP, ACP, or DeerFlow
`task`. Worker summary text is ignored by submit.

Alternative considered: accept `NodeExecutionResult.artifact_refs` without rereading
files. Rejected because a ref proves only that a worker named a path; it does not prove
identity, containment, schema, or content hash.

### 6. Use a logically append-only JSONL hash chain with atomic whole-file publication

The ledger is
`workspace/deep-research/<research_id>/evidence/submissions.jsonl`. Each line is one
canonical `SubmissionRecord` plus `\n`. On every submit, the store acquires an exclusive
lock for that research, parses every existing line, validates schema and newline
termination, verifies the complete hash chain, and indexes both logical work id and
work/attempt identity. More than one accepted record for one `work_id` is ledger
corruption even when the attempt ids differ. Hard per-record, record-count, and
total-ledger byte limits are checked before parsing and before constructing replacement
bytes.

The first record has explicit `previous_record_hash: null`; every later record repeats
the immediately preceding `record_hash`. Empty ledger bytes are valid, CRLF/blank lines
are not, and every non-empty ledger ends in exactly one LF after its final record.

The first-version ledger is bounded to 4,096 records and 8 MiB total, with the 64 KiB
per-record bound from Decision 2. If no record exists for the logical work, the store
constructs the next record using an injected UTC clock,
writes `old_bytes + new_line` to a unique same-directory staging file with mode `0600`,
flushes and `fsync`s it, atomically replaces the ledger, and `fsync`s the evidence
directory before releasing the lock. This is logically append-only even though physical
publication rewrites the complete file. A reader observes either the previous complete
ledger or the next complete ledger, never a partial line. Stale staging files are
non-authoritative and are removed under the lock.

Evidence directory, lock, ledger, and staging access is descriptor-relative and
no-follow. Absence of those POSIX primitives makes work-unit storage unavailable. The
store rejects symlink/non-regular lock or ledger entries, opens staging with exclusive
creation, and verifies the opened evidence directory remains beneath the trusted
research root before publication.

If the same attempt identity already exists, an equal stable candidate fingerprint
returns the existing record as idempotent replay and a different fingerprint is a
conflict. If another attempt for the same logical work already has an accepted record,
the store returns that record as `work_already_accepted` and never appends a second
winner. Reconciliation validates the existing record and files, publishes only that
record hash, and supersedes any still-active sibling attempt. Existing records are never
edited, truncated, reordered, or superseded in the ledger.

Reusing an existing record is not a trust shortcut. The runtime repeats contained reads
and the pure validator verifies the current spec/result/output/source bytes against the
stored hashes. Missing, replaced, or mutated files fail closed even when the stored
`candidate_hash` matches, because a replay fingerprint proves record equality rather
than current artifact availability.

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

| Parent/control state | Validated ledger state | Reconcile action |
| --- | --- | --- |
| no materialized work state | no record for deterministic id | regenerate the same spec/attempt from trusted cursors, then execute |
| pending/running attempt | no record for logical work | execute or revalidate its candidate and append once |
| pending/running attempt | matching same-attempt record, no accepted ref | ledger is ahead; revalidate current files, skip worker, and publish submitted/ref catch-up |
| submitted status plus accepted ref | matching record and current files | both agree; skip worker and return an idempotent no-op |
| any state | same attempt with different `candidate_hash` | divergent replay; fail closed with `candidate_conflict` |
| pending/running retry | valid record for a sibling attempt of the same work | revalidate the accepted record, publish only its ref, and terminally supersede the retry; never append a second winner |
| submitted status or accepted ref | no matching valid record | checkpoint/evidence authority diverged; return `work_unit_storage_unavailable/ledger_corrupt`, never recreate evidence from state, and do not repair the checkpoint |
| any state | matching record but missing/mutated referenced file | accepted artifact authority diverged; return infrastructure-unavailable without state repair |
| any state | more than one record for one logical work or a broken chain | ledger corruption; return infrastructure-unavailable before dispatch or state repair |
| any state | staging file only, no published record | ignore/clean staging under lock and treat as no record |

Fault injection points are named around: after the last parent checkpoint/before
accepted-ref publication, before staging write, after staging fsync, after atomic ledger
replace, after directory fsync, before submit-node return, and after returned state
update. Tests assert the matrix rather than depending on timing.

An already accepted logical work is never re-executed, even when the accepted record
belongs to an older attempt. A non-terminal attempt with no accepted record may replay
the same graph step and produce the same candidate. Explicit failure or timeout closes
that attempt and permits repair to allocate a new id. Cancellation closes the research
path and does not authorize a retry; supersession proves a sibling winner. Late
candidates for every closed attempt fail closed before store commit.

The exact attempt transition relation is:

```text
pending -> running -> submitted | failed | timed_out | cancelled
pending ---------------------------------------------> cancelled
```

Reapplying the same status with identical timestamps/terminal code is idempotent. Any
other same-status payload mismatch, every transition out of a terminal status, direct
`pending -> submitted|failed|timed_out`, and replacement of an old attempt entry are
conflicts. Retry appends a fresh attempt id; it never reopens the old entry.

The shared file lock guarantees at most one accepted record per logical work across
independent store processes, including candidates from different attempts. It does not
create a cross-store transaction with LangGraph checkpoints. Supported lifecycle
mutation remains serialized by the single-process/single-worker `GraphHost`; if two
independent Gateway processes run split-brain control snapshots, the ledger still yields
one winner but does not promise that the numerically newest attempt wins. Multi-process
checkpoint fencing or newest-attempt priority would require a distributed control lock
or a fourth durable fence and is explicitly outside this version. Within the supported
lifecycle, the controller checks `active_attempt_by_work_id` immediately before submit,
so a timed-out/cancelled/superseded attempt is rejected and only the current active
attempt can reach the store.

Alternative considered: checkpoint accepted intent before ledger publication and repair
the ledger from checkpoint. Rejected because it would let control state mint evidence
without revalidating the artifact authority.

### 8. Serialize independent processes with a per-research POSIX lock

`runtime/work_unit_store.py` uses a stable lock file in the research evidence directory
and `fcntl.flock(LOCK_EX)` around ledger read, chain validation, identity comparison,
staging cleanup, and atomic publication. The lock path is derived from the trusted host
root and validated research id; caller input cannot choose it. Separate research roots
therefore proceed independently. The lock is descriptor-relative opened with
`O_CREAT | O_RDWR | O_NOFOLLOW` and requested mode `0600`; existing lock and ledger
entries must be regular files with no group/world permission bits. A published ledger
inherits the exclusive `0600` staging mode.

Lock acquisition uses `LOCK_NB` retry every 25 ms with an injected monotonic two-second
deadline and returns a typed `work_unit_store_busy`; neither value is caller supplied,
and the loop never leaves an indefinitely blocked worker thread.
Acquisition and the size-bounded commit execute off the event loop. Once atomic commit
work starts, cancellation waits for that bounded section to release the lock and then
re-raises `CancelledError`; if the ledger committed, replay repairs the absent checkpoint
update. The process-local `GraphHost` namespace lock remains useful but is not treated as
the cross-process guarantee.

The supported first-version race contract is multiple independent store processes
sharing a POSIX workspace where advisory locks, same-directory atomic rename, and
directory fsync are honored. Runtime initialization verifies both those primitives and
that the parent sandbox uses the same physical thread workspace as the trusted host
path. A shared pure config classifier is used by doctor and runtime bootstrap:

| Effective `sandbox.use` / mode | Config classification | Reason code |
| --- | --- | --- |
| `deerflow.sandbox.local:LocalSandboxProvider` or its canonical module path | `ready` candidate | `local_thread_mount` |
| `deerflow.community.aio_sandbox:AioSandboxProvider` without `provisioner_url` | `ready` candidate | `aio_local_thread_mount` |
| the same AIO provider with non-empty `provisioner_url` | `not_ready` | `aio_provisioner_unmounted` |
| `deerflow.community.e2b_sandbox:E2BSandboxProvider` | `not_ready` | `e2b_unmounted` |
| `deerflow.community.boxlite:BoxliteProvider` | `not_ready` | `boxlite_unmounted` |
| every unrecognized/custom class path | `unknown` | `provider_unrecognized` |

Each built-in row recognizes both the package export shown above and its checked-in
implementation path: `deerflow.sandbox.local.local_sandbox_provider:LocalSandboxProvider`,
`deerflow.community.aio_sandbox.aio_sandbox_provider:AioSandboxProvider`,
`deerflow.community.e2b_sandbox.e2b_sandbox_provider:E2BSandboxProvider`, and
`deerflow.community.boxlite.provider:BoxliteProvider`. Suffix/class-name guessing is not
classification; any other path is `unknown`.

`ReadinessDiagnostic` gains `work_unit_storage: ready | not_ready | unknown` plus a
stable redacted reason in its existing checks/issues collections. For the two ready
candidates, prelaunch doctor also executes the required host filesystem primitives in
the effective thread-data filesystem without printing its path; a failed probe changes
the result to `not_ready`. Capability-set introspection such as `os.supports_dir_fd` is
never sufficient because supported `os.replace(..., src_dir_fd=..., dst_dir_fd=...)`
implementations are not reported consistently. `runtime_ready` is true only when
`work_unit_storage == ready`, so `unknown` remains informative but fail-closed. Sandbox
config is already included in the startup fingerprint and no new startup-only field is
added.

Store construction then rechecks the actual initialized provider instance rather than
trusting the offline classification. The runtime resolves the installed provider
singleton, requires `uses_thread_data_mounts is True`, requires
`provider.get(parent_sandbox.id) is parent_sandbox`, and treats a missing/changed id or
provider instance as `thread_mount_unavailable`. The runtime-owned alias probe then
round-trips independently generated bounded base64url ASCII tokens in both
host-write/sandbox-read and sandbox-write/host-read directions through synchronous
`Sandbox.write_file/read_file` calls executed with `asyncio.to_thread`. Cleanup uses the
trusted host directory's descriptor-relative `unlink`/empty-directory removal in
`finally`. Because an alias-mismatch file may exist only in the sandbox filesystem and
the public `Sandbox` interface has no delete method, `finally` also runs a bounded
`Sandbox.execute_command` cleanup for the exact generated virtual probe path and its
probe-only empty directories. The command receives no caller/model text, is shell-quoted,
runs through `asyncio.to_thread`, and is followed by an absence check; any host or sandbox
residue returns `probe_cleanup_failed`.
Host-created alias/probe files use exclusive mode `0600`. Because `Sandbox.write_file`
has no mode parameter, the sandbox-created alias file is immediately opened no-follow
from the trusted host directory, verified as a regular file, narrowed with
`fchmod(0600)`, and only then read and compared.

The filesystem probe must actually acquire and contend a nonblocking `fcntl.flock`,
create exclusive mode-`0600` no-follow regular files relative to an opened directory,
write and `fsync` a file, call same-directory
`os.replace(..., src_dir_fd=..., dst_dir_fd=...)`, reopen and verify the result, `fsync`
the directory, and remove all probe entries. Availability constants may be checked only
to fail early; success requires executing every primitive. Probe files are randomized,
bounded, removed in `finally`, and never evidence/control authority. Failure returns
`work_unit_storage_unavailable` before research spec/result/ledger/checkpoint mutation.
Doctor and runtime import the same classifier and stable reason enum; neither returns a
resolved host path. A distributed/remote store adapter remains future work.

Runtime capability probes use hidden random files under the current canonical research
diagnostics subtree:
`workspace/deep-research/<research_id>/diagnostics/.work-unit-probe-<32-lowercase-hex>`
for the alias round trip, plus one filesystem-probe family sharing another random token:
`.work-unit-fsprobe-<32-lowercase-hex>.lock`, `.src`, and `.dst`. The two opens of `.lock`
test contention; `.src` is fsynced and atomically replaces `.dst`. They are never returned
as refs and are removed on success, denial, exception, and cancellation; directories
created solely for the probe are removed if empty.

Prelaunch doctor has no research id and uses the exact same-token host-side names
`.deep-research-work-unit-fsprobe-<32-lowercase-hex>.lock`,
`.deep-research-work-unit-fsprobe-<32-lowercase-hex>.src`, and
`.deep-research-work-unit-fsprobe-<32-lowercase-hex>.dst` directly under the existing
gateway-visible `get_paths().base_dir`, which owns all later thread-data directories and
therefore tests the same filesystem without inventing a user/thread id. It never uses the
Docker-daemon-only `host_base_dir`, calls a sandbox, or creates a research ref.

`WorkUnitStoreError` is a runtime-owned typed exception. The reflected tool catches it
alongside existing runtime/host errors and projects two new
`InfrastructureResultCode` values: `work_unit_storage_unavailable` for an unsupported
workspace contract, and retryable `work_unit_store_busy` for lock-deadline exhaustion.
Neither path writes graph state or converts the failure into a gate/business terminal.
Provider/checkpointer resources still close through the existing `GraphHost` context.
`work_unit_storage_unavailable` also carries only a stable redacted reason enum for
`ledger_corrupt` or `accepted_artifact_diverged`. `ledger_corrupt` covers a broken chain,
duplicate logical-work records, or a submitted/accepted checkpoint hash with no matching
valid ledger record; `accepted_artifact_diverged` covers missing/mutated files behind a
matching record. These post-acceptance authority defects never become a repairable
`Attempt` or `FailureCode`.

The complete error reason enum is
`aio_provisioner_unmounted | e2b_unmounted | boxlite_unmounted |
provider_unrecognized | thread_mount_unavailable | workspace_alias_mismatch |
posix_primitives_unavailable | probe_cleanup_failed | ledger_corrupt |
accepted_artifact_diverged | lock_timeout`. `lock_timeout` is valid only with
`work_unit_store_busy`; every other value is valid only with
`work_unit_storage_unavailable`. Success check ids `local_thread_mount` and
`aio_local_thread_mount` are diagnostic checks, not error reasons.

The wire contract is explicit: `domain/lifecycle.py` adds
`WorkUnitStorageReason` with that enum and optional
`DeepResearchControlResult.infrastructure_reason`. The field is required exactly when
`code` is `work_unit_storage_unavailable | work_unit_store_busy`, forbidden for every
other result code, and validates the unavailable/busy pairing above. The tool catches
`WorkUnitStoreError` in a dedicated first branch so the reason is not collapsed to
`checkpoint_inconsistent`; it returns durability `unavailable` and no free-form detail.
Known lifecycle/runtime errors retain their existing typed projection. A final redacted
`except Exception` branch maps unexpected graph/domain invariant failures such as
`work_unit_gate_view_inconsistent` or `node_gate_write_conflict` to
`checkpoint_inconsistent` without exception text. It does not catch `BaseException`/
`CancelledError`, and all branches run only after `GraphHost` has unwound its saver
context.

Alternative considered: rely on `GATEWAY_WORKERS=1` and the existing lock stripe.
Rejected because tests and operational races can involve separate process instances, and
the plan requires the same logical work to have at most one accepted winner now.

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
readable because the new reader defaults absent fields and retains prior meanings. This
is one-way upgrade compatibility, not downgrade compatibility: the pre-change dataclass
reader rejects newly written fields rather than ignoring them. A code rollback therefore
fails closed on change-04 checkpoints, uses a fresh research run, and leaves ledger files
intact for diagnosis rather than deleting evidence authority.

## Open Questions

No blocking decision remains for change 04. Later changes may decide whether production
scale warrants a segmented/database ledger adapter, whether a non-POSIX distributed
or non-mounted sandbox needs an external transaction service, and what phase-specific
evidence floors apply; none changes the first-version mounted-workspace submit authority
or replay contract.
