## Why

Change 01 has a working zero-API lifecycle, but its current terminal walkthrough is plain text and gives little visual sense of the two HITL pauses. A small, explicitly non-product Textual demo can make the control flow immediately visible without taking on the much larger DeerFlow Terminal Workbench or Web UI integration problem.

## What Changes

- Add an agent-owned `make -C agent demo-tui` entry that launches a thin Textual shell over the existing full-fake lifecycle handlers.
- Show the initial request, lifecycle status, HITL1 text response, HITL2 decision choices, and terminal result while retaining explicit `implementation_mode=full_fake` and no-research-output warnings.
- Add a separately locked optional demo dependency and deterministic Textual pilot tests; keep the existing plain `make -C agent demo` as the lowest-cost smoke path.
- Reuse the real `start | resume | cancel` control path and retained memory host; do not introduce a second graph, fixture authority, checkpoint schema, or fake product client.
- Do not modify or claim compatibility with DeerFlow's production TUI, embedded `DeerFlowClient`, Web UI, Gateway, IM channels, or generic human-input protocol.

## Capabilities

### New Capabilities

- `research-demo-tui`: An agent-owned, zero-API Textual visualization of the archived Change 01 full-fake lifecycle (`RED-001`, `RED-002`).

### Modified Capabilities

None.

## Impact

- Affected paths: `agent/Makefile`, `agent/pyproject.toml`, `agent/uv.lock`, agent-owned demo scripts/tests, and agent documentation.
- The demo uses `deerflow_deep_research.tool.run_deep_research` with a test-owned trusted envelope and process-local memory host. It writes no sandbox research artifacts and changes no checkpoint schema or graph node.
- No Deep Research node-agent role, phase skill, DeerFlow `task` subagent, MCP, ACP, model, network API, Gateway service, runtime configuration, mount, public skill, or per-user Agent/SOUL change is used.
- No next-agent-build or Gateway restart is required; the optional Textual dependency is installed only in the agent project environment.
- No files under `backend/` or `frontend/` are modified. Formal DeerFlow TUI/Web UI human-input compatibility remains separate future work.
