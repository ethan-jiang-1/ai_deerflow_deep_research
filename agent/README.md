# DeerFlow Deep Research

This independent Python project contains the downstream Deep Research runtime
for DeerFlow 2.1. Its controller is a nested Python `StateGraph`; bounded agent
loops execute inside graph nodes. DeerFlow remains the host runtime and does not
import this package.

Change 00 is currently establishing the package, runtime integration, and
deterministic infrastructure probe. The public research lifecycle and business
nodes are intentionally not available until their later numbered changes.

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
```

`make test-viability` is a hard prerequisite for structure/runtime work after
change 00 group 2. It verifies reflected async `ToolRuntime` injection and
ordinary asyncio cancellation through a nested LangGraph without private
Gateway cancellation state.

Source lives only under `src/deerflow_deep_research/`, and tests live under
`tests/`. See `AGENTS.md` for ownership boundaries, the stable node-package
shape, development order, and the exact current structure contract.

The canonical machine-readable structure registry is
`../openspec/governance/project-structure.toml`. Verify it from the repository
root with:

```bash
python3 openspec/governance/check_project_architecture.py
```

Local Gateway loading, Docker assembly, configuration materialization, and the
`infra_probe` command are added by later tasks in change 00. Until those tasks
are complete, use this project only for its package and governance test surface.
