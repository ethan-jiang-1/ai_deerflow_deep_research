# DeerFlow Deep Research

This independent Python project contains the downstream Deep Research runtime
for DeerFlow 2.1. Its controller is a nested Python `StateGraph`; bounded agent
loops execute inside graph nodes. DeerFlow remains the host runtime and does not
import this package.

Changes 00 through 15 are complete — all 11 graph nodes (bootstrap through
final_delivery) have both real and fake implementations. The demo pipeline
supports three entry points:

- `make demo` — fake CLI, zero API, shows all phases
- `make demo-real` — real CLI, full LLM + web search pipeline
- `make demo-tui` — real TUI, visual phase progress

## Work-Unit Kernel

The kernel keeps three authorities separate. Checkpointed `ResearchState` owns
control and legal transitions; `evidence/submissions.jsonl` is the sole accepted-
evidence authority; sandbox files are content authority. Deterministic controller
code alone allocates work/attempt ids and writes canonical specs, workers receive
only an attempt-scoped artifact writer, and deterministic submit alone validates
files, publishes the hash-chained ledger, and returns accepted record hashes.

The version-2 checkpoint schema is extended compatibly with defaulted compact
work-unit fields. The active window is bounded to 32 works, 64 attempts, 32
selected failures, and 64 accepted refs; the exact work block is capped at
40,960 bytes inside the existing 65,536-byte whole-checkpoint limit. Candidate
bodies and evidence files never enter the checkpoint.

Ledger publication uses one research-scoped POSIX `flock`, mode-0600 staging,
same-directory atomic replace, file/directory fsync, and ledger-first replay.
The manually invoked child graph has no inherited checkpointer, so the complete
Wave node is the replay unit: restart deterministically recreates ids, verifies
the ledger, revalidates accepted files, and catches up missing checkpoint refs.

This first store requires a verified mounted workspace shared by the parent
sandbox and trusted host path. Local and local-container mounted modes may pass
the runtime probe; remote, provisioner-backed, custom, or otherwise unverified
modes fail closed. `status` and `cancel` remain checkpoint-only and deliberately
do not initialize a parent sandbox or construct the work-unit store.

Wave0/Wave1 fixtures may write only controller-owned `work-spec.json`, worker-
owned `result.json` and declared `outputs/`, and submit-owned ledger lock/staging/
JSONL files. Later Wave, targeted-evidence, and rerun implementations must reuse
this component, validator, store, ledger, retry, and drain path rather than add a
second delegated-completion authority.

## Real Bootstrap And HITL1

Real bootstrap establishes `workspace/deep-research/<research_id>/request/marker.json`
through a runtime-owned `BootstrapBundleStore`. Real HITL1 is available only in
the mixed implementation map with `bootstrap=real` and `hitl1=real`; it calls the
runtime node-agent bridge with a zero-tool, one-model-call policy to draft a
structured brief, then uses the existing graph interrupt/resume protocol for
human profile input.

The final validated profile is written as canonical JSON to
`request/profile.json` through `RequestBundleStore` and referenced from
`ResearchState.profile_ref`. Checkpoints store only short profile fields,
`must_answer_questions`, `degraded_profile`, and bounded follow-up progress
(`pending_profile`, `profile_followup_round`) without bumping schema version 2.
Incomplete HITL1 answers route explicitly through `hitl1 --needs_followup--> hitl1`;
brief-generation failure routes through `hitl1 --exhausted--> blocked`.

No `backend/`, `frontend/`, root config, extension, skill, Agent/SOUL, MCP, ACP,
or lead-agent middleware surface is modified by the real HITL1 change.

## Real Wave0 And Source-Intake Worker

Real Wave0 is the first real *worker* node. It reads the planner-owned
`topic_registry` and materializes one immutable source-intake `WorkSpec` per
topic through the shared work-unit controller. Each work unit runs a bounded
web worker agent through the runtime node-agent bridge under a real
`ExecutionPolicy` with web search/fetch tools and attempt-scoped read/write
roots. All fetched content is treated as untrusted data and placed in the
`<untrusted-source-data>` block; the deny-by-default `ToolPolicyMiddleware`
blocks any tool/path the worker is not allow-listed for.

A real `wave0.source-intake` v1 result contract (canonical source URLs, source
metadata, baseline facts, fetch/cache refs, limitations) is registered in a
generalized `(result_contract, result_schema_version)` validation registry.
Submit validation canonicalizes URLs, verifies fetch/cache refs, and deduplicates
sources per topic. A real source-floor gate replaces the fixture sequence rule
with per-topic independent-source coverage enforced at submit-validation time.
An honest degraded-capture contract records unreachable sources as typed
limitations rather than fabricating success.

Real Wave0 is available only in the mixed implementation map with
`bootstrap=real`, `hitl1=real`, `topic_planning=real`, and `wave0=real`.
Selecting `wave0=real` without the real topic chain fails before graph
invocation. The full-fake Wave0 fixture path remains deterministic and does NOT
construct the runtime node-agent bridge. Web-tool provisioning is an operator
configuration prerequisite; this change declares the worker tool-policy surface
without adding a specific provider.

No `backend/`, `frontend/`, root config, extension, skill, Agent/SOUL, MCP, ACP,
or lead-agent middleware surface is modified by the real Wave0 change.

## Requirements

- Python 3.12 or newer
- `uv`
- The sibling DeerFlow harness at `../backend/packages/harness`

## Setup

```bash
cd agent
make install
make lock-check
```

The project is independently locked. Repository development resolves
`deerflow-harness` from the sibling checkout through an editable uv source.
The `operations` extra contains the round-trip YAML dependency used by project
configuration scripts; runtime code does not acquire it implicitly.

## Development

```bash
make format
make lint
make test              # complete network-free deterministic union
make test-fast         # contract/domain/engine/unit/graph/eval tests
make test-integration  # deterministic integration/blocking-I/O correctness
make test-workflow     # deterministic real-loop workflow conformance
make test-viability
make test-durability
make test-blocking-io
make test-assets       # incident, scenario, selector, and regression inventories
make test-req-coverage # alive requirements -> collected deterministic tests
make test-live         # credentialed short live canaries; strict preflight
RELEASE_E2E_CONFIRM=1 make test-release-e2e # isolated full-real acceptance
make demo               # interactive zero-API fake lifecycle (show all 11 phases)
make demo-scripted      # deterministic non-interactive fake (CI)
make demo-real          # interactive real pipeline (requires ANTHROPIC_API_KEY)
make demo-real-scripted # deterministic non-interactive real (CI, requires creds)
make demo-tui           # standalone Textual real-mode visualization
```

## Testing And Evaluation

Deep Research maintains four distinct asset classes. Code-correctness tests
cover deterministic domain, engine, runtime, checkpoint, sandbox, store, and
filesystem contracts. Agent-workflow conformance tests run real nodes, graph
prefixes, middleware, policies, budgets, parsers, submit, gates, and artifacts
with scripted model/tool adapters. Behavioral evaluation runs bounded real
model/tool canaries and separates hard invariants from non-blocking quality and
cost metrics. Full-system acceptance enters through the real public tool and
runs the isolated all-real pipeline through final delivery.

Every test and report carries an authenticity claim from this ladder:

1. `FAKE_GRAPH` proves topology and graph-owned control flow.
2. `REAL_NODE_FAKE_CAPABILITIES` proves a real node's typed state and route behavior.
3. `SCRIPTED_REAL_WORKFLOW` proves the real bridge, middleware, policy, loop, stores, and gates.
4. `LIVE_REAL_DEPENDENCIES` proves observed model/tool-provider behavior under explicit bounds.
5. `FULL_REAL_PIPELINE` proves one isolated end-to-end acceptance run.

A lower level cannot satisfy a higher claim. The preferred stable test seams,
from narrowest to broadest, are domain/engine interfaces; `NodeSpec` plus
`NodeExecutionCapabilities`; runtime adapter/bridge/store protocols; lifecycle
handlers plus mixed graphs; and the real public entry.

Exact selectors and `TestEvidenceClaim` records live in the central test-owned registry and
are checked against all five focused pytest selections; prose documentation is
not the enumerable catalog. Reusable manifests live in `tests/scenarios/`. Each scenario declares a stable
id, risk family, requirement and optional regression ids, entrypoint,
authenticity, preconditions, scripted/live inputs, expected route and terminal
outcome, artifacts/citations, hard invariants, metrics, and permitted
degradation. Internal nodes, middleware, gates, validators, and stores stay real
when a scenario claims workflow conformance; only true external model/tool,
time, randomness, and supported fault boundaries may be replaced. Deterministic
scenarios require no credential or public network.

Selection is intentionally non-overlapping. `make test` is the exact
network-free union of `make test-fast`, `make test-integration`, and
`make test-workflow`; it excludes `requires_llm`, `release_e2e`, and `postgres`.
`make test-live` selects six bounded canaries: three short public-entry prefixes
and three directly seeded late-node cases. The late-node cases prove only their
focused node/provider/store/gate semantics and explicitly do not prove the
public entry, predecessor lifecycle, production recipe, or full pipeline.
Reports use `report_schema_version=1` / `metrics_schema=evidence-v1` with typed
metric status and structural evidence basis. `make test-release-e2e` requires
explicit confirmation plus model and Tavily credentials, uses fresh
thread/run/research/checkpoint identity, and writes `.reports/release`. An
explicitly selected live or release lane fails preflight when its environment is
incomplete; it never silently skips.

Use the terms precisely: a scripted case drives a real production loop with
short deterministic external responses; a provider-shape fixture is a minimized
redacted payload passed through the production normalization/validation seam; a
persisted trace replay is reserved for a reviewed temporal/interleaving need and
is not a synonym for either. Raw provider responses are not retained as test
fixtures.

CI follows the same authority split: `agent-tests.yml` runs deterministic gates
on pull requests and pushes. The six-case `agent-live-evaluation.yml` is
manual-only while the current measured lane has open failures; schedule is
restored only after all six pass and preserve the aggregate margin.
`agent-release-e2e.yml` remains the single full-pipeline
lane and runs only on
manual/reusable release invocation after deterministic gates. Hard lifecycle,
authority, containment, artifact, citation, and cleanup invariants are blocking.
Subjective quality thresholds remain reported until a reviewed later change
promotes a stable baseline.

The accepted 2026-07-17 full-real proof survives cleanup of gitignored raw
reports as the minimal redacted committed attestation in
`docs/release-attestation-2026-07-17.json`. It proves one isolated accepted run,
not current provider distribution or a general quality threshold.

Every live or release defect follows the regression-descent policy in
`docs/regression-descent.md`: record a redacted discovery, classify its risk and
lowest stable seam, add the smallest red-before-green deterministic regression
when it is replayable, and retain an explicit provider-only live rationale when
it is not. A successful demo or single full-real run never replaces the lower
test assets or proves distributional quality by itself.

`make demo` and `make demo-scripted` are zero-dependency: no Gateway, config,
model credentials, or network needed. They show every pipeline phase from bootstrap
to final_delivery with human-readable Chinese labels driven by the graph's own
`execution_trace`.

`make demo-real` and `make demo-real-scripted` require `ANTHROPIC_API_KEY` (and
optionally web search tool credentials). They exercise the full real pipeline
through all 11 nodes.

`make demo-tui` is a real-mode Textual visualization. It requires
`ANTHROPIC_API_KEY` and the `demo-tui` extra. This is an agent-owned visual demo,
not the production DeerFlow Terminal Workbench, Web UI, Gateway, or generic
human-input integration.

`make test-viability` is a hard prerequisite for structure/runtime work after
change 00 group 2. It verifies reflected async `ToolRuntime` injection and
ordinary asyncio cancellation through a nested LangGraph without private
Gateway cancellation state.

The reflected `deep_research` tool supports `infra_probe | start | resume |
status | cancel`. `start` and `resume` are intended for the Web UI or compatible
generic clients and require human interaction; known IM transports and
non-interactive contexts refuse them. `status` and `cancel` remain available.
File SQLite is restart durable; memory and SQLite memory mode are same-process
only.

Source lives only under `src/deerflow_deep_research/`, and tests live under
`tests/`. See `AGENTS.md` for ownership boundaries, the stable node-package
shape, development order, and the exact current structure contract.

The canonical machine-readable structure registry is
`../openspec/governance/project-structure.toml`. Verify it from the repository
root with:

```bash
python3 openspec/governance/check_project_architecture.py
```

The runtime substrate and full-fake graph are verified with zero-API tests: the trusted
`RuntimeAdapter`, `GraphHost` with isolated checkpoint namespaces, the node-agent
bridge with budgets/policy, the reflected `infra_probe` tool, configuration
materialization (`configure.py`), the source-loading preparation core
(`prepare.py`) and Docker override, readiness diagnostics (`doctor.py`), and
file-backed SQLite lifecycle recovery across a real subprocess restart
(`make test-durability`), and event-loop blocking checks
(`make test-blocking-io`). The topology snapshot is generated with
`uv run python scripts/render_topology.py`.

The project-owned live launch wrapper (`serve.sh`, `make dev/prod` targets), the
in-container prelaunch doctor gate, and the Postgres durability profile are
**deferred to a follow-up deployment change** — production is not provisioned
yet. See `../_backlog/todos/deferred_deep-research-00-launcher-and-docker.md` and
`../_backlog/todos/deferred_deep-research-00-postgres-profile.md`.
