# DeerFlow Deep Research

This independent Python project contains the downstream Deep Research runtime
for DeerFlow 2.1. Its controller is a nested Python `StateGraph`; bounded agent
loops execute inside graph nodes. DeerFlow remains the host runtime and does not
import this package.

Change 00's runtime substrate is complete and archived. Change 01 adds the full
deterministic topology, real checkpoint interrupts, lifecycle actions, repair
and rerun routes, and a fake terminal marker. Every lifecycle result is labelled
`implementation_mode=full_fake`: no node calls a model, network, or sandbox
research tool, and the terminal marker is not findings or a report.

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
```

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
