# demo-pipeline Specification

> req: DPL-001, DPL-002, DPL-003, DPL-004, DPL-005

## Purpose

Provide a shared demo core module, control-result-driven pipeline phase progress display, a recipe factory supporting both fake and real implementation modes, an independent real-mode CLI entry point, and corresponding Makefile targets — all without modifying graph topology, nodes, handlers, `backend/`, or `frontend/`.

## ADDED Requirements

### Requirement: Shared demo core module provides infrastructure for all demo scripts

The agent project SHALL provide `agent/scripts/_demo_core.py` containing: `DemoAdapter` (custom `RuntimeAdapter` with temporary workspace/upload/output directories and `WorkUnitStore` factory), synthetic tool-call construction helpers (`_tool_call`, `_runtime` accepting an optional `context` parameter, `_suspension`), `PHASE_META` mapping all 11 logical node names to Chinese labels and descriptions, `ALL_REAL_MODES` constant, `build_demo_recipe()` factory (fake/real), `build_demo_host()` factory, `create_hitl_response()` helper, `check_credentials_available()` guard, and `display_phase_progress(phases, *, suspended_at)` for human-readable phase output. The module SHALL be importable by all demo scripts in the same directory without `sys.path` manipulation beyond what `make` targets already provide. (`DPL-001`)

#### Scenario: CLI fake demo imports from shared core
- **WHEN** `make demo` runs `demo.py` which imports `DemoAdapter`, `_tool_call`, `_runtime`, `_suspension`, `PHASE_META`, `build_demo_recipe`, `build_demo_host`, and `create_hitl_response` from `_demo_core`
- **THEN** all imports resolve and the lifecycle completes with phase progress displayed

#### Scenario: CLI real demo imports from shared core
- **WHEN** `make demo-real` runs `demo_real.py` which imports `DemoAdapter`, `PHASE_META`, `build_demo_recipe(mode="real")`, `build_demo_host`, `create_hitl_response`, and `check_credentials_available` from `_demo_core`
- **THEN** all imports resolve, credentials pass, and the lifecycle starts

#### Scenario: Phase meta covers all 11 logical nodes
- **WHEN** `PHASE_META` is inspected
- **THEN** it contains entries for every key in `deerflow_deep_research.graph.topology.LOGICAL_NODES`

### Requirement: Phase progress display is driven by checkpoint execution_trace

Demo scripts SHALL display pipeline phase progress by reading the `execution_trace` field from the `DeepResearchControlResult` returned after each lifecycle action, computing the difference from the trace observed in the previous action, and rendering completed phases with their `PHASE_META` labels. The display SHALL use `→` for completed phases and `⏸` for the phase at which the graph is currently suspended (determined from the result's `phase` field). No phase list SHALL be hardcoded in the demo scripts beyond `PHASE_META`. (`DPL-002`)

#### Scenario: Fake demo shows phases that actually executed between HITL points
- **WHEN** `make demo --scripted` runs the fake pipeline
- **THEN** the output shows the bootstrap phase before HITL1, the phases that executed between HITL1 and HITL2 in the order they appear in `execution_trace`, and the post-HITL2 phases through terminal delivery, with each phase rendered using its `PHASE_META` label

#### Scenario: Suspended phase is marked distinctly
- **WHEN** the graph is suspended at `hitl1` or `hitl2`
- **THEN** that phase is displayed with `⏸` prefix, not `→`

#### Scenario: Phase order reflects actual execution path
- **WHEN** the graph takes the `targeted_evidence → wave2_synthesis` loop path
- **THEN** the displayed phases match the actual `execution_trace` order, including any repeated phases

### Requirement: Recipe factory supports fake and real implementation modes

`build_demo_recipe(*, mode, work_unit_store_factory)` SHALL return a `ResearchGraphRecipe` created via `ResearchGraphRecipe.create()`. When `mode="fake"`, it SHALL pass no `implementation_modes` (defaulting all nodes to fake). When `mode="real"`, it SHALL pass `ALL_REAL_MODES` and `node_agent_bridge_factory=RuntimeNodeAgentBridge`. The factory SHALL NOT bypass `create()` validation or construct the recipe dataclass manually. (`DPL-003`)

#### Scenario: Fake recipe has no node-agent bridge requirement
- **WHEN** `build_demo_recipe(mode="fake", ...)` is called
- **THEN** the returned recipe has `requires_node_agent_bridge=False`

#### Scenario: Real recipe requires node-agent bridge
- **WHEN** `build_demo_recipe(mode="real", ...)` is called with valid `work_unit_store_factory`
- **THEN** the returned recipe has `requires_node_agent_bridge=True` and `requires_bootstrap_bundle=True`

#### Scenario: Real recipe validates dependency chain
- **WHEN** `build_demo_recipe(mode="real", ...)` is called
- **THEN** `ResearchGraphRecipe.create()` validates the all-real dependency chain and raises `ValueError` only if a real factory is unavailable (not expected with all 11 nodes implemented)

### Requirement: CLI real demo is an independent script with credential validation

The agent project SHALL provide `agent/scripts/demo_real.py` as an independent CLI entry point for real-mode research. It SHALL import from `_demo_core`, validate that `ANTHROPIC_API_KEY` is set before building the recipe, display phase progress from the `execution_trace` field in each `DeepResearchControlResult`, and support `--question` and `--scripted` arguments. In `--scripted` mode it SHALL pass `non_interactive_policy={"auto_profile": True, "auto_proceed": True}` via the `_runtime` helper's `context` parameter. (`DPL-004`)

#### Scenario: Real demo rejects missing credentials
- **WHEN** `demo_real.py` is launched without `ANTHROPIC_API_KEY` in the environment
- **THEN** it prints a clear error message listing required environment variables and exits with non-zero status before building the graph

#### Scenario: Real demo starts with valid credentials
- **WHEN** `demo_real.py` is launched with `ANTHROPIC_API_KEY` set
- **THEN** it builds the all-real recipe, constructs the graph host, and begins the lifecycle with `action="start"`

#### Scenario: Scripted real demo passes non-interactive policy
- **WHEN** `demo_real.py --scripted` is launched
- **THEN** the runtime context includes `non_interactive_policy` with `auto_profile=True` and `auto_proceed=True`, allowing the lifecycle to pass HITL1 and HITL2 without stdin prompts

### Requirement: Makefile provides targets for all demo variants

The `agent/Makefile` SHALL provide: `demo` (unchanged, fake CLI), `demo-scripted` (unchanged, fake CLI non-interactive), `demo-real` (new, real CLI), `demo-real-scripted` (new, real CLI non-interactive), and `demo-tui` (changed to real-only TUI). The `DEMO_ARGS` variable SHALL be passed to all targets. No files under `backend/` or `frontend/` SHALL be modified. (`DPL-005`)

#### Scenario: make demo runs fake pipeline
- **WHEN** `make demo` is invoked
- **THEN** it executes `uv run --extra operations python scripts/demo.py $(DEMO_ARGS)` and the fake lifecycle completes

#### Scenario: make demo-real runs real pipeline
- **WHEN** `make demo-real` is invoked with `ANTHROPIC_API_KEY` set
- **THEN** it executes `uv run --extra operations python scripts/demo_real.py $(DEMO_ARGS)` and real nodes are selected

#### Scenario: make demo-tui runs real TUI
- **WHEN** `make demo-tui` is invoked
- **THEN** it executes `uv run --extra operations --extra demo-tui python scripts/demo_tui.py` and the TUI validates credentials before starting
