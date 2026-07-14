# DeerFlow Deep Research

This independent Python project contains the downstream Deep Research runtime
for DeerFlow 2.1. Its controller is a nested Python `StateGraph`; bounded agent
loops execute inside graph nodes. DeerFlow remains the host runtime and does not
import this package.

Changes 00 through 03 are complete and archived. The active change 04 adds the
shared work-unit kernel beneath Wave0 and Wave1 while keeping every lifecycle
result labelled `implementation_mode=full_fake`: no node calls a model, network,
or sandbox research tool, and fixture submissions are not findings or a report.

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
make test
make test-viability
make test-durability
make test-blocking-io
make demo             # interactive zero-API lifecycle walkthrough
make demo-scripted    # deterministic non-interactive walkthrough
make demo-tui         # standalone Textual visualization of the same lifecycle
```

`make demo-tui` is an agent-owned visual demo, not the production DeerFlow
Terminal Workbench, Web UI, Gateway, or generic human-input integration. It
requires no root `config.yaml`, model credentials, network, or service process;
it drives the same process-local full-fake lifecycle used by `make demo` and
never produces research findings or a report.

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
