# DPT Invariant Parity And Release Evidence: 2026-07-17

Status: Superseded by `docs/release-attestation-2026-07-17.json`.

This document is the pre-acceptance snapshot from the same evidence epoch. Its
`NOT READY` and `full-real not executed` statements below are historical and
must not be read as the current release-evidence verdict. The committed
attestation records the later accepted full-real run and its provenance.

Release verdict: NOT READY

This report separates deterministic proof, live observation, and full-real
release evidence. A single successful demo is not release proof. The current
credentialed result is 2 of 3 short-prefix canaries passing; the one-topic
Wave0 canary failed closed. Full-real acceptance: not executed.

## DPT Invariant Parity

| Preserved DPT invariant | Current evidence | Status |
| --- | --- | --- |
| Legal phase and route progression is graph-controlled | Static topology, route contracts, all-real compilation, full-fake lifecycle, and mixed-prefix deterministic scenarios pass. | achieved deterministically |
| Control authority is checkpointed ResearchState | State ownership/reducer, resume, duplicate resume, stale checkpoint, cancellation, restart, and bounded-state tests pass. | achieved deterministically |
| Evidence authority is the accepted-submission ledger | Identity, schema, hash, atomic publication, conflict, replay, and gate-input tests pass; scripted real workers reach the authoritative store. | achieved deterministically |
| Content authority is the sandbox filesystem | Mounted-workspace, containment, no-follow reads, attempt isolation, durability, cleanup, and real final-file publication tests pass. The runtime atomically publishes both canonical final files and returns refs whose hashes match stored bytes, so final artifact materialization: achieved deterministically. | achieved deterministically |
| Work and retry authority remains controller-owned | Immutable work/attempt identity, bounded dispatch, new-attempt retry, drain, conflict, fatigue, and exhausted outcomes pass deterministic tests. | achieved deterministically |
| Gates cannot accept model self-report as authority | Submit validation, accepted-ledger-only gates, adversarial source text, forged submission, duplicate source, and degraded-source scenarios pass. | achieved deterministically |
| HITL decisions are explicit and resumable | HITL1/HITL2 contracts and lifecycle tests pass; both credentialed early-prefix canaries reached their expected boundary. | deterministic plus live prefix evidence |
| Final report and claim/citation bindings are materialized and checked | Deterministic final delivery materializes both files and the release runner validates bindings against accepted refs, but no full-real run has produced the complete evidence chain. | deterministic materialization achieved; full-real unproved |

The deterministic suite is strong evidence for interface parity, failure
containment, and recovery semantics. It does not prove provider behavior,
end-to-end report quality, or production-like full-pipeline completion.

## Quality Evidence

Achieved:

- Pure metrics cover citation precision/completeness, must-answer coverage,
  source diversity, contradiction recall, and unsupported major claims.
- Hard correctness/security failures are reported separately from quality
  scores and cannot be averaged into a passing result.
- Deterministic real-node and mixed-prefix scenarios cover all eleven real
  nodes, insufficient evidence, partial success, malformed output, and
  adversarial sources.
- The start-to-HITL1 and HITL1-to-topic-planning live canaries passed their hard
  invariants with the expected lifecycle boundaries.

Outstanding:

- Wave0 produced no accepted evidence in the live run, so no meaningful live
  citation, source-diversity, coverage, contradiction, or unsupported-claim
  baseline exists for an evidence-producing prefix.
- No full-real report exists from which to score report-level citation binding,
  must-answer coverage, contradiction handling, or unsupported major claims.
- Subjective quality thresholds remain deliberately non-blocking until repeated
  successful live observations establish a reviewed baseline.

## Resilience Evidence

Achieved:

- Deterministic fault injection covers timeout, cancel, duplicate resume,
  partial publication, stale checkpoint, conflicting worker results, restart,
  cleanup, and blocking-I/O behavior.
- The complete deterministic Batch 2 gate passed, including 1,200 tests, the
  viability gate, eight durability tests, and nine blocking-I/O tests. Four
  Gateway-unavailable skips and one deferred Postgres case were recorded rather
  than treated as passes.
- The failed Wave0 live run remained bounded and failed closed after three
  internal attempts without creating an accepted ledger record.

Outstanding:

- The Wave0 provider/tool-selection failure has not converged to a passing live
  observation.
- No isolated full-real lifecycle has demonstrated recovery, completion, and
  cleanup under credentialed execution.
- Deferred Postgres multi-process durability remains outside this change's
  baseline and is not claimed as covered.

## Cost Evidence

Achieved:

- Live attempts report model/tool identity, token usage, tool-call count,
  retries, and wall time. The three observations were 596/1044 tokens in
  18.42s, 622/819 tokens in 14.39s, and 2595/1448 tokens in 28.52s.
- Canary model/tool calls, token budget, wall time, and internal attempts are
  bounded; release retries are bounded and visible in the report contract.

Outstanding:

- Provider metadata supplied no monetary cost, so cost in USD is unknown.
- There is no successful Wave0 cost sample and no full-real token, fetch, tool,
  retry, wall-time, or monetary-cost observation.
- One observation per prefix is insufficient for variance, trend, or release
  threshold claims.

## Security Evidence

Achieved:

- The deterministic lane excludes credentialed tests and denies public network
  access while allowing loopback integration.
- Scripted real-workflow tests traverse untrusted-data wrapping, typed tool
  policy, path containment, submission validation, ledger authority, and gates.
- Prompt injection, route-like source text, forged submission text, traversal,
  duplicate/SEO sources, unavailable sources, symlink escape, and secret/host
  path redaction have deterministic regressions.
- Live and release preflight fail on missing configuration rather than silently
  skipping; report contracts expose provider identities without credentials.

Outstanding:

- Because full-real acceptance has not executed, no release archive has yet
  proved both secret-free diagnostics and absence of raw host paths.
- Final sandbox materialization and content hashes pass deterministically, but
  release-archive containment remains unproved until full-real execution.

## Release Closure

Batch 3 may pass only when all three live canaries pass their hard invariants
and one isolated full-real acceptance completes the normal lifecycle with
accepted evidence, both final files, valid citation bindings, contained paths,
clean cleanup, unique checkpoint identity, and redacted archived reports. Until
then, this report is an evidence ledger and gap statement, not an approval.
