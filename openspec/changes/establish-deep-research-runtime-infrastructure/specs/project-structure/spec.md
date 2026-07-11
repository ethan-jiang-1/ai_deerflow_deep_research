> req: PRS-001, PRS-002, PRS-003

## ADDED Requirements

### Requirement: Canonical downstream package ownership
The project SHALL place all Deep Research Python source under `agent/src/deerflow_deep_research/`, all owned tests under `agent/tests/`, and all owned runtime templates and launch tooling under `agent/`. The documented ownership layers SHALL be `runtime`, `domain`, `engine`, `agents`, and `graph`; no Deep Research source SHALL be added under `backend/` or `frontend/`.

#### Scenario: Canonical scaffold passes
- **WHEN** the folder contract inspects a fresh change 00 checkout
- **THEN** it finds the required owned roots, package metadata, module guide, and mirrored test roots at their canonical paths

#### Scenario: Second source tree is rejected
- **WHEN** a fixture places Deep Research implementation source at repository root or under an upstream tree
- **THEN** the folder contract fails and identifies the non-canonical owner

### Requirement: Import and shared-code boundaries are mechanical
The project SHALL enforce import direction with an AST-based contract. Domain code SHALL depend only on the standard library and Pydantic; engine code SHALL depend only on domain; agents SHALL depend only on domain plus public DeerFlow/LangChain APIs; nodes SHALL depend only on domain/engine and SHALL not import agents, runtime, graph implementation modules, or sibling nodes; runtime SHALL be the only layer allowed to bind graph execution to raw DeerFlow context and the embedded-agent factory; production downstream code SHALL not import `app.*`; and generic shared modules named `utils`, `helpers`, or `common` SHALL be rejected.

#### Scenario: Valid dependency direction passes
- **WHEN** the contract scans the canonical downstream package
- **THEN** every import resolves within the allowed layer direction

#### Scenario: Reverse dependency fails closed
- **WHEN** a fixture makes domain code import runtime code, a node import the agents/runtime layer, or one node import another node
- **THEN** the contract fails with the importing and imported module names

### Requirement: Top-level nodes expose one stable surface
Every top-level workflow node package introduced after change 00 SHALL expose exactly one valid `NODE_SPEC` from its package root, using the pure contract from `domain/node_spec.py`, colocate its deterministic fake and private contracts, and keep reusable non-top-level subflows under `graph/components/`. Real/fake node factories SHALL accept only pure NodeBuildDependencies containing reduced context/capability contracts. Nodes SHALL NOT import `graph/registry.py`; the registry/builder SHALL load only an explicitly listed node package root and read its public `NODE_SPEC`, never import a private node module path directly.

#### Scenario: Valid node package is discoverable
- **WHEN** a fixture supplies the required node files and a valid `NODE_SPEC`
- **THEN** registry discovery returns the stable logical node name, real/fake factories, contracts, phase, and policy reference

#### Scenario: Partial node package is refused
- **WHEN** a node package omits its fake, exports internal callables directly, or uses an unstable logical name
- **THEN** registry validation fails before graph compilation

#### Scenario: Node-to-registry cycle is refused
- **WHEN** a node package imports `graph.registry` or another graph implementation module to construct its spec
- **THEN** the import contract fails and directs the node to the pure domain NodeSpec contract
