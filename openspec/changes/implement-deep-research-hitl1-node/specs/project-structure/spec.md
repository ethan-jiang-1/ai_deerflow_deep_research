> req: PRS-001, PRS-002, PRS-003, PRS-004
> structure: openspec/governance/project-structure.toml

## MODIFIED Requirements

### Requirement: Canonical downstream package ownership

The project SHALL place all Deep Research Python source under
`agent/src/deerflow_deep_research/`, all owned tests under `agent/tests/`, and all
owned runtime templates and launch tooling under `agent/`. The documented ownership
layers SHALL be `runtime`, `domain`, `engine`, `agents`, and `graph`; no Deep Research
source SHALL be added under `backend/` or `frontend/`.

Real HITL1 SHALL add only canonical downstream production paths owned by this change:
`agent/src/deerflow_deep_research/domain/profile.py`,
`agent/src/deerflow_deep_research/graph/nodes/hitl1/prompts.py`, and
`agent/src/deerflow_deep_research/runtime/request_bundle.py`. These paths SHALL be registered in
`openspec/governance/project-structure.toml` and reflected in the generated
`agent/AGENTS.md` block.

#### Scenario: Canonical HITL1 paths pass
- **WHEN** the folder contract inspects this change after implementation
- **THEN** the new profile, HITL1 prompt, and `runtime/request_bundle.py` paths appear under the canonical downstream package and no Deep Research source appears under `backend/` or `frontend/`

### Requirement: Import and shared-code boundaries are mechanical

The project SHALL enforce import direction with an AST-based contract. Domain code
SHALL depend only on the standard library and Pydantic; engine code SHALL depend only
on domain; agents SHALL depend only on domain plus public DeerFlow/LangChain APIs;
ordinary node modules SHALL depend only on domain/engine, except that graph-owned HITL
node modules (`fake.py` or `node.py` under HITL packages) MAY import exactly public
`langgraph.types.interrupt`. A node package's optional phase-local `subgraph.py` MAY
additionally import public LangGraph APIs required for its internal `Send`
fan-out/fan-in and reusable cross-node subflows under `graph/components/`. Reusable
graph components MAY depend on domain, engine, and public LangGraph APIs. None of these
exceptions MAY import other graph implementation modules, agents, runtime, or sibling
nodes. Runtime SHALL be the only layer allowed to bind graph execution to raw DeerFlow
context, request-bundle host I/O, and the embedded-agent factory; production downstream
code SHALL not import `app.*`; and generic shared modules named `utils`, `helpers`, or
`common` SHALL be rejected.

#### Scenario: Real HITL interrupt import passes narrowly
- **WHEN** the contract scans `agent/src/deerflow_deep_research/graph/nodes/hitl1/node.py` and it imports exactly `langgraph.types.interrupt`
- **THEN** the import is accepted as a graph-owned HITL interrupt boundary, while other LangGraph imports from ordinary node modules remain rejected

#### Scenario: Reverse dependency fails closed
- **WHEN** a fixture makes domain code import runtime code, an ordinary non-HITL node module import LangGraph or `graph/components/`, a HITL node import LangGraph APIs other than `langgraph.types.interrupt`, a node-local `subgraph.py` import graph implementation outside `graph/components/`, a node import agents/runtime, or one node import another node
- **THEN** the contract fails with the importing and imported module names

### Requirement: Top-level nodes expose one stable surface

Every top-level workflow node package introduced after change 00 SHALL expose exactly
one valid `NODE_SPEC` from its package root, using the pure contract from
`domain/node_spec.py`, colocate its deterministic fake and private contracts, and MAY
colocate one optional phase-local `subgraph.py` for internal implementation components.
Reusable cross-node non-top-level subflows SHALL remain under `graph/components/` and
MAY be imported only by node-local `subgraph.py` modules, not by ordinary node factories
or fakes. Real/fake node factories SHALL accept only pure `NodeBuildDependencies`
containing reduced context/capability contracts. Nodes SHALL NOT import
`graph/registry.py`; the registry/builder SHALL load only an explicitly listed node
package root and read its public `NODE_SPEC`, never import a private node module path
directly.

Real HITL1 SHALL declare only the narrow capabilities it consumes: the existing
`NodeExecutionCapabilities.run_agent()` protocol for brief generation and the
request-bundle profile writer for `request/profile.json`. It SHALL NOT declare or
receive `NodeCapability.BOOTSTRAP_BUNDLE` or `NodeCapability.WORK_UNIT_CONTROLLER`.
Fake HITL1 SHALL declare no request-bundle capability.

#### Scenario: Real HITL1 NodeSpec declares only its capabilities
- **WHEN** the HITL1 package root `NODE_SPEC` is loaded after this change
- **THEN** the real factory is available, its contract routes include `accepted`, `cancel`, `needs_followup`, and `exhausted`, it declares the request-bundle capability, and it does not declare bootstrap or work-unit controller capabilities

#### Scenario: Capability injection mismatch fails closed
- **WHEN** the graph wrapper attempts to attach a request-bundle writer to a node that did not declare it, or real HITL1 runs without the declared request-bundle writer
- **THEN** graph invocation fails before the node can fabricate a `ContentRef` or write profile state

### Requirement: Structural authority survives change archival

The active `project-structure` main spec SHALL own the semantic structure requirements
and SHALL normatively identify `openspec/governance/project-structure.toml` as the
single machine-readable registry for their exact repository-relative roots, current
required paths, ownership layers, forbidden locations, import boundaries, and top-level
node-package grammar. Before the capability's first archive, the one active owning
delta SHALL serve as the pending normative reference; after the main spec exists,
archived deltas SHALL be historical only and SHALL NOT remain authority.
`openspec/governance/architecture-policy.md` SHALL define the authority and
synchronized-change protocol without maintaining a competing path enumeration.
`agent/AGENTS.md` SHALL contain one bounded checker-rendered structural block derived
from the registry plus human-authored operational guidance.

#### Scenario: Synchronized HITL1 structure passes governance
- **WHEN** this change updates `project-structure.toml`, the architecture checker rule/fixtures, and the generated `agent/AGENTS.md` block for real HITL1 paths and import exceptions
- **THEN** the architecture-governance checker passes without semantic inference

#### Scenario: Structural drift fails governance
- **WHEN** the registry and repository disagree, the controlled guide block is not the registry's exact rendering, or the lifecycle-appropriate owning spec loses or ambiguously declares its normative registry reference
- **THEN** the checker fails with the mechanically mismatched authority surface and no archive may complete
