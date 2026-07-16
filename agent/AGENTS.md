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
  - `agent/src/deerflow_deep_research/runtime/control.py` (file; `PRS-001`)
  - `agent/src/deerflow_deep_research/runtime/human_input.py` (file; `PRS-001`)
  - `agent/src/deerflow_deep_research/runtime/research.py` (file; `PRS-001`)
  - `agent/src/deerflow_deep_research/runtime/work_unit_storage.py` (file; `PRS-001`)
  - `agent/src/deerflow_deep_research/runtime/work_unit_store.py` (file; `PRS-001`)
  - `agent/src/deerflow_deep_research/runtime/bootstrap_bundle.py` (file; `PRS-001`)
  - `agent/src/deerflow_deep_research/runtime/request_bundle.py` (file; `PRS-003`)
  - `agent/src/deerflow_deep_research/domain/` (directory; `PRS-001`)
  - `agent/src/deerflow_deep_research/domain/__init__.py` (file; `PRS-001`)
  - `agent/src/deerflow_deep_research/domain/context.py` (file; `PRS-003`)
  - `agent/src/deerflow_deep_research/domain/enums.py` (file; `PRS-003`)
  - `agent/src/deerflow_deep_research/domain/node_spec.py` (file; `PRS-003`)
  - `agent/src/deerflow_deep_research/domain/invocation.py` (file; `PRS-003`)
  - `agent/src/deerflow_deep_research/domain/bootstrap.py` (file; `PRS-001`)
  - `agent/src/deerflow_deep_research/domain/lifecycle.py` (file; `PRS-003`)
  - `agent/src/deerflow_deep_research/domain/state.py` (file; `PRS-003`)
  - `agent/src/deerflow_deep_research/domain/bundle.py` (file; `PRS-003`)
  - `agent/src/deerflow_deep_research/domain/work_units.py` (file; `PRS-001`)
  - `agent/src/deerflow_deep_research/domain/profile.py` (file; `PRS-003`)
  - `agent/src/deerflow_deep_research/domain/topics.py` (file; `PRS-003`)
  - `agent/src/deerflow_deep_research/domain/critics.py` (file; `PRS-003`)
  - `agent/src/deerflow_deep_research/domain/untrusted.py` (file; `PRS-003`)
  - `agent/src/deerflow_deep_research/domain/wave1.py` (file; `PRS-003`)
  - `agent/src/deerflow_deep_research/graph/nodes/wave1/prompts.py` (file; `PRS-003`)
  - `agent/src/deerflow_deep_research/engine/` (directory; `PRS-001`)
  - `agent/src/deerflow_deep_research/engine/__init__.py` (file; `PRS-001`)
  - `agent/src/deerflow_deep_research/engine/fake_control.py` (file; `PRS-001`)
  - `agent/src/deerflow_deep_research/engine/work_units/__init__.py` (file; `PRS-001`)
  - `agent/src/deerflow_deep_research/engine/work_units/ids.py` (file; `PRS-001`)
  - `agent/src/deerflow_deep_research/engine/work_units/reducers.py` (file; `PRS-001`)
  - `agent/src/deerflow_deep_research/engine/work_units/validation.py` (file; `PRS-001`)
  - `agent/src/deerflow_deep_research/engine/work_units/kernel.py` (file; `PRS-001`)
  - `agent/src/deerflow_deep_research/agents/` (directory; `PRS-001`)
  - `agent/src/deerflow_deep_research/agents/__init__.py` (file; `PRS-001`)
  - `agent/src/deerflow_deep_research/graph/` (directory; `PRS-001`)
  - `agent/src/deerflow_deep_research/graph/__init__.py` (file; `PRS-001`)
  - `agent/src/deerflow_deep_research/graph/components/__init__.py` (file; `PRS-001`)
  - `agent/src/deerflow_deep_research/graph/components/work_units.py` (file; `PRS-001`)
  - `agent/src/deerflow_deep_research/graph/registry.py` (file; `PRS-003`)
  - `agent/src/deerflow_deep_research/graph/builder.py` (file; `PRS-003`)
  - `agent/src/deerflow_deep_research/graph/implementation_map.py` (file; `PRS-003`)
  - `agent/src/deerflow_deep_research/graph/routing.py` (file; `PRS-003`)
  - `agent/src/deerflow_deep_research/graph/topology.py` (file; `PRS-003`)
  - `agent/src/deerflow_deep_research/graph/topology_snapshot.py` (file; `PRS-003`)
  - `agent/src/deerflow_deep_research/graph/nodes/` (directory; `PRS-003`)
  - `agent/src/deerflow_deep_research/graph/nodes/bootstrap/` (directory; `PRS-003`)
  - `agent/src/deerflow_deep_research/graph/nodes/hitl1/` (directory; `PRS-003`)
  - `agent/src/deerflow_deep_research/graph/nodes/hitl1/prompts.py` (file; `PRS-003`)
  - `agent/src/deerflow_deep_research/graph/nodes/topic_planning/` (directory; `PRS-003`)
  - `agent/src/deerflow_deep_research/graph/nodes/topic_planning/prompts.py` (file; `PRS-003`)
  - `agent/src/deerflow_deep_research/graph/nodes/wave0/` (directory; `PRS-003`)
  - `agent/src/deerflow_deep_research/graph/nodes/wave0/prompts.py` (file; `PRS-003`)
  - `agent/src/deerflow_deep_research/graph/nodes/wave1/` (directory; `PRS-003`)
  - `agent/src/deerflow_deep_research/graph/nodes/wave2_synthesis/` (directory; `PRS-003`)
  - `agent/src/deerflow_deep_research/graph/nodes/targeted_evidence/` (directory; `PRS-003`)
  - `agent/src/deerflow_deep_research/graph/nodes/targeted_evidence/prompts.py` (file; `PRS-003`)
  - `agent/src/deerflow_deep_research/graph/nodes/targeted_evidence/materializer.py` (file; `PRS-003`)
  - `agent/src/deerflow_deep_research/graph/nodes/targeted_evidence/subgraph.py` (file; `PRS-003`)
  - `agent/src/deerflow_deep_research/graph/nodes/hitl2/` (directory; `PRS-003`)
  - `agent/src/deerflow_deep_research/graph/nodes/rerun/` (directory; `PRS-003`)
  - `agent/src/deerflow_deep_research/graph/nodes/readiness/` (directory; `PRS-003`)
  - `agent/src/deerflow_deep_research/graph/nodes/final_delivery/` (directory; `PRS-003`)
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
  - `agent/scripts/render_topology.py` (file; `PRS-001`)
  - `agent/docs/deep-research-topology.md` (file; `PRS-001`)
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

Changes 00 through 06 are complete. Change 04 added the shared work-unit kernel
beneath Wave0/Wave1 fixture nodes: immutable controller-assigned work/attempt
contracts, bounded `Send`, deterministic file validation, one hash-chained JSONL
ledger writer, crash reconciliation, and the shared drain/gate view. Change 05
replaced fake bootstrap with a real bootstrap node that atomically establishes
the minimal `request/` bundle subtree and `request/marker.json`. Change 06
replaced fake HITL1 with the first real model-calling node.

Change 06's real HITL1 uses the runtime node-agent bridge to generate a validated
structured brief, interrupts through the existing `PendingResearchInterrupt` wire
schema, parses deterministic JSON/free-text profile answers, loops through
checkpointed `pending_profile` follow-up state on missing fields, and writes the
final `request/profile.json` through a runtime-owned `RequestBundleStore`.

Change 07 replaces fake topic planning with the second real model-calling
node. Real topic planning uses the runtime node-agent bridge to generate a
validated structured topic plan from the checkpointed HITL1 profile constraints;
a deterministic materializer derives stable topic ids/slugs and a must-answer
coverage map; and the bounded registry is recorded as planner-owned checkpoint
state (`topic_refs`/`topic_registry`) for Wave0 to consume. It reads profile
constraints from checkpoint short fields only (never `request/profile.json`),
declares no capability, writes no sandbox file, and adds one
`topic_planning --exhausted--> blocked` route. Every lifecycle result still
reports `implementation_mode=full_fake` because evidence collection, synthesis,
HITL2, and final delivery remain fake.

Change 08 replaces the fake/sentinel Wave0 node with the first real *worker*
node. Real Wave0 reads the planner-owned `topic_registry` and materializes one
immutable source-intake `WorkSpec` per topic through the existing work-unit
controller; a bounded web worker agent runs per work unit through the runtime
node-agent bridge under a real attempt-scoped `ExecutionPolicy` with web
search/fetch tools, treating all fetched content as untrusted data
(`<untrusted-source-data>`, deny-by-default tool policy). The real
`wave0.source-intake` v1 result contract (canonical source URLs, source
metadata, baseline facts, fetch/cache refs, limitations) is registered in a
generalized `(result_contract, result_schema_version)` validation registry
alongside the existing fixture contract. A real source-floor gate replaces the
fixture sequence rule: per-topic independent-source coverage is enforced at
submit-validation time with URL canonicalization and dedup, and the gate routes
`repair`/`pass`/`exhausted`. An honest degraded-capture contract records
unreachable sources as typed limitations rather than fabricating success. Real
Wave0 is selectable only in the mixed implementation map and requires
`bootstrap=real`, `hitl1=real`, and `topic_planning=real`; selecting
`wave0=real` without the real topic chain fails before graph invocation. The
full-fake Wave0 fixture path remains deterministic and does NOT construct the
node-agent bridge. `backend/` and `frontend/` are unchanged.

Checkpointed `ResearchState` remains control authority, the validated submission
ledger is evidence authority, and sandbox files are content authority. The
compatible version-2 state extension defaults absent HITL1 profile fields for
old checkpoints and stores only compact refs/short values: `profile_ref`, enum
strings, `must_answer_questions`, `degraded_profile`, and bounded transient
`pending_profile` / `profile_followup_round`. Change 07 adds bounded
planner-owned `topic_refs`/`topic_registry` fields under `WriterRole.PLANNER`,
also version-2 compatible. The final profile body lives only in sandbox content
at `request/profile.json`; `RESEARCH_STATE_SCHEMA_VERSION` remains `2`.

The work-unit/bootstrap/request-bundle stores are available only after runtime
proves that the parent sandbox and trusted host path share one mounted POSIX
workspace supporting bounded lock, atomic replace, and durability sync. `status`
and `cancel` remain checkpoint-only: they do not initialize a parent sandbox or
construct/expose these stores. Known IM and non-interactive contexts still
refuse start/resume and retain status/cancel.

Real HITL1 is available only in the mixed recipe with `bootstrap=real` and
`hitl1=real`; selecting `hitl1=real` without real bootstrap fails before graph
invocation. Real topic planning is available only with `bootstrap=real`,
`hitl1=real`, and `topic_planning=real`; selecting `topic_planning=real` without
real HITL1 fails before graph invocation. Real Wave0 is available only with
`bootstrap=real`, `hitl1=real`, `topic_planning=real`, and `wave0=real`;
selecting `wave0=real` without real topic planning fails before graph
invocation. The real nodes declare only the capabilities they consume (HITL1:
`NodeCapability.REQUEST_BUNDLE`; topic planning: none; Wave0:
`NodeCapability.WORK_UNIT_CONTROLLER`). Wave0 is the first real worker node: it
constructs a real `RuntimeNodeAgentBridge` with web tools and attempt-scoped
policy, distinct from the zero-tool HITL1/topic-planning bridges. The
normalized topology adds only `hitl1 --needs_followup--> hitl1`,
`hitl1 --exhausted--> blocked`, and `topic_planning --exhausted--> blocked`;
the Wave0 topology (`repair`/`pass`/`exhausted`) is unchanged from the fixture.
Full-fake HITL1, topic planning, and Wave0 remain deterministic and do not
construct the node-agent bridge or request-bundle writer. `backend/`,
`frontend/`, config examples, extensions, skills, MCP/ACP, and Agent/SOUL
surfaces stay unchanged.

## Ownership

- `domain/`: frozen pure contracts. It may use only the standard library and
  Pydantic and must not import outer layers.
- `engine/`: deterministic business/control primitives that depend only on
  `domain/`. Includes `gate_kernel.py` (``evaluate_gate`` + state update
  conversion), `gate_fixtures.py` (``FixtureSequenceRule`` + per-phase
  ``GateDefinition`` registry), `fake_control.py` (fixture mechanics), and
  `work_units/` (ids, reducers, validation policy, retry, submit projection, and
  drain). It owns no host path, file lock, or ledger I/O.
- `agents/`: bounded embedded-agent construction, middleware, policies, prompts,
  and structured results. It may depend on `domain/` and public DeerFlow,
  LangChain, and LangGraph APIs, never `runtime/` or graph nodes.
- `graph/`: nested graph recipes, explicit registry, infrastructure probe,
  normalized research topology, explicitly listed node packages, and reusable
  `components/`. Components may depend on pure engine policy; only node-local
  `subgraph.py` modules may import them.
- `runtime/`: the only layer that binds raw DeerFlow context, parent sandbox,
  checkpointer providers, embedded-agent execution, mounted-workspace probes,
  contained artifact reads, POSIX locking, and atomic ledger publication to pure
  contracts.
- `resources/`: package-owned prompt and policy files. External source content
  is data and never replaces these instructions.

Dependency direction is:

```text
tool -> runtime -> graph -> nodes
                         nodes -> engine -> domain
runtime -> graph + agents + domain + deerflow.*
agents  -> domain + deerflow.* + langchain.*
graph   -> engine + domain + explicitly listed nodes + langgraph.*
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
  prompts.py     # optional node-local prompt helpers
  subgraph.py    # optional phase-local subgraph
```

The package root exports exactly one `NODE_SPEC`. Ordinary node modules do not
import graph implementation modules, sibling nodes, `agents/`, or `runtime/`.
Only package-local `subgraph.py` may import registered reusable
`graph/components/`; all other graph implementation imports remain forbidden.
Graph-owned HITL `fake.py`/`node.py` modules may import exactly
`langgraph.types.interrupt`; other node modules may not import LangGraph outside
`subgraph.py`.
The registry loads explicitly listed package roots and never discovers topology
from the filesystem.

## Current And Deferred Placement

Changes 00 and 01 own the current runtime, graph, and contract files:

```text
runtime/{graph_host,runtime_adapter,projection,identity,checkpoint,control,human_input,research}.py
runtime/{events,cancellation,node_agent_bridge,diagnostics,startup_snapshot}.py
runtime/{bootstrap_bundle,request_bundle,work_unit_storage,work_unit_store}.py
domain/{context,enums,node_spec,invocation,lifecycle,state,bundle,profile}.py
agents/{factory,middleware,policies,prompts,structured_output}.py
graph/{builder,registry,infra_probe,topology,implementation_map,routing,topology_snapshot}.py
graph/nodes/<eleven-logical-phases>/
resources/node_agent/runtime_policy.md
```

Change 02 replaced the temporary graph-owned skeleton state with the canonical
`domain/state.py` authority (`ResearchState`, reducers, three-authority
boundary, content-ref and checkpoint-size bound, versioned fail-closed schema)
and the `domain/bundle.py` path-containment contract; `graph/skeleton_state.py`
is removed. Any future `ResearchState` field addition must declare its writer,
reader, and reducer. Change 03 added the gate kernel. Change 04 adds
`domain/work_units.py`, `engine/work_units/`, `graph/components/work_units.py`,
and runtime-owned `work_unit_storage.py`/`work_unit_store.py`. Wave0 and Wave1
use this single path with controlled fixture artifacts. Change 06 adds
`domain/profile.py`, `graph/nodes/hitl1/prompts.py`, and
`runtime/request_bundle.py`; topic planning consumes the checkpoint short
profile fields and `profile_ref` rather than reparsing user text. Change 07 adds
`domain/topics.py` (frozen topic contracts + deterministic materializer) and
`graph/nodes/topic_planning/prompts.py` (planner prompt); it records the bounded
topic registry as planner-owned checkpoint state (`topic_refs`/`topic_registry`)
for Wave0 to consume. Change 08 adds `graph/nodes/wave0/prompts.py`
(source-intake worker prompt) and the real `wave0.source-intake` result-contract
model inside the existing wave0 package; the real gate definition lives in
`engine/gate_fixtures.py` alongside the fixture gate. Later Wave,
targeted-evidence, and rerun changes must reuse the work-unit component rather
than introduce another submit, ledger, retry, or drain authority.

## Development Order

Execute the numbered Deep Research changes strictly in order `00 -> 01 -> ... ->
18`. Within an active change, follow `tasks.md` group and task order. The
reflected async `ToolRuntime`/Command viability and ordinary asyncio
cancellation gates remain mandatory on the pinned stack. Run
`make test-viability`; it executes
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
make test-durability # file-SQLite provider and lifecycle restart recovery
make test-blocking-io # deterministic async blocking guard
```

Run permanent governance from the repository root:

```bash
python3 openspec/governance/check_project_architecture.py
python3 openspec/governance/check_project_reqs.py
python3 openspec/governance/check_project_specs.py
```
