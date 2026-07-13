> req: WOU-001, WOU-002, WOU-003, WOU-004, WOU-005, WOU-006, WOU-007, WOU-008

## ADDED Requirements

### Requirement: Controller-assigned immutable work contracts preserve identity and spec integrity

The downstream package SHALL define frozen, versioned, extra-forbid contracts for
`WorkSpec`, `Attempt`, `CandidateResult`, and `SubmissionRecord`. A `WorkSpec` SHALL
bind the trusted research id, generation, logical phase, work id, worker role, bounded
scope, and expected output contract. Its `spec_hash` SHALL be derived from a
domain-separated canonical JSON encoding that excludes the hash field itself. An
`Attempt` SHALL bind one controller-assigned attempt id and ordinal to exactly one work
id and spec hash. A candidate and submission SHALL repeat those identity fields and
carry their own deterministic content hash or fingerprint.

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

#### Scenario: Controller materializes a valid work and attempt
- **WHEN** a deterministic fixture planner returns three bounded work intents for one phase
- **THEN** the controller assigns three unique work ids, writes canonical immutable specs with verified hashes, and assigns each dispatched attempt a unique controller-derived attempt id

#### Scenario: Worker attempts to rewrite authority fields
- **WHEN** a candidate changes its research id, generation, phase, work id, attempt id, worker role, or spec hash from the controller-assigned values
- **THEN** contract validation rejects the candidate before any submission record, accepted reference, or submitted status is published

#### Scenario: Work-unit context uses the canonical bundle root
- **WHEN** the runtime projects dependencies for a controller-assigned work and attempt
- **THEN** the worker sees only the virtual `work/<work_id>/<attempt_id>` root matching `domain/bundle.py`, with no caller-selected path or host workspace value

### Requirement: Typed bounded batches reduce candidates without losing or replacing winners

Checkpointed parent `ResearchState` SHALL use typed work-unit fields for immutable spec
metadata, terminal/aggregate work status, batch and id cursors, bounded attempt history,
and accepted submission refs. A separate typed, size-bounded child state SHALL own the
current replay unit's pending work, in-flight attempts, and candidate fan-in. Because the
current Wave child is manually invoked, those transient channels SHALL use explicit
`checkpointer=False`; after a crash they SHALL be reconstructed deterministically from
the last parent checkpoint and reconciled against the ledger before redispatch.

The phase-local work-unit component SHALL select pending work in stable order and emit no
more LangGraph `Send` calls than its construction-time concurrency limit. The change-04
Wave0 and Wave1 fixtures SHALL use a limit of at least three so three workers can run
concurrently; the limit SHALL NOT be a caller-supplied authority field.

Candidate fan-in SHALL reduce by `(work_id, attempt_id)`, normalize stable order, treat
same-hash replay as idempotent, reject different-hash replay as a conflict, and preserve
terminal monotonicity. A terminal attempt SHALL have at most one winner and SHALL NOT be
downgraded to pending or running by a stale branch.

#### Scenario: Three workers finish in arbitrary scheduler order
- **WHEN** three fixture workers are dispatched in one bounded batch and complete in any order
- **THEN** all three candidates are retained exactly once, normalized by stable work/attempt identity, submitted at most once each, and no candidate is lost at fan-in

#### Scenario: Two branches claim different winners for one attempt
- **WHEN** concurrent branches return different candidate hashes for the same work and attempt identity
- **THEN** the reducer raises a typed conflict, publishes no accepted winner for that attempt, and does not use last-write-wins behavior

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

#### Scenario: Worker says complete without a result artifact
- **WHEN** a worker returns a completion summary but `result.json` or a declared output file is absent or empty
- **THEN** submit fails with a stable validation code, the attempt is not accepted, and no submission ledger record or accepted ref is produced

#### Scenario: Candidate contains invalid identity, path, hash, or source data
- **WHEN** a candidate has a wrong id, an absolute/traversing/symlink-escaping path, a mismatched file hash, a non-canonical or mismatched source ref, or an unsupported schema version
- **THEN** submit fails closed before ledger mutation and reports the applicable typed validation failures in stable order

### Requirement: The controller submit path is the sole accepted-evidence writer

The evidence authority SHALL be
`workspace/deep-research/<research_id>/evidence/submissions.jsonl`, represented as
canonical newline-terminated JSON records whose `previous_record_hash` and
`record_hash` form a validated hash chain. A record SHALL include the logical work and
attempt identity, generation, phase, worker role and scope, immutable spec hash,
candidate/result/output/source refs and hashes, result schema version, validator
version, passed checks, controller timestamp, previous hash, and record hash.

Only the runtime-backed deterministic controller submit path SHALL validate and publish
records and update `accepted_submission_refs`. Planner, worker, repair, gate, model,
public tool input, and direct sandbox content SHALL have no ledger mutation capability.
Gate and later synthesis consumers SHALL count evidence only when an accepted state ref
resolves to the matching valid ledger record; an orphan file or unreferenced ledger
line SHALL not count.
The store SHALL enforce explicit per-record, record-count, and total-ledger byte bounds
before parsing or rewriting so an oversized or unbounded ledger fails closed rather than
blocking the event loop or exhausting memory.

#### Scenario: Valid candidate becomes accepted evidence
- **WHEN** submit receives a valid candidate and intact declared files for an active attempt
- **THEN** exactly one hash-chained `SubmissionRecord` is published, the attempt becomes submitted, and its record hash is dedupe-appended to `accepted_submission_refs` in the same state update

#### Scenario: Non-submit actor attempts ledger mutation
- **WHEN** a planner, worker, repair agent, gate, or model-facing capability attempts to append a record or publish an accepted ref
- **THEN** the ownership boundary rejects the operation and the ledger, attempt status, and accepted refs remain unchanged

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

#### Scenario: Crash occurs after ledger publication but before checkpoint update
- **WHEN** fault injection stops execution after the atomic ledger publish and before the submit node's state update is checkpointed
- **THEN** replay finds the same record, performs no second append, and publishes the missing submitted status and accepted ref

#### Scenario: Checkpoint predates accepted-ref publication
- **WHEN** fault injection restarts the bounded phase step from its last parent checkpoint before the ledger record and accepted ref were published
- **THEN** deterministic allocation recreates the same work/attempt identities, reconciliation runs before worker redispatch, and an unaccepted attempt is re-executed or submitted without inventing checkpoint evidence

#### Scenario: Replay state diverges from evidence authority
- **WHEN** replay presents a different candidate for an already accepted attempt or an accepted checkpoint ref has no matching valid ledger record
- **THEN** reconciliation reports a conflict and neither repairs by last-write-wins nor appends a replacement record

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

Ledger publication SHALL be atomic: a crash or write failure SHALL leave either the
previous complete ledger or the next complete newline-terminated ledger as authority;
staging files SHALL never count as records. Lock acquisition SHALL use a bounded timeout
and return retryable `work_unit_store_busy` without checkpoint mutation rather than leave
an uncancellable blocking thread. Blocking filesystem and lock operations SHALL run off
the async event loop, and cancellation SHALL not expose a half-published ledger or leak a
held lock.

#### Scenario: Independent processes race the same candidate
- **WHEN** two independent store instances concurrently submit the same candidate for one work/attempt against a shared workspace
- **THEN** one complete record becomes authoritative, both callers observe the same accepted record hash, and the ledger contains one winner

#### Scenario: Independent processes race divergent candidates
- **WHEN** two independent store instances concurrently submit different candidate hashes for the same work/attempt
- **THEN** at most one candidate is accepted, the other receives a conflict, and the ledger remains a complete valid hash chain with no partial line

#### Scenario: Sandbox and host workspace are not shared
- **WHEN** the configured sandbox provider keeps `/mnt/user-data/workspace` in a remote or non-mounted filesystem that cannot be proven identical to the trusted host workspace
- **THEN** doctor reports runtime not ready and the lifecycle action returns `work_unit_storage_unavailable` before controller spec write, worker dispatch, ledger access, checkpoint update, or accepted-ref mutation

#### Scenario: Per-research lock cannot be acquired before deadline
- **WHEN** another process holds the research ledger lock beyond the configured internal deadline
- **THEN** the lifecycle action returns retryable `work_unit_store_busy`, leaves checkpoint and ledger unchanged, releases every local resource, and may be retried from the same state

### Requirement: Attempt retry, expiry, cancellation, and crash recovery are one-way

Attempt statuses SHALL be one-way across `pending | running | submitted | failed |
timed_out | cancelled`. Once terminal, an attempt SHALL NOT return to pending or running.
A repair/retry SHALL create a new controller-assigned attempt id and ordinal for the
same immutable work spec. The first version SHALL fail closed on a candidate from an
expired or superseded attempt and SHALL NOT implement a late-submit winner.

Replay SHALL skip work already proven submitted by a valid accepted ledger record.
Non-terminal work interrupted before acceptance MAY execute again with the same active
attempt when replaying the same graph step; after an explicit failure, timeout,
cancellation, or expiry, further execution requires a new retry attempt. Cancellation
SHALL propagate and SHALL never be converted into worker success.

#### Scenario: Failed work is retried
- **WHEN** an attempt reaches failed or timed-out status and repair schedules the logical work again
- **THEN** the controller preserves the original spec hash, allocates a strictly newer attempt id, and refuses any later candidate from the old attempt

#### Scenario: Crash recovery distinguishes accepted and unaccepted attempts
- **WHEN** a process restarts with one attempt present in the accepted ledger and another attempt without an accepted record
- **THEN** the accepted attempt is skipped idempotently while the non-terminal unaccepted attempt may be re-executed without creating a second winner

#### Scenario: Cancellation or expiry races a late candidate
- **WHEN** an attempt is cancelled, timed out, expired, or superseded before its candidate is submitted
- **THEN** the late candidate is rejected, no ledger record is added for that attempt, and only a fresh retry attempt can continue the logical work

### Requirement: Generic phase drain gates on empty pending and in-flight work

The work-unit kernel SHALL expose one deterministic phase drain predicate shared by
Wave0, Wave1, targeted evidence, and rerun consumers. A phase SHALL NOT invoke its gate
while any logical work remains pending or any attempt remains in flight. Terminal
failed, timed-out, or cancelled attempts MAY make the queue structurally drained, but
their typed failures SHALL remain available to gate rules; drain SHALL never imply gate
pass or evidence coverage.

#### Scenario: Pending or running work blocks phase gate
- **WHEN** either `pending_work_ids` or active in-flight attempts are non-empty after a batch
- **THEN** the component schedules the next bounded batch or waits for fan-in and does not invoke the phase gate

#### Scenario: Terminal batch reaches gate without inventing success
- **WHEN** pending and in-flight collections are empty after all attempts become terminal
- **THEN** the phase may invoke its gate against a reducer-previewed post-work state, and the gate sees the current batch's accepted refs plus terminal failures rather than stale input or drain alone
