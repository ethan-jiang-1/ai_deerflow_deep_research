# Live Evaluation Baseline: 2026-07-17

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
