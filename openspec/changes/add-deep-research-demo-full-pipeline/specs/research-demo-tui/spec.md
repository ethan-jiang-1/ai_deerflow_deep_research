# research-demo-tui Specification (Delta)

> req: RED-001, RED-002

## MODIFIED Requirements

### Requirement: Standalone TUI demo traverses the real-mode lifecycle

The agent project SHALL provide a Textual demo entry that invokes the existing reflected-tool lifecycle dispatch with a retained process-local memory host and test-owned trusted runtime envelope, using the all-real implementation mode (`ALL_REAL_MODES`) through `ResearchGraphRecipe.create()` with `RuntimeNodeAgentBridge`. It SHALL traverse a visible request, HITL1 text response, HITL2 advertised decision, and terminal or cancelled result. The demo SHALL validate that at least one known API key (`DEEPSEEK_API_KEY`, `ANTHROPIC_API_KEY`, or `OPENAI_API_KEY`) is set at startup and exit with a clear error if unavailable. The demo SHALL display pipeline phase progress in the UI driven by the `execution_trace` field from each `DeepResearchControlResult`, rendered as a Rich table with ✓/⏸/● markers for completed/suspended/active phases. The UI SHALL include a welcome panel explaining the 11-phase pipeline and usage instructions. It SHALL NOT introduce a second graph, checkpoint schema, fixture authority, or research artifact. (`RED-001`)

#### Scenario: User completes the visual happy path with real mode
- **WHEN** a user launches the demo with valid model credentials, submits a research request and HITL1 response, then selects the advertised `proceed` decision
- **THEN** the UI shows both real request ids, phase progress for each completed phase, and the lifecycle reaches a terminal result

#### Scenario: User cancels a suspended lifecycle
- **WHEN** the demo has a pending HITL request and the user invokes the explicit cancel action
- **THEN** the same lifecycle handler reaches the durable cancelled terminal without interpreting UI interruption as a user answer

#### Scenario: Demo refuses to start without credentials
- **WHEN** the demo target runs without any of `DEEPSEEK_API_KEY`, `ANTHROPIC_API_KEY`, or `OPENAI_API_KEY` set
- **THEN** the Textual application exits with a clear error message listing the three supported environment variables before building the graph

#### Scenario: Demo shows welcome guide and pipeline tracker on startup
- **WHEN** the TUI launches with valid credentials
- **THEN** the UI displays a welcome panel explaining the 11-phase pipeline and how-to instructions, plus a pipeline progress table showing all phases as pending

### Requirement: Demo remains bounded and explicitly non-product

The demo SHALL launch through `make -C agent demo-tui` using an agent-only optional Textual dependency. It SHALL visibly state that it uses real implementation mode and requires model credentials. Deterministic pilot tests SHALL exercise the visual flow using a mock node-agent bridge. Documentation SHALL state that the shell is not DeerFlow Terminal Workbench, Web UI, Gateway, or generic human-input integration, and no files under `backend/` or `frontend/` SHALL change. (`RED-002`)

#### Scenario: Unsupported decision is refused locally
- **WHEN** a user enters a HITL2 value that is not in the request's advertised options
- **THEN** the UI retains the pending request, displays a bounded validation error, and does not invoke resume or mutate the checkpoint

#### Scenario: Phase progress updates during lifecycle
- **WHEN** the TUI completes a `run_deep_research()` call
- **THEN** the phase progress panel updates to show newly completed phases from the `DeepResearchControlResult`'s `execution_trace`
