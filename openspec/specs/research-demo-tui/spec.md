# research-demo-tui Specification

> req: RED-001, RED-002

## Purpose
Provide a bounded, standalone terminal visualization of the deterministic Deep Research lifecycle without implying production DeerFlow TUI, Web UI, Gateway, or generic human-input integration.

## Requirements
### Requirement: Standalone TUI demo traverses the real full-fake lifecycle

The agent project SHALL provide a Textual demo entry that invokes the existing reflected-tool lifecycle dispatch with a retained process-local memory host and test-owned trusted runtime envelope. It SHALL traverse a visible request, HITL1 text response, HITL2 advertised decision, and terminal or cancelled result without invoking a Gateway, model, network API, DeerFlow task subagent, MCP/ACP service, or sandbox research tool. The demo SHALL NOT introduce a second graph, checkpoint schema, fixture authority, or research artifact. (`RED-001`)

#### Scenario: User completes the visual happy path
- **WHEN** a user launches the demo, submits a research request and HITL1 response, then selects the advertised `proceed` decision
- **THEN** the UI shows both real request ids and the lifecycle reaches the existing completed full-fake terminal result

#### Scenario: User cancels a suspended lifecycle
- **WHEN** the demo has a pending HITL request and the user invokes the explicit cancel action
- **THEN** the same lifecycle handler reaches the durable cancelled terminal without interpreting UI interruption as a user answer

### Requirement: Demo remains bounded and explicitly non-product

The demo SHALL launch through `make -C agent demo-tui` using an agent-only optional Textual dependency, retain the existing plain CLI demo, and visibly state `implementation_mode=full_fake`, zero API, and no research-output semantics. Deterministic pilot tests SHALL exercise the visual flow. Documentation SHALL state that the shell is not DeerFlow Terminal Workbench, Web UI, Gateway, or generic human-input integration, and no files under `backend/` or `frontend/` SHALL change. (`RED-002`)

#### Scenario: Demo starts without product configuration
- **WHEN** the demo target runs in the locked agent environment without root `config.yaml`, model credentials, Gateway, or network access
- **THEN** the Textual application starts and the lifecycle can complete using only deterministic local dependencies

#### Scenario: Unsupported decision is refused locally
- **WHEN** a user enters a HITL2 value that is not in the request's advertised options
- **THEN** the UI retains the pending request, displays a bounded validation error, and does not invoke resume or mutate the checkpoint
