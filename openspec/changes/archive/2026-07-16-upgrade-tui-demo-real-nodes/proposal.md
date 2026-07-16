## Why

The `agent/scripts/demo_tui.py` runs the full-fake graph in a Textual terminal UI. With the CLI demo now supporting `--real` mode, the TUI demo needs the same capability.

## What Changes

- Add `--real` flag to `demo_tui.py`. Same pattern as CLI demo: build complete 11-entry implementation_modes dict, use `build_research_graph()` + minimal `ResearchGraphRecipe` with `work_unit_store_factory`.
- TUI already imports `DemoAdapter`, `build_control_graph_host`, `ResearchGraphRecipe` from the demo module.

## Impact

- **Source**: modify `agent/scripts/demo_tui.py` (~15 lines).
- **Graph**: no changes.
- **Non-goals**: no backend/frontend changes.
