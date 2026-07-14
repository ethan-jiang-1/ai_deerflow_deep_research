# project-structure Specification

> req: PRS-001, PRS-002, PRS-003, PRS-004
> structure: openspec/governance/project-structure.toml

## Purpose
The canonical downstream package structure, mechanically enforced import directions and node surface, and archive-durable architecture governance.
## Requirements
### Requirement: Canonical downstream package ownership
The project SHALL place all Deep Research Python source under `agent/src/deerflow_deep_research/`, all owned tests under `agent/tests/`, and all owned runtime templates and launch tooling under `agent/`. The documented ownership layers SHALL be `runtime`, `domain`, `engine`, `agents`, and `graph`; no Deep Research source SHALL be added under `backend/` or `frontend/`.

#### Scenario: Canonical scaffold passes
- **WHEN** the folder contract inspects a fresh change 00 checkout
- **THEN** it finds the required owned roots, package metadata, module guide, and mirrored test roots at their canonical paths

#### Scenario: Second source tree is rejected
- **WHEN** a fixture places Deep Research implementation source at repository root or under an upstream tree
- **THEN** the folder contract fails and identifies the non-canonical owner

### Requirement: Import and shared-code boundaries are mechanical

The project SHALL enforce import direction with an AST-based contract. Domain code
SHALL depend only on the standard library and Pydantic; engine code SHALL depend only
on domain; agents SHALL depend only on domain plus public DeerFlow/LangChain APIs;
ordinary node modules SHALL depend only on domain/engine, except that a graph-owned
HITL fake MAY import exactly public `langgraph.types.interrupt`. A node package's
optional phase-local `subgraph.py` MAY additionally import public LangGraph APIs
required for its internal `Send` fan-out/fan-in and reusable cross-node subflows under
`graph/components/`. Reusable graph components MAY depend on domain, engine, and public
LangGraph APIs. Neither node exception MAY import other graph implementation modules,
agents, runtime, or sibling nodes. Runtime SHALL be the only layer allowed to bind
graph execution to raw DeerFlow context and the embedded-agent factory; production
downstream code SHALL not import `app.*`; and generic shared modules named `utils`,
`helpers`, or `common` SHALL be rejected.

#### Scenario: Valid dependency direction passes
- **WHEN** the contract scans the canonical downstream package including a node-owned phase-local subgraph using public LangGraph and a HITL fake importing only public `interrupt`
- **THEN** every import resolves within the allowed layer direction and the subgraph does not gain access to other graph implementation modules, runtime, agents, or sibling nodes

#### Scenario: Reverse dependency fails closed
- **WHEN** a fixture makes domain code import runtime code, an ordinary node module import LangGraph or `graph/components/`, a node-local `subgraph.py` import graph implementation outside `graph/components/`, a node import agents/runtime, or one node import another node
- **THEN** the contract fails with the importing and imported module names

### Requirement: Top-level nodes expose one stable surface

Every top-level workflow node package introduced after change 00 SHALL expose exactly
one valid `NODE_SPEC` from its package root, using the pure contract from
`domain/node_spec.py`, colocate its deterministic fake and private contracts, and MAY
colocate one optional phase-local `subgraph.py` for internal implementation components.
Reusable cross-node non-top-level subflows SHALL remain under `graph/components/` and
MAY be imported only by node-local `subgraph.py` modules, not by ordinary node factories
or fakes.
Real/fake node factories SHALL accept only pure NodeBuildDependencies containing
reduced context/capability contracts. Nodes SHALL NOT import `graph/registry.py`; the
registry/builder SHALL load only an explicitly listed node package root and read its
public `NODE_SPEC`, never import a private node module path directly.

#### Scenario: Valid node package is discoverable
- **WHEN** a fixture supplies the required node files, a valid `NODE_SPEC`, and an optional phase-local subgraph using only its permitted public LangGraph and `graph/components/` imports
- **THEN** registry discovery returns the stable logical node name, real/fake factories, contracts, phase, and policy reference without exposing internal subgraph components as top-level nodes

#### Scenario: Partial node package is refused
- **WHEN** a node package omits its fake, exports internal callables directly, uses an unstable logical name, imports a reusable graph component from an ordinary node module, or exposes a phase-local worker as a top-level node
- **THEN** registry validation fails before graph compilation

#### Scenario: Node-to-registry cycle is refused
- **WHEN** a node package imports `graph.registry`, another graph implementation module outside the narrow `subgraph.py -> graph.components` exception, or a sibling node to construct its spec or subgraph
- **THEN** the import contract fails and directs the node to the pure domain NodeSpec, package-local subgraph contract, or registered reusable graph component

### Requirement: Structural authority survives change archival
The active `project-structure` main spec SHALL own the semantic structure requirements and SHALL normatively identify `openspec/governance/project-structure.toml` as the single machine-readable registry for their exact repository-relative roots, current required paths, ownership layers, forbidden locations, import boundaries, and top-level node-package grammar. Before the capability's first archive, the one active owning delta SHALL serve as the pending normative reference; after the main spec exists, archived deltas SHALL be historical only and SHALL NOT remain authority. `openspec/governance/architecture-policy.md` SHALL define the authority and synchronized-change protocol without maintaining a competing path enumeration. `agent/AGENTS.md` SHALL contain one bounded checker-rendered structural block derived from the registry plus human-authored operational guidance. Archived proposals, designs, and tasks SHALL be historical context only. A deterministic zero-external-dependency governance checker SHALL reject a missing or invalid registry, a missing lifecycle-appropriate normative spec reference, controlled-block drift, or a mismatch between the registry and the repository.

#### Scenario: Active truth is discoverable after archive
- **WHEN** change 00 has been archived and a later contributor starts from the active `project-structure` main spec
- **THEN** the spec identifies the permanent policy, exact structure registry, generated `agent/AGENTS.md` block, and deterministic checker without requiring the archived design

#### Scenario: Synchronized structure passes governance
- **WHEN** the one pending owning delta before first archive or the active main spec afterward references the valid registry, the controlled `agent/AGENTS.md` block matches its deterministic rendering, and the required repository paths and boundaries conform
- **THEN** the architecture-governance checker passes without semantic inference

#### Scenario: Structural drift fails governance
- **WHEN** the registry and repository disagree, the controlled guide block is not the registry's exact rendering, or the lifecycle-appropriate owning spec loses or ambiguously declares its normative registry reference
- **THEN** the checker fails with the mechanically mismatched authority surface and no archive may complete

