> req: WOU-001, WOU-002, WOU-003, WOU-004, WOU-005, WOU-006, WOU-007, WOU-008

## ADDED Requirements

### Requirement: Controller-assigned immutable work contracts preserve identity and spec integrity

The downstream package SHALL define frozen, versioned, extra-forbid contracts for
`WorkSpec`, `Attempt`, `CandidateResult`, and `SubmissionRecord`. A `WorkSpec` SHALL
bind the trusted research id, generation, logical phase, work id, worker role, bounded
scope, result contract/version, and expected output contract. Its `spec_hash` SHALL be derived from a
domain-separated canonical JSON encoding that excludes the hash field itself. An
`Attempt` SHALL bind one controller-assigned attempt id and ordinal to exactly one work
id and spec hash. A candidate and submission SHALL repeat those identity fields and
carry their own deterministic content hash or fingerprint.

The identifier grammar SHALL be exact:
`work_id = g<generation>_<phase>_w<four-digit-work-ordinal>` and
`attempt_id = <work_id>_a<two-digit-attempt-ordinal>`, with work ordinals `0..9999`
scoped to one generation/phase and attempt ordinals `0..99` scoped to one work. Identity
SHALL derive only from trusted generation, phase, and checkpointed cursors. Replaying one
cursor position SHALL recreate the same id; changed planner/spec content at that id SHALL
surface a spec-hash conflict rather than mint another identity.

Canonical hashes SHALL use SHA256 over compact sorted-key UTF-8 JSON prefixed by the
exact ASCII-plus-NUL bytes `deerflow-deep-research:work-spec:v1\0`,
`deerflow-deep-research:candidate-result:v1\0`, or
`deerflow-deep-research:submission-record:v1\0` for the applicable model,
explicit enum values, normalized UTC timestamps, and no NaN/Infinity. `spec_hash`,
`candidate_hash`, and `record_hash` SHALL each exclude only their own hash field.
`candidate_hash` SHALL be the stable replay fingerprint and SHALL cover repeated
identity, spec hash, result contract/ref/hash/schema/byte count, output refs, and source refs.
Output refs SHALL be unique and bytewise-sorted by canonical path; source refs SHALL be
unique and sorted by `(source_id, canonical_url)`. Duplicate, unsorted, or non-canonical
set-like input SHALL be rejected before hashing rather than silently normalized.

The schema bounds SHALL be fixed: a spec has `1..16` scope strings of at most 512 chars
and `0..16` required output paths; a candidate has one `1..256 KiB` result, `0..16`
outputs, `0..32` source refs, at most 8 MiB per output/source body, and at most 32 MiB of
referenced bytes in total. Paths are at most 256 chars, canonical URLs at most 2048
chars, and worker/source identifiers at most 64/128 chars respectively. A submission
record has integer validator version `1..32`, `1..32` unique bytewise-sorted stable
validator check ids, and canonical encoded size at most 64 KiB. Work, candidate result,
and output schema versions SHALL be exactly 1 in this change. Optional lifecycle
timestamps SHALL serialize as explicit nulls when absent so
missing and null do not create two canonical encodings.
Canonical `WorkSpec` bytes SHALL be at most 16 KiB and canonical `CandidateResult` bytes
at most 48 KiB, leaving bounded room for scope and ledger fields inside the 64 KiB
submission-record ceiling.

Every change-04 accepted record SHALL use `validator_version = 1` and the exact sorted
`passed_checks` tuple `("artifact_hashes", "candidate_hash", "identity",
"logical_work_unique", "paths", "result_contract", "source_refs", "work_spec")`, including
checks over empty optional collections. Existing records SHALL never be rewritten when a
later validator version is introduced.

Required output entries SHALL be relative to `outputs/` (`claims.json`, not
`outputs/claims.json` or a bundle path). Canonical relative paths SHALL be non-empty
ASCII POSIX paths without a leading/trailing slash, backslash, NUL, empty segment, `.`,
or `..`. Worker roles SHALL match `[a-z][a-z0-9_]{0,63}`, source ids SHALL match
`[A-Za-z0-9][A-Za-z0-9._:-]{0,127}`, and validator check ids SHALL match
`[a-z][a-z0-9_.-]{0,63}`. Result contract ids SHALL use the same pattern.

Only deterministic controller code SHALL allocate logical work ids, attempt ids,
attempt ordinals, and spec hashes. Planner output MAY provide bounded work intent, but
planner, worker, repair, model text, public tool arguments, and sandbox files SHALL NOT
select or replace controller identity. The controller SHALL persist the canonical
`work-spec.json` before dispatch, and retries SHALL reuse the immutable spec while
creating a new attempt. Runtime projection SHALL derive a work-unit worker context from
the trusted graph scope plus controller-assigned work and attempt ids, with
`attempt_root = <research_root>/work/<work_id>/<attempt_id>`; the worker SHALL NOT choose
that root and the existing phase-level `.../attempts/<id>` projection SHALL NOT be used
as the work-unit artifact root.

The state ownership enum SHALL add closed `WriterRole.SUBMIT` for deterministic submit/
reconciliation code. Ordinary `CONTROLLER` SHALL materialize specs/attempts but SHALL NOT
append accepted refs; `SUBMIT` alone SHALL publish accepted refs and the current terminal-
failure projection while performing its allowed attempt/active-map transition; and
`GATE` SHALL read the validated view without mutating any work-unit authority field.

`NodeSpec` SHALL gain closed capability `WORK_UNIT_CONTROLLER`, declared only by Wave0
and Wave1 in this change. The wrapper SHALL project controller store/resolver
dependencies only to a declaring node; every other node SHALL receive no work-unit
authority and a declaration/runtime mismatch SHALL fail before factory construction.
Per-work resolution SHALL return worker dependencies whose nested
`NodeBuildDependencies.work_units` is always null, with only ordinary execution
capabilities, a trusted work-specific agent context, the fully validated immutable
`WorkSpec` and active `Attempt`, and an optional narrowed fixture artifact writer. For
replay, the controller SHALL derive attempt `a00`'s canonical spec path, read and validate
the plain canonical `work-spec.json`, match identity/role/hash to `WorkSpecRef`, and write
or verify a byte-identical copy at the active retry attempt path before calling the
resolver. Scope/output-contract bodies SHALL come from that validated spec, not the
compact parent ref or caller input.

Retry SHALL be legal only for logical work with no accepted record after a failed or
timed-out attempt. A terminal with code `cancelled` ends the research control path and
SHALL NOT authorize redispatch; `superseded` proves a sibling attempt already won and
SHALL likewise forbid retry. Accepted logical work SHALL never receive another attempt.
A gate-requested quality repair after acceptance SHALL allocate a new logical work id/spec
rather than replace or retry accepted evidence.

#### Scenario: Controller materializes a valid work and attempt
- **WHEN** a deterministic fixture planner returns three bounded work intents for one phase
- **THEN** the controller assigns three unique work ids, writes canonical immutable specs with verified hashes, and assigns each dispatched attempt a unique controller-derived attempt id

#### Scenario: Worker attempts to rewrite authority fields
- **WHEN** a candidate changes its research id, generation, phase, work id, attempt id, worker role, or spec hash from the controller-assigned values
- **THEN** contract validation rejects the candidate before any submission record, accepted reference, or submitted status is published

#### Scenario: Work-unit context uses the canonical bundle root
- **WHEN** the runtime projects dependencies for a controller-assigned work and attempt
- **THEN** the worker sees only the virtual `work/<work_id>/<attempt_id>` root matching `domain/bundle.py`, with no caller-selected path or host workspace value

#### Scenario: Replay changes the spec at the same deterministic cursor
- **WHEN** replay regenerates the same generation/phase/work ordinal but planner intent would produce different canonical spec bytes
- **THEN** the controller keeps the original deterministic work id, reports a spec-hash conflict, and does not hide divergence behind a new id

### Requirement: Typed bounded batches reduce candidates without losing or replacing winners

Checkpointed parent `ResearchState` SHALL use typed work-unit fields for immutable spec
metadata, terminal/aggregate work status, batch and id cursors, bounded attempt history,
and accepted submission refs. A separate typed, size-bounded child state SHALL own the
current replay unit's pending work, in-flight attempts, and candidate fan-in. Because the
current Wave child is manually invoked, those transient channels SHALL use explicit
`checkpointer=False`; after a crash they SHALL be reconstructed deterministically from
the last parent checkpoint and reconciled against the ledger before redispatch.

The child state SHALL have exactly sorted `planned_work_ids` (max 32), sorted
`pending_work_ids` (max 32), `batch_cursor`, `in_flight_by_attempt_id` (max 16),
`candidates_by_attempt_id` (max 16), and `terminal_updates_by_attempt_id` (max 64).
An `AttemptTerminalUpdate` SHALL contain only attempt id, terminal status, UTC terminal
timestamp, terminal code, and optional ordered closed validation codes.
Terminal code `validation_failed` SHALL require a non-empty validation-code tuple in the
closed registry order; every other terminal code SHALL require that tuple to be empty.
In-flight, candidate, and terminal-update reducers SHALL treat identical keyed values as
idempotent and different values as conflicts. The sole deferred submit node SHALL run
after current workers, process sorted attempt keys, accumulate terminal updates, and
clear only the in-flight/candidate maps with LangGraph `Overwrite({})` before refill; it
SHALL NOT write the aggregated candidate map back through its reducer or clear terminal
updates before the child returns.

The child SHALL compile with `checkpointer=False` and SHALL be invoked with internal
`recursion_limit=128`, sufficient for 32 work items at concurrency 1. Public/root config
SHALL NOT select or lower that internal limit.

The phase-local work-unit component SHALL select pending work in stable order and emit no
more LangGraph `Send` calls than its construction-time concurrency limit. The change-04
Wave0 and Wave1 fixtures SHALL use exactly 3; generic construction SHALL accept only
`1..16`; the limit SHALL NOT be a caller-supplied authority field. Work SHALL be ordered
by ordinal/zero-padded id. `batch_cursor` SHALL be the zero-based next-undispatched index,
allocation SHALL select the next slice of at most the limit and advance by the emitted
count before dispatch, and worker completion SHALL NOT move the cursor.

`work_specs_by_id` SHALL be keyed by logical work id. `attempts_by_id` and the retained
compatibility field `work_status_by_id` SHALL both be keyed by attempt id.
`active_attempt_by_work_id` SHALL map each logical work to at most one non-terminal
attempt. Retry SHALL append a new attempt/status entry and SHALL NOT replace or downgrade
an old terminal entry. Compact map values SHALL omit identity derivable from their
validated keys: `WorkSpecRef` contains only worker role and spec hash; `AttemptRef`
contains only lifecycle timestamps and terminal code; and
`terminal_failures_by_attempt_id` values contain only failure code and detail hash.
Classification SHALL be derived from the existing closed `FailureCode` registry when the
gate view is built and SHALL NOT be duplicated in checkpoint state. Attempt work id/
ordinal and spec hash SHALL be recovered from the attempt id plus `work_specs_by_id`,
never duplicated in the value.
`detail_hash` SHALL be the standard `h_<base64url-no-padding>` SHA256 of exact canonical
JSON object `{"terminal_code": <enum>, "validation_codes": [<ordered enums>]}` prefixed
by exact ASCII-plus-NUL domain `deerflow-deep-research:terminal-failure-detail:v1\0`.
Non-validation terminals SHALL use an empty validation-code list; free-form worker/model
text SHALL never enter that hash or the checkpoint.
The canonical first-spec path SHALL be derived from the trusted research id and work id
as attempt `a00`'s `work-spec.json` through `domain/bundle.py`; it SHALL NOT be persisted
inside `WorkSpecRef`. Retry spec paths SHALL likewise derive from their attempt ids.

`terminal_failures_by_attempt_id` SHALL be the bounded current gate projection, not the
terminal-history authority. It SHALL contain at most one summary per logical work for the
selected highest terminal unaccepted attempt; an accepted work has none. The controller
SHALL publish the complete validated mapping with replacement semantics when a retry
changes that selection. The replaced attempt SHALL remain immutable in `attempts_by_id`
and `work_status_by_id`, so this derived projection update SHALL NOT erase terminal
history or count as silent eviction.

Compact refs/summaries SHALL be validated by frozen extra-forbid Pydantic models, but
checkpoint channels SHALL persist their `model_dump(mode="json")` plain mappings rather
than opaque model instances. Reducers and checkpoint loading SHALL accept model/mapping
input, validate and normalize it through the same model, and use that exact JSON-mode
representation for size accounting, replay equality, and checkpoint output.

The active parent window SHALL contain at most 32 logical works, 64 attempts, 32 terminal
failure summaries, and 64 accepted record hashes. Canonical JSON for exactly the parent
work-unit fields SHALL be at most 40,960 bytes. The budget object SHALL contain exactly
`pending_work_ids`, `batch_cursor`, `next_work_ordinal`,
`next_attempt_ordinal_by_work_id`, `work_specs_by_id`, `attempts_by_id`,
`work_status_by_id`, `active_attempt_by_work_id`,
`terminal_failures_by_attempt_id`, and `accepted_submission_refs` under sorted-key compact
JSON; none may be omitted from the size calculation. The existing 65,536-byte whole-
state limit SHALL still apply. Exceeding a collection, work-block, or whole-state bound
SHALL fail closed without truncation or silent eviction. A maximum-shape golden fixture
SHALL prove the independent-field 32/64/32/64 work-block upper envelope fits its budget.
A separate legal all-terminal fixture at the same four collection maxima, with empty
pending/active maps, SHALL fit the whole-state bound when combined with a maximum-length
single-byte ASCII request text. Other request/control combinations SHALL remain subject
to the unchanged whole-state failure rather than receiving a larger request allowance.

Compatibility SHALL be one-way for upgrade: the change-04 reader SHALL load old version-
2 checkpoints with absent fields defaulted, while a pre-change reader MAY reject a newly
written version-2 payload containing added fields. Rollback SHALL fail closed and require
a fresh research run; it SHALL NOT claim that old code ignores new fields.

Candidate fan-in SHALL reduce by `(work_id, attempt_id)`, normalize stable order, treat
same-hash replay as idempotent, reject different-hash replay as a conflict, and preserve
terminal monotonicity. A terminal attempt SHALL have at most one winner and SHALL NOT be
downgraded to pending or running by a stale branch.

Controller materialization and `SUBMIT` operations SHALL each be writer-authorized
against their applicable current/preview state, then one pure cross-field validator SHALL
check the final parent projection across spec ref, attempt ref, status, active mapping,
selected failure, and accepted ref before the node returns. Worker/model output SHALL
never be accepted as a parent-state delta. Parent reducers SHALL enforce keyed replay and
terminal monotonicity on that coalesced projection; they SHALL NOT infer missing internal
child transitions from a single status field.

#### Scenario: Three workers finish in arbitrary scheduler order
- **WHEN** three fixture workers are dispatched in one bounded batch and complete in any order
- **THEN** all three candidates are retained exactly once, normalized by stable work/attempt identity, submitted at most once each, and no candidate is lost at fan-in

#### Scenario: Two branches claim different winners for one attempt
- **WHEN** concurrent branches return different candidate hashes for the same work and attempt identity
- **THEN** the reducer raises a typed conflict, publishes no accepted winner for that attempt, and does not use last-write-wins behavior

#### Scenario: Retry preserves terminal attempt history
- **WHEN** a failed attempt is retried for the same immutable work
- **THEN** the old attempt/status entry remains terminal, a fresh attempt id is appended and becomes the sole active attempt for the work, and no reducer rewrites history

#### Scenario: Accepted work needs a quality repair
- **WHEN** a gate requests revised evidence after the logical work already has a valid accepted record
- **THEN** planning allocates a new logical work id and leaves the accepted work/record immutable rather than creating a sibling attempt

#### Scenario: Maximum parent work window remains serializable
- **WHEN** the compact parent budget fixture independently maximizes every declared work field and a separate legal all-terminal state reaches 32 logical works, 64 attempts, 32 selected failures, and 64 accepted hashes
- **THEN** the pessimistic work-block encoding is at most 40,960 bytes and the legal full checkpoint with maximum-length single-byte ASCII request is at most 65,536 bytes without truncation

### Requirement: Deterministic submit validation fails closed before evidence acceptance

The submit validator SHALL validate, in stable order, the candidate schema/version,
trusted research/generation/phase/work/attempt/role identity, immutable spec hash,
canonical `work-spec.json`, expected result contract, result path, declared output
paths, non-empty file bodies, content hashes, and source references. Every result and
output path SHALL resolve beneath the trusted research workspace and the assigned
attempt root after symlink resolution. Source URLs SHALL be canonicalized and every
declared source/cache ref SHALL have a contained path and matching hash. The validator
SHALL return closed typed failure codes and SHALL NOT infer success from worker summary
text, file names alone, run events, or a `completed` finish reason.

The closed validation registry and collect-all precedence SHALL be exactly:
`identity_mismatch`, `work_spec_missing`, `spec_hash_mismatch`,
`schema_version_unsupported`, `result_contract_unsupported`,
`invalid_output_schema`, `path_not_canonical`, `path_not_contained`,
`artifact_missing`, `artifact_empty`, `content_hash_mismatch`,
`source_ref_invalid`, `candidate_hash_mismatch`, `candidate_conflict`. Results SHALL be
deduplicated by code in that order. Symlink/path-swap failures SHALL use
`path_not_contained`; only missing `work-spec.json` SHALL use `work_spec_missing`; every
other missing file SHALL use `artifact_missing`.

Persisted, checkpointed, and ledger path refs SHALL use the existing canonical relative
bundle form `workspace/deep-research/<research_id>/...`. Only runtime projection SHALL
convert that form to the model/tool virtual `/mnt/user-data/workspace/...` path or the
trusted host path. Absolute virtual paths and host paths SHALL NOT be hashed or persisted
as authority refs.

For attempt root `A`, the canonical spec/result refs SHALL be exactly
`A/work-spec.json` and `A/result.json`; an output requirement `p` SHALL map exactly to
`A/outputs/p`. A retry SHALL receive a byte-identical `work-spec.json` copy under its new
attempt root while the logical `WorkSpec` and spec hash remain unchanged.

The pure validator SHALL dispatch through a closed `(result_contract,
result_schema_version)` registry. Change 04 SHALL register exactly
`(fixture.work-unit, 1)`. Its canonical `FixtureResultDocument` SHALL contain schema
version, repeated research/generation/phase/work/attempt/role identity, spec hash,
`result_contract = fixture.work-unit`, `fixture_marker = non_research_fixture`,
bytewise-sorted `output_paths`, and `source_ids = []`. Its output paths and the
candidate's output refs SHALL correspond exactly to `WorkSpec.required_outputs`: each
required entry `p` maps to exactly one canonical candidate ref at
`<attempt_root>/outputs/<p>`. Missing or extra outputs SHALL fail validation. Later phases MAY register additional result
contracts but SHALL reuse the same validator/store/submit path.

Canonical source URLs SHALL be absolute HTTP(S), contain no userinfo, use lowercase
scheme and ASCII/IDNA host, omit default port 80/443, map an empty path to `/`, remove a
trailing slash only from a non-root path, remove fragments, and otherwise preserve path
percent-octets and query bytes. Inputs that are not already equal to that canonical form
SHALL be rejected rather than silently hashed under a rewritten spelling.

#### Scenario: Worker says complete without a result artifact
- **WHEN** a worker returns a completion summary but `result.json` or a declared output file is absent or empty
- **THEN** submit fails with a stable validation code, the attempt is not accepted, and no submission ledger record or accepted ref is produced

#### Scenario: Candidate contains invalid identity, path, hash, or source data
- **WHEN** a candidate has a wrong id, an absolute/traversing/symlink-escaping path, a mismatched file hash, a non-canonical or mismatched source ref, or an unsupported schema version
- **THEN** submit fails closed before ledger mutation and reports the applicable typed validation failures in stable order

#### Scenario: Fixture result contract or output set diverges
- **WHEN** `result.json` has another contract/marker, or its output paths are missing, extra, unsorted, or different from the spec and candidate refs
- **THEN** submit reports invalid output schema before ledger mutation and does not infer completion from the worker result envelope

### Requirement: The controller submit path is the sole accepted-evidence writer

The evidence authority SHALL be
`workspace/deep-research/<research_id>/evidence/submissions.jsonl`, represented as
canonical newline-terminated JSON records whose `previous_record_hash` and
`record_hash` form a validated hash chain. A record SHALL include the logical work and
attempt identity, generation, phase, worker role and scope, immutable spec hash,
candidate/result/output/source refs and hashes, result schema version, validator
version, passed checks, controller timestamp, previous hash, and record hash.

The stable lock SHALL be `evidence/.submissions.lock`; staging files SHALL match
`evidence/.submissions.<32-lowercase-hex>.tmp`, stay in the same directory as the ledger,
use exclusive mode-`0600` creation, and never be persisted as refs or authority. The
evidence directory, lock, ledger, and staging paths SHALL use descriptor-relative and
no-follow access, SHALL reject symlink or non-regular lock/ledger entries before
publication, and SHALL make storage not ready when those POSIX primitives are absent.
The stable lock SHALL open with `O_CREAT | O_RDWR | O_NOFOLLOW` and requested mode
`0600`; existing lock and ledger files SHALL have no group/world permission bits. Atomic
publication SHALL leave the ledger at the staging file's `0600` mode.
The first record SHALL contain explicit `previous_record_hash: null`; each later record
SHALL reference the immediately preceding record hash. Empty ledger bytes SHALL be
valid; blank lines, CRLF, a missing final LF, or more than one line terminator after a
record SHALL fail canonical parsing.

Only the runtime-backed deterministic controller submit path SHALL validate and publish
records and update `accepted_submission_refs`. Planner, worker, repair, gate, model,
public tool input, and direct sandbox content SHALL have no ledger mutation capability.
Gate and later synthesis consumers SHALL count evidence only when an accepted state ref
resolves to the matching valid ledger record; an orphan file or unreferenced ledger
line SHALL not count.
The store SHALL enforce explicit per-record, record-count, and total-ledger byte bounds
before parsing or rewriting so an oversized or unbounded ledger fails closed rather than
blocking the event loop or exhausting memory. Those bounds SHALL be 64 KiB per canonical
record, 4,096 records, and 8 MiB for the complete newline-terminated ledger.

The atomic compare-and-set SHALL index accepted records by logical `work_id` as well as
attempt identity. At most one `SubmissionRecord` SHALL exist for one logical work in a
generation/phase, even across retry attempts. The same attempt and same candidate hash
SHALL reuse the existing record; the same attempt and different candidate hash SHALL
conflict; a different attempt after the logical work is accepted SHALL receive
`work_already_accepted`, publish no second record, and be terminally superseded during
reconciliation. More than one existing record for one logical work SHALL be treated as
ledger corruption.

#### Scenario: Valid candidate becomes accepted evidence
- **WHEN** submit receives a valid candidate and intact declared files for an active attempt
- **THEN** exactly one hash-chained `SubmissionRecord` is published, the attempt becomes submitted, and its record hash is dedupe-appended to `accepted_submission_refs` in the same state update

#### Scenario: Non-submit actor attempts ledger mutation
- **WHEN** a planner, worker, repair agent, gate, or model-facing capability attempts to append a record or publish an accepted ref
- **THEN** the ownership boundary rejects the operation and the ledger, attempt status, and accepted refs remain unchanged

#### Scenario: Old and retry attempts both present valid candidates
- **WHEN** candidates for two attempts of the same logical work reach the serialized store
- **THEN** the first accepted record is the sole logical-work winner, the other attempt cannot append a second record, and reconciliation exposes only the winner's record hash

### Requirement: Ledger and checkpoint crash windows reconcile idempotently

Submit SHALL treat the validated ledger as evidence truth and checkpointed
`ResearchState` as control truth without pretending they share one database
transaction. The last durable parent checkpoint MAY predate execution of the current
bounded phase step; controller allocation SHALL therefore be deterministic from that
checkpoint, and replay SHALL reconcile the regenerated work/attempt identities against
the ledger before redispatch. A successful submit node SHALL return submitted status
and its accepted ref together as one state update. On replay, reconciliation SHALL
validate the entire ledger/hash chain and compare the attempt's stable candidate
fingerprint before deciding whether to append, catch up the checkpoint, skip, or fail
closed.

A matching ledger record that exists before its accepted ref is checkpointed SHALL be
reused and SHALL repair the missing checkpoint ref without a second append. A candidate
re-executed from a pre-submit checkpoint SHALL be validated and submitted normally after
restart. The implementation SHALL NOT claim durable nested candidate checkpoints unless
the child graph is directly bound to the parent checkpointer; change 04 instead treats
the bounded Wave node as the replay unit. An accepted ref or submitted state without the
matching valid ledger record, and any replay whose stable candidate fingerprint differs
from the accepted record, SHALL fail closed.

Reusing a matching record SHALL repeat contained file reads and validate the current
canonical spec/result/output/source bytes against the record's hashes. Matching stored
`candidate_hash` alone SHALL NOT accept missing or mutated artifact content. A valid
accepted record for a sibling attempt of the same logical work SHALL suppress worker
redispatch and supersede the active retry rather than create a second winner. More than
one record for one logical work, a broken chain, or a submitted/ref checkpoint with no
valid matching record SHALL fail closed.

Broken chain, duplicate logical-work records, or a submitted/accepted checkpoint hash
with no matching valid ledger record SHALL return `work_unit_storage_unavailable` with
stable redacted reason `ledger_corrupt`. Missing or mutated files referenced by an
already accepted record SHALL return the same
infrastructure code with reason `accepted_artifact_diverged`. Both SHALL return without
checkpoint mutation and SHALL NOT create a repairable attempt/gate failure. Initial
candidate validation defects before acceptance remain ordinary typed work failures.

#### Scenario: Crash occurs after ledger publication but before checkpoint update
- **WHEN** fault injection stops execution after the atomic ledger publish and before the submit node's state update is checkpointed
- **THEN** replay finds the same record, performs no second append, and publishes the missing submitted status and accepted ref

#### Scenario: Checkpoint predates accepted-ref publication
- **WHEN** fault injection restarts the bounded phase step from its last parent checkpoint before the ledger record and accepted ref were published
- **THEN** deterministic allocation recreates the same work/attempt identities, reconciliation runs before worker redispatch, and an unaccepted attempt is re-executed or submitted without inventing checkpoint evidence

#### Scenario: Replay candidate diverges from accepted evidence
- **WHEN** replay presents a different candidate hash for an attempt whose valid accepted ledger record already exists
- **THEN** reconciliation returns `candidate_conflict`, neither repairs by last-write-wins nor appends a replacement record, and leaves the accepted authority unchanged

#### Scenario: Checkpoint references a missing accepted ledger record
- **WHEN** submitted state or an accepted checkpoint hash has no matching valid ledger record
- **THEN** reconciliation returns `work_unit_storage_unavailable` with redacted reason `ledger_corrupt`, performs no checkpoint repair, and never recreates evidence from state

#### Scenario: Matching fingerprint points to mutated files
- **WHEN** replay finds the same stored candidate hash but a referenced spec, result, output, or source file is missing or has different bytes
- **THEN** reconciliation returns `work_unit_storage_unavailable` with redacted reason `accepted_artifact_diverged`, performs no checkpoint repair, and appends no replacement record

#### Scenario: Ledger accepts an earlier attempt before retry state catches up
- **WHEN** replay has an active retry but the valid ledger already contains the sole accepted record for an earlier attempt of that work
- **THEN** reconciliation revalidates the existing record, skips the retry worker, publishes only the existing accepted ref, and terminally supersedes the retry

#### Scenario: Ledger authority is structurally corrupt
- **WHEN** chain verification fails or more than one accepted record exists for one logical work
- **THEN** reconciliation returns `work_unit_storage_unavailable` with redacted reason `ledger_corrupt`, performs no checkpoint repair or worker dispatch, and preserves the bytes for diagnosis

### Requirement: Per-research cross-process serialization prevents duplicate or partial publication

The runtime-owned submission store SHALL serialize the complete read-validate-compare-
publish operation for one research id across independent process instances sharing the
trusted workspace. Before any work artifact or ledger access, runtime SHALL verify that
the parent sandbox and trusted host workspace expose the same physical thread workspace
and that the filesystem supports the required POSIX lock/replace/fsync contract. A
remote, non-mounted, custom, or otherwise unverified provider SHALL fail readiness and
runtime execution with `work_unit_storage_unavailable`; it SHALL NOT fall back to a
separate host ledger. The reflected lifecycle action SHALL return that infrastructure
code without checkpoint mutation. Different research ids SHALL not share one global
mutation lock.

Runtime work-unit dependency/store construction SHALL be asynchronous and occur only
immediately before a start/resume graph invocation that may enter a declaring Wave
controller. After action validation, the reflected tool SHALL call the runtime adapter
with parent-sandbox initialization disabled for status/cancel and enabled for start/
resume; the trusted envelope parent sandbox SHALL therefore be optional. Status and
cancel SHALL remain checkpoint-only and SHALL not initialize or require a parent sandbox
or work-unit store. Cancel SHALL use an invocation context with no work-unit controller
dependency; any malformed route from cancel into a declaring Wave node SHALL fail the
capability check before factory construction. Typed store errors SHALL unwind through
GraphHost so the checkpointer provider closes, then be projected only at the reflected-
tool boundary.

The cross-process guarantee SHALL cover the ledger compare-and-set and SHALL guarantee
at most one accepted record per logical work. It SHALL NOT claim a distributed
transaction or newest-attempt priority across independent Gateway processes holding
split-brain checkpoint snapshots. Supported lifecycle mutation remains serialized by the
single-process/single-worker GraphHost; if unsupported split-brain submitters race
different attempts, the ledger still yields one winner but does not promise which
attempt wins. Runtime SHALL reject terminal/superseded attempts from the current trusted
state before they reach the store.

Ledger publication SHALL be atomic: a crash or write failure SHALL leave either the
previous complete ledger or the next complete newline-terminated ledger as authority;
staging files SHALL never count as records. Lock acquisition SHALL use a bounded timeout
of two seconds with 25 ms nonblocking retry intervals and return retryable
`work_unit_store_busy` without checkpoint mutation rather than leave
an uncancellable blocking thread. Blocking filesystem and lock operations SHALL run off
the async event loop, and cancellation SHALL not expose a half-published ledger or leak a
held lock.

Store failures SHALL expose only the closed redacted reasons
`aio_provisioner_unmounted | e2b_unmounted | boxlite_unmounted |
provider_unrecognized | thread_mount_unavailable | workspace_alias_mismatch |
posix_primitives_unavailable | probe_cleanup_failed | ledger_corrupt |
accepted_artifact_diverged | lock_timeout`; only `lock_timeout` SHALL pair with
`work_unit_store_busy`, and every other reason SHALL pair with
`work_unit_storage_unavailable`.

`DeepResearchControlResult` SHALL add optional typed `infrastructure_reason`. It SHALL be
required exactly for `work_unit_storage_unavailable | work_unit_store_busy`, forbidden
for all other result codes, and SHALL enforce the reason/code pairing above. The tool
SHALL catch `WorkUnitStoreError` first and preserve only that enum; it SHALL NOT collapse
the result to `checkpoint_inconsistent` or include free-form detail. Known typed errors
SHALL retain their current projection. A final redacted `except Exception` SHALL map
unexpected graph/domain invariant failures to `checkpoint_inconsistent` without
exception text, SHALL run only after GraphHost resource unwinding, and SHALL NOT catch
`BaseException` or cancellation.

#### Scenario: Independent processes race the same candidate
- **WHEN** two independent store instances concurrently submit the same candidate for one work/attempt against a shared workspace
- **THEN** one complete record becomes authoritative, both callers observe the same accepted record hash, and the ledger contains one winner

#### Scenario: Independent processes race divergent candidates
- **WHEN** two independent store instances concurrently submit different candidate hashes for the same work/attempt
- **THEN** at most one candidate is accepted, the other receives a conflict, and the ledger remains a complete valid hash chain with no partial line

#### Scenario: Independent store processes race different attempts
- **WHEN** unsupported split-brain callers present candidates from two attempts of one logical work to independent store instances
- **THEN** the ledger compare-and-set accepts at most one logical-work record and reports the other as already accepted or conflicting, without claiming that the newer ordinal is guaranteed to win

#### Scenario: Sandbox and host workspace are not shared
- **WHEN** the configured sandbox provider keeps `/mnt/user-data/workspace` in a remote or non-mounted filesystem that cannot be proven identical to the trusted host workspace
- **THEN** doctor reports runtime not ready and the lifecycle action returns `work_unit_storage_unavailable` before controller spec write, worker dispatch, ledger access, checkpoint update, or accepted-ref mutation

#### Scenario: Per-research lock cannot be acquired before deadline
- **WHEN** another process holds the research ledger lock beyond the fixed construction-time internal deadline
- **THEN** the lifecycle action returns retryable `work_unit_store_busy`, leaves checkpoint and ledger unchanged, releases every local resource, and may be retried from the same state

#### Scenario: Storage outage does not block cancellation
- **WHEN** work-unit storage readiness fails while an existing research is suspended at a cancellable HITL boundary
- **THEN** the adapter does not initialize the parent sandbox, cancel resumes the checkpoint-only control path without constructing the store, records cancellation normally, and exposes no ledger authority to the canceling node

### Requirement: Attempt retry, expiry, cancellation, and crash recovery are one-way

Attempt statuses SHALL be one-way across `pending | running | submitted | failed |
timed_out | cancelled`. Once terminal, an attempt SHALL NOT return to pending or running.
A repair/retry after `failed` or `timed_out` SHALL create a new controller-assigned
attempt id and ordinal for the same immutable work spec. `cancelled` and `superseded`
attempts SHALL never authorize retry. The first version SHALL fail closed on a candidate
from any expired, cancelled, or superseded attempt and SHALL NOT implement a late-submit
winner.

The only state changes SHALL be `pending -> running`, `pending -> cancelled`, and
`running -> submitted | failed | timed_out | cancelled`. Reapplying the same status with
identical timestamps and terminal code SHALL be idempotent. Any same-status detail
mismatch, direct `pending -> submitted|failed|timed_out`, transition out of a terminal
status, mutation of immutable identity/spec/created-at fields, or replacement that is not
the validated next lifecycle version SHALL be a conflict. A legal transition publishes a
new frozen `Attempt` value for the same key with only its permitted lifecycle fields
advanced. Retry SHALL append a fresh attempt and SHALL preserve every prior terminal
entry.

Those adjacency rules SHALL govern kernel transition operations. The manually invoked
child is one atomic parent node, so a validated parent update MAY coalesce multiple legal
internal transitions and first project a new attempt as terminal, or project an existing
non-terminal attempt at its later terminal state. Before return, the cross-field parent-
projection validator SHALL prove the attempt timestamps/code/status, active-map removal,
failure selection, and accepted ref are mutually consistent. This allowance SHALL NOT
permit reopening/replacing a checkpointed terminal attempt or bypassing the internal
transition tests.

Terminal codes SHALL be the closed set
`accepted | worker_failed | validation_failed | candidate_conflict |
deadline_exceeded | expired | cancelled | superseded` with these
status mappings: submitted uses only `accepted`; failed uses
`worker_failed | validation_failed | candidate_conflict`; timed out
uses `deadline_exceeded | expired`; cancelled uses `cancelled | superseded`.
Pending/running attempts SHALL have null terminal timestamp/code; terminal attempts SHALL
have both. `created_at` SHALL always be present, `started_at` SHALL be present after
running, and direct pending-to-cancelled MAY keep `started_at` null.
All timestamps SHALL be timezone-aware UTC with monotonic ordering:
`created_at <= started_at <= terminal_at` when started,
`created_at <= terminal_at` for direct cancellation, and `expires_at > created_at` when
set. `expired` SHALL require `terminal_at >= expires_at`; submit SHALL reject a candidate
when the injected current UTC time is greater than or equal to `expires_at`.

Replay SHALL skip work already proven submitted by a valid accepted ledger record.
Non-terminal work interrupted before acceptance MAY execute again with the same active
attempt when replaying the same graph step; after explicit failure or timeout, further
execution requires a new retry attempt. Cancellation SHALL propagate, SHALL never be
converted into worker success, and SHALL not authorize retry. A superseded attempt SHALL
remain closed because a sibling accepted record is authoritative.

#### Scenario: Failed work is retried
- **WHEN** an attempt reaches failed or timed-out status and repair schedules the logical work again
- **THEN** the controller preserves the original spec hash, allocates a strictly newer attempt id, and refuses any later candidate from the old attempt

#### Scenario: Crash recovery distinguishes accepted and unaccepted attempts
- **WHEN** a process restarts with one attempt present in the accepted ledger and another attempt without an accepted record
- **THEN** the accepted attempt is skipped idempotently while the non-terminal unaccepted attempt may be re-executed without creating a second winner

#### Scenario: Cancellation or expiry races a late candidate
- **WHEN** an attempt is cancelled, timed out, expired, or superseded before its candidate is submitted
- **THEN** the late candidate is rejected and no ledger record is added for that attempt; failed/timed-out work may continue only through a fresh retry, while cancelled/superseded work cannot be redispatched

#### Scenario: Terminal transition is replayed exactly
- **WHEN** replay applies the same terminal status, timestamp, and terminal code to an existing attempt
- **THEN** the reducer treats it as an idempotent no-op, while any changed terminal detail or attempted reopening is rejected as a conflict

### Requirement: Generic phase drain gates on empty pending and in-flight work

The work-unit kernel SHALL expose one deterministic phase drain predicate shared by
Wave0, Wave1, targeted evidence, and rerun consumers. A phase SHALL NOT invoke its gate
while any logical work remains pending or any attempt remains in flight. Terminal
failed, timed-out, or cancelled attempts MAY make the queue structurally drained, but
their typed failures SHALL remain available to gate rules; drain SHALL never imply gate
pass or evidence coverage. Wave0 and Wave1 gate definitions SHALL include one shared
deterministic work-completion rule ahead of their fixture rule. It SHALL verify structural
drain, terminal status, and the bounded pure accepted-coverage view produced by the
controller's immediately preceding ledger reconciliation for every planned work item,
and map typed submission failures to the existing closed gate failure registry. The rule
SHALL perform no filesystem I/O. A fixture
`pass` SHALL NOT override missing, failed, conflicting, unaccepted, or invalid work.

The frozen ephemeral `WorkUnitGateView` SHALL contain only `drained`, sorted
`planned_work_ids`, `terminal_attempt_by_work_id`,
`accepted_record_by_work_id`, and ordered bounded failure summaries, each collection
limited to 32 entries. It SHALL contain no scope, artifact path, candidate body, ledger
record, cursor, phase, route, fixture counter, or host/virtual path and SHALL never be
checkpointed.
For one work it SHALL select the accepted attempt when present, otherwise the highest
terminal attempt ordinal, and SHALL include at most one matching failure summary ordered
by work id.
Each ephemeral `WorkUnitGateFailure` SHALL contain exactly work id, attempt id, failure
code, classification derived from that code, and detail hash. It SHALL be constructed
from the keyed compact parent failure but SHALL be a separate non-checkpointed type so
identity carried by the parent map key is not lost in the ordered tuple.

Because an accepted record hash alone does not encode its logical work id, the reconciler
SHALL return the typed view to a declaring Wave node under exact reserved mapping key
`__work_unit_gate_view__`. `_node_wrapper` SHALL copy the result, pop and type-check the
view before reducer preview, reject that key from every non-`WORK_UNIT_CONTROLLER` node,
inject it only into the in-memory gate mapping, and omit it from the final state update.
The reserved key SHALL not be a `ResearchState` field and SHALL never reach LangGraph
reduction or checkpoint serialization.

View validation SHALL have two explicit stages. Before child return, while reconciled
records and the exact child plan are still available, a pure component validator SHALL
prove that `planned_work_ids` exactly equals the child plan, each accepted
`work_id -> record_hash` pair matches the reconciled `SubmissionRecord` work/attempt/hash
association, terminal selection is canonical, and the view agrees with the complete final
parent projection. After reserved-key extraction, a separate wrapper validator SHALL
prove only what the reducer preview can establish: planned ids are sorted/unique, belong
to the previewed current-phase spec map, and exactly key the terminal map; each
terminal attempt exists, derives the mapped work id, and has a terminal preview status;
each accepted work selects a submitted attempt whose hash is present in previewed
`accepted_submission_refs`, while an unaccepted work does not select submitted; and each
selected failure matches `terminal_failures_by_attempt_id`. The wrapper SHALL NOT claim
to reconstruct record-to-work association from accepted hashes. Either mismatch SHALL
raise `work_unit_gate_view_inconsistent` before fixture/business gate evaluation and
SHALL NOT be converted into a repairable work failure.

For a declaring Wave node, `_node_wrapper` SHALL construct the gate input by shallow-
copying the input checkpoint and previewing exactly `work_specs_by_id`, `attempts_by_id`,
`work_status_by_id`, `active_attempt_by_work_id`,
`terminal_failures_by_attempt_id`, and `accepted_submission_refs` through their explicit
domain reducers. It SHALL NOT inspect LangGraph channel internals, mutate the input or
node delta, preview phase/route/trace/cursors/gate fields, or return the merged preview as
the node update. The node delta and gate update SHALL have disjoint keys; overlap SHALL
fail as `node_gate_write_conflict`, and LangGraph SHALL apply each returned reducer delta
exactly once.

The deterministic submit projection SHALL map validation detail to the compact parent
failure exactly once. For a validation failure, it SHALL select the first code in the
closed collect-all precedence as primary, hash the complete ordered validation-code tuple
into `detail_hash`, and map `work_spec_missing -> MISSING_WORK_SPEC`;
`identity_mismatch | spec_hash_mismatch -> IDENTITY_MISMATCH`;
`schema_version_unsupported -> SCHEMA_VERSION_UNSUPPORTED`;
`result_contract_unsupported | invalid_output_schema | path_not_canonical |
path_not_contained | artifact_missing | artifact_empty | source_ref_invalid ->
INVALID_OUTPUT_SCHEMA`; `content_hash_mismatch | candidate_hash_mismatch ->
CONTENT_HASH_MISMATCH`; and `candidate_conflict -> WORK_FAILED`. Non-validation terminal
codes SHALL map at the same boundary as follows: `worker_failed | candidate_conflict ->
WORK_FAILED`, `deadline_exceeded | expired -> WORK_TIMED_OUT`, and `cancelled |
superseded -> WORK_CANCELLED`. Submitted/accepted attempts SHALL have no failure summary.
`WorkUnitCompletionRule` SHALL consume the already mapped `FailureCode` and SHALL NOT
repeat or reinterpret this mapping.

#### Scenario: Pending or running work blocks phase gate
- **WHEN** either `pending_work_ids` or active in-flight attempts are non-empty after a batch
- **THEN** the component schedules the next bounded batch or waits for fan-in and does not invoke the phase gate

#### Scenario: Terminal batch reaches gate without inventing success
- **WHEN** pending and in-flight collections are empty after all attempts become terminal
- **THEN** the phase may invoke its gate against a reducer-previewed post-work state, and the gate sees the current batch's accepted refs plus terminal failures rather than stale input or drain alone

#### Scenario: Ephemeral gate view diverges from the returned state delta
- **WHEN** a controller result's reserved view names a missing terminal attempt, accepted hash, planned work, or selected failure relative to the reducer preview
- **THEN** the wrapper raises `work_unit_gate_view_inconsistent` before gate rules or state reduction, the reserved key is never checkpointed, and the reflected tool returns redacted `checkpoint_inconsistent`

#### Scenario: Fixture pass cannot override failed submit
- **WHEN** a Wave fixture route is `pass` but one planned work item lacks a valid accepted record or carries a terminal submit-validation failure
- **THEN** the shared work-completion rule returns a typed hard or repairable failure, the collect-all gate does not pass, and the fixture rule cannot suppress that failure
