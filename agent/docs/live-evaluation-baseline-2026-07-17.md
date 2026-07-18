# Live Evaluation Baseline: 2026-07-17

> Classification: legacy report schema. These observations predate
> `report_schema_version=1` and `metrics_schema=evidence-v1`; their historical
> quality values are not comparable to evidence-v1 typed metrics.

This is the first non-blocking live baseline for the Deep Research short-prefix
canaries. It is observational evidence, not a release pass and not a quality
threshold. All runs used unique thread, run, and research identities with the
DeepSeek `deepseek-v4-pro` model. Cost was unavailable from provider metadata.

| Scenario | Hard invariants | Input / output tokens | Tool calls | Wall time | Result |
| --- | --- | ---: | ---: | ---: | --- |
| `live-start-to-hitl1` | pass | 596 / 1044 | 0 | 18.42s | suspended at HITL1 as expected |
| `live-hitl1-to-topic-planning` | pass | 622 / 819 | 0 | 14.39s | real topic-planning prefix observed |
| `live-one-topic-wave0` | fail | 2595 / 1448 | 0 | 28.52s | blocked after 3 internal attempts; no accepted record |

The early-prefix scenarios intentionally have no accepted evidence, so citation
and coverage scores are not useful thresholds for them. The Wave0 failure is a
hard-invariant failure and is not averaged into a quality score.

## Regression Descent

The live run exposed four deterministic defects. Each was reduced before the
provider lane was retried:

- Real LocalSandbox cleanup removed the same mounted directory from sandbox and
  host views; host cleanup now treats an already-removed directory as idempotent
  while retaining residual-file checks.
- The canary model configuration declared `max_retries` twice; the deterministic
  model-construction test now enforces one retry authority.
- The canary HITL setup used an invalid `time_budget` enum; all setup payloads are
  now parsed by the real node parsers in deterministic tests.
- The Wave0 prompt requested runtime-owned `content_ref`, `content_hash`, and
  `byte_count` fields that `WorkerSource` forbids. The prompt now matches the
  typed model-owned fields and runtime remains the only authority that derives
  artifact refs, hashes, and byte counts.

## Provider-Only Observations

After deterministic fixes, the final Wave0 observation made no Tavily call and
returned no validated worker result across three bounded internal attempts. The
same bridge, policy, tool-call, parser, validator, artifact, and ledger path
passes with scripted adapters. Whether a live model elects to call a tool, its
structured-output adherence distribution, provider latency/token usage, and
Tavily ranking/content changes remain live concerns and must not be represented
as deterministic coverage.

The next credentialed live run should retain the same scenario and bounds. A
release gate remains blocked until all three canaries pass their hard invariants.

## Evidence-V1 Non-Blocking Baseline

The evidence-v1 observation window starts with this change. It is non-blocking:
no metric threshold is active. Existing local reports are classified `legacy`
because they lack both schema fields and contain superseded proxy metrics.

A credentialed evidence-v1 observation was recorded on 2026-07-18 after the six
case expansion. Four cases passed: start-to-HITL1, HITL1-to-topic-planning,
one-topic Wave0, and one-topic Wave1. Wave2 synthesis failed closed because the
provider repeated a gap-level `search_required` field forbidden by the canonical
gap contract; targeted evidence failed closed after tool-only turns followed by
prose instead of its required JSON result. Both failures retained schema-valid,
redacted reports and published no false authority. They require a separately
reviewed production prompt/repair change; the test-asset change does not coerce
the outputs.

The evidence-v1 window remains non-blocking and has no promoted metric threshold.
Each selected metric serializes `not_applicable`, `insufficient_authority`, or
`measured` with a null or numeric value and structural evidence basis. Missing
late-node authority remains `insufficient_authority`; it is not replaced by a
vacuous score. The historical full-real acceptance proof is separately preserved
in `release-attestation-2026-07-17.json` and does not turn this partial current
provider observation into a six-case pass.
