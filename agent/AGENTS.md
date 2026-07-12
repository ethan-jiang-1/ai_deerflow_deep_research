# Deep Research Module Guide

This guide owns development instructions for `agent/`. The root `AGENTS.md`
still governs repository-wide behavior. Deep Research is a downstream consumer
of DeerFlow: files under `backend/` and `frontend/` are upstream mirrors and
must not import or be modified for this roadmap.

## Structural Authority

The active `project-structure` OpenSpec owns semantic requirements. Exact
enumerable structure lives in `openspec/governance/project-structure.toml`, and
`openspec/governance/architecture-policy.md` defines the synchronized-change
protocol. The block below is generated from the TOML registry. Do not edit it
by hand; update the owning OpenSpec delta and registry, render the block with
`python3 openspec/governance/check_project_architecture.py --render-guide`, and
run the checker.

<!-- BEGIN GENERATED: PROJECT-STRUCTURE -->
## Canonical Structure Contract

Registry: `openspec/governance/project-structure.toml`

- Source root: `agent/src/deerflow_deep_research/`
- Test root: `agent/tests/`
- Ownership layers: `runtime`, `domain`, `engine`, `agents`, `graph`
- Forbidden source roots: `backend/`, `frontend/`
- Required current paths:
  - `agent/AGENTS.md` (file; `PRS-004`)
  - `agent/README.md` (file; `PRS-001`)
  - `agent/Makefile` (file; `PRS-001`)
  - `agent/pyproject.toml` (file; `PRS-001`)
  - `agent/uv.lock` (file; `PRS-001`)
  - `agent/src/deerflow_deep_research/` (directory; `PRS-001`)
  - `agent/src/deerflow_deep_research/__init__.py` (file; `PRS-001`)
  - `agent/src/deerflow_deep_research/__about__.py` (file; `PRS-001`)
  - `agent/src/deerflow_deep_research/runtime/` (directory; `PRS-001`)
  - `agent/src/deerflow_deep_research/runtime/__init__.py` (file; `PRS-001`)
  - `agent/src/deerflow_deep_research/runtime/checkpoint.py` (file; `PRS-001`)
  - `agent/src/deerflow_deep_research/runtime/startup_snapshot.py` (file; `PRS-001`)
  - `agent/src/deerflow_deep_research/domain/` (directory; `PRS-001`)
  - `agent/src/deerflow_deep_research/domain/__init__.py` (file; `PRS-001`)
  - `agent/src/deerflow_deep_research/domain/context.py` (file; `PRS-003`)
  - `agent/src/deerflow_deep_research/domain/enums.py` (file; `PRS-003`)
  - `agent/src/deerflow_deep_research/domain/node_spec.py` (file; `PRS-003`)
  - `agent/src/deerflow_deep_research/engine/` (directory; `PRS-001`)
  - `agent/src/deerflow_deep_research/engine/__init__.py` (file; `PRS-001`)
  - `agent/src/deerflow_deep_research/agents/` (directory; `PRS-001`)
  - `agent/src/deerflow_deep_research/agents/__init__.py` (file; `PRS-001`)
  - `agent/src/deerflow_deep_research/graph/` (directory; `PRS-001`)
  - `agent/src/deerflow_deep_research/graph/__init__.py` (file; `PRS-001`)
  - `agent/src/deerflow_deep_research/graph/registry.py` (file; `PRS-003`)
  - `agent/src/deerflow_deep_research/resources/` (directory; `PRS-001`)
  - `agent/config/` (directory; `PRS-001`)
  - `agent/config/deerflow.fragment.yaml` (file; `PRS-001`)
  - `agent/config/extensions.fragment.json` (file; `PRS-001`)
  - `agent/config/agent-template/` (directory; `PRS-001`)
  - `agent/config/agent-template/config.yaml` (file; `PRS-001`)
  - `agent/config/agent-template/SOUL.md` (file; `PRS-001`)
  - `agent/config/public-skill/` (directory; `PRS-001`)
  - `agent/config/public-skill/deep-research-controller/` (directory; `PRS-001`)
  - `agent/config/public-skill/deep-research-controller/SKILL.md` (file; `PRS-001`)
  - `agent/scripts/` (directory; `PRS-001`)
  - `agent/scripts/configure.py` (file; `PRS-001`)
  - `agent/scripts/prepare.py` (file; `PRS-001`)
  - `agent/docker/` (directory; `PRS-001`)
  - `agent/tests/unit/` (directory; `PRS-001`)
  - `agent/tests/contract/` (directory; `PRS-001`)
  - `agent/tests/graph/` (directory; `PRS-001`)
  - `agent/tests/integration/` (directory; `PRS-001`)
  - `agent/tests/e2e/` (directory; `PRS-001`)
  - `agent/tests/fixtures/` (directory; `PRS-001`)
  - `openspec/governance/architecture-policy.md` (file; `PRS-004`)
  - `openspec/governance/project-structure.toml` (file; `PRS-004`)
  - `openspec/governance/check_project_architecture.py` (file; `PRS-004`)
- Top-level node root: `agent/src/deerflow_deep_research/graph/nodes/`
- Required node files: `__init__.py`, `node.py`, `fake.py`, `contracts.py`
- Public node export: `NODE_SPEC`
<!-- END GENERATED: PROJECT-STRUCTURE -->

## Current Status

The current checkout contains the completed, archived change 00 runtime
substrate: the independent package, ownership roots, runtime integration,
infrastructure probe, and bounded node-agent base. Empty business topology is
intentionally absent until change 01. Treat any tree below labelled "later" as
a placement rule, not as implemented behavior.

## Ownership

- `domain/`: frozen pure contracts. It may use only the standard library and
  Pydantic and must not import outer layers.
- `engine/`: deterministic business/control primitives that depend only on
  `domain/`. Change 03 and later add gates, work units, evidence, and artifact
  policy when those contracts become real.
- `agents/`: bounded embedded-agent construction, middleware, policies, prompts,
  and structured results. It may depend on `domain/` and public DeerFlow,
  LangChain, and LangGraph APIs, never `runtime/` or graph nodes.
- `graph/`: nested graph recipes, explicit registry, infrastructure probe, and
  later topology. It depends on pure contracts and explicitly listed nodes.
- `runtime/`: the only layer that binds raw DeerFlow context, parent sandbox,
  checkpointer providers, and embedded-agent execution to pure contracts.
- `resources/`: package-owned prompt and policy files. External source content
  is data and never replaces these instructions.

Dependency direction is:

```text
tool -> runtime -> graph -> nodes
                         nodes -> engine -> domain
runtime -> graph + agents + domain + deerflow.*
agents  -> domain + deerflow.* + langchain.*
graph   -> domain + explicitly listed nodes
domain  -> stdlib + pydantic only
```

Production code under `agent/` must not import `app.*`. Real Gateway integration
tests may launch the application as a fixture. Generic shared modules named
`utils`, `helpers`, or `common` are forbidden; place shared contracts in the
owning domain module and shared internal subflows under `graph/components/`.

## Node Packages

Top-level workflow nodes are added under `graph/nodes/<logical_name>/` only by
the change that owns that node. Every package has this stable surface:

```text
<logical_name>/
  __init__.py    # exports NODE_SPEC only
  node.py        # real factory
  fake.py        # deterministic zero-API factory
  contracts.py   # private node-local contracts
  subgraph.py    # optional phase-local subgraph
```

The package root exports exactly one `NODE_SPEC`. Nodes do not import the graph
registry, graph implementation modules, sibling nodes, `agents/`, or `runtime/`.
The registry loads explicitly listed package roots and never discovers topology
from the filesystem.

## Planned Placement

Change 00 may add the following infrastructure files as their tasks turn green:

```text
runtime/{graph_host,runtime_adapter,projection,identity,checkpoint}.py
runtime/{events,cancellation,node_agent_bridge,diagnostics,startup_snapshot}.py
domain/{context,enums,node_spec}.py
agents/{factory,middleware,policies,prompts,structured_output}.py
graph/{builder,registry,infra_probe}.py
resources/node_agent/runtime_policy.md
```

Change 01 and later may add `graph/topology.py`, `implementation_map.py`,
`routing.py`, `graph/components/`, and `graph/nodes/`. Change 03 and later may
add `engine/gates/`, `work_units/`, `evidence/`, and `artifacts/`. Do not create
these packages early merely to match a plan diagram.

## Development Order

Execute the numbered Deep Research changes strictly in order `00 -> 01 -> ... ->
18`. Within change 00, follow `tasks.md` group and task order. Group 2 is a hard
viability gate: do not continue to group 3 unless reflected async `ToolRuntime`
injection and ordinary asyncio cancellation propagation pass on the pinned
stack. Run `make test-viability`; it executes
`test_reflected_runtime_viability.py` and `test_cancellation_viability.py`.

Use red-before-green deterministic tests. Model-facing tests use
`FakeToolCallingModel` or `ReplayChatModel`; real API tests require the
`requires_llm` marker. Add `@impl XXX-001` at the owning implementation surface.

## Commands

Run from `agent/`:

```bash
make install       # sync the locked project with the operations extra
make lock-check    # verify uv.lock matches pyproject.toml
make format        # Ruff fixes and formatting
make lint          # Ruff lint and format check
make test          # complete agent-owned test suite
make test-unit     # unit tests only
make test-contract # contract tests only
make test-viability # hard reflected-runtime and nested-cancellation gate
```

Run permanent governance from the repository root:

```bash
python3 openspec/governance/check_project_architecture.py
python3 openspec/governance/check_project_reqs.py
python3 openspec/governance/check_project_specs.py
```
