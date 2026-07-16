## Why

The existing demos (`demo.py`, `demo_tui.py`) hide the 11-phase research pipeline behind raw JSON dumps at HITL suspension points — users see two pauses, not the bootstrap → topic_planning → wave0 → … → final_delivery flow. There is no real-mode CLI or TUI entry point that exercises the full graph with actual LLM and web search. The previous attempt (reverted `demo_fake.py`) used hardcoded static phase lists instead of ground truth from the graph's `execution_trace`, and bypassed `ResearchGraphRecipe.create()` validation for real mode.

## What Changes

### Demo infrastructure (`_demo_core.py`)
- **Shared `DemoAdapter`** with real `LocalSandbox` (not `object()`) — required for work-unit storage verification
- **`DemoAppConfig`** auto-detects available API keys (`DEEPSEEK_API_KEY`, `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`) and builds corresponding `ModelConfig` entries with correct field names (`base_url` for DeepSeek, not `api_base`)
- **Storage probe patch** — `BootstrapBundleStore.create`, `RequestBundleStore.create`, `WorkUnitStore.create` patched to skip POSIX probe in demo mode (the probe requires full sandbox infrastructure unavailable in temp-directory context)
- **Pipeline progress** driven by checkpoint `execution_trace` diffs, with Chinese labels

### CLI demos
- **`demo_real.py`**: real-mode CLI with `--question` and `--scripted` flags; `--scripted` passes `non_interactive_policy: {auto_profile, auto_proceed}`
- **`demo.py`**: enhanced with phase progress display, preserves zero-dependency guarantee

### TUI demo (`demo_tui.py`)
- Real-only with pipeline progress table (✓/⏸/● markers), welcome guide, multi-key credential check

### Production code changes (in `agent/src/`)
1. **`tool.py`**: Added `non_interactive_policy=non_interactive_policy` to `ResearchActionInput` constructor — was **missing**, causing HITL auto-skip to never trigger
2. **`node_agent_bridge.py`**: `_default_tools_resolver` falls back to global `get_app_config()` when `envelope.app_config` has no tools configured
3. **`research.py`**: Added `web_search`/`web_fetch` to `WAVE0_WORKER_TOOL_NAMES` and `WAVE1_WORKER_TOOL_NAMES` (actual Tavily tool names); increased wave0 budget for demo reliability
4. **`domain/lifecycle.py`**: `execution_trace` field + widened `implementation_mode` (from earlier commits)

### Config & env
- **`config.yaml`** at repo root (gitignored): models (deepseek-v4-pro, deepseek-v4-flash), sandbox (local), tools (tavily web_search + web_fetch)
- **`agent/.env`** (gitignored): `DEEPSEEK_API_KEY` + `TAVILY_API_KEY`
- **`agent/Makefile`**: `--env-file .env` on all real-mode targets

### Open issues
- wave0/wave1 worker nodes produce varying output quality with DeepSeek v4-pro; gate conditions sometimes reject valid output → retries exhaust → BLOCKED. The pipeline *runs* correctly but LLM output parsing is brittle.
- HITL1 followup rounds not handled in demo CLI/TUI (assumes single-round)

## Capabilities

### New
- `demo-pipeline`: shared demo core, checkpoint-driven progress, recipe factory, real-mode CLI

### Modified
- `research-demo-tui`: fake → real, pipeline tracker, multi-key credential check

## Impact
- **Production code**: 4 files in `agent/src/` (tool.py, node_agent_bridge.py, research.py, lifecycle.py)
- **Config**: new `config.yaml` at repo root, new `agent/.env`
- **No changes** to `backend/` or `frontend/`
