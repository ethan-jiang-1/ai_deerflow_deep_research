## Why

The existing demos (`demo.py`, `demo_tui.py`) hide the 11-phase research pipeline behind raw JSON dumps at HITL suspension points — users see two pauses, not the bootstrap → topic_planning → wave0 → … → final_delivery flow. There is no real-mode CLI or TUI entry point that exercises the full graph with actual LLM and web search. The previous attempt (reverted `demo_fake.py`) used hardcoded static phase lists instead of ground truth from the graph's `execution_trace`, and bypassed `ResearchGraphRecipe.create()` validation for real mode.

## What Changes

- **New `agent/scripts/_demo_core.py`**: shared `DemoAdapter`, helpers (`_tool_call`, `_runtime`, `_suspension`), `PHASE_META` (Chinese labels + descriptions for all 11 phases), `build_demo_recipe()` factory (fake/real), `build_demo_host()`, `create_hitl_response()`
- **Enhance `agent/scripts/demo.py`**: import from `_demo_core`; replace JSON dumps with human-readable phase progress driven by checkpoint `execution_trace`; preserve zero-dependency guarantee
- **New `agent/scripts/demo_real.py`**: independent real-mode CLI script (no `--real` flag on `demo.py` — separate script, separate concern); validates credentials; passes `ALL_REAL_MODES` through `ResearchGraphRecipe.create()`
- **Convert `agent/scripts/demo_tui.py`** to real-only: import from `_demo_core`; remove `full_fake` UI text; add phase progress panel; check credentials at startup
- **Update `agent/Makefile`**: add `demo-real`, `demo-real-scripted` targets; `demo-tui` is now real-mode
- No files under `backend/` or `frontend/` are modified

## Capabilities

### New Capabilities

- `demo-pipeline`: shared demo core module (`_demo_core.py`), checkpoint-driven phase progress display, recipe factory for fake/real mode, and the independent `demo_real.py` real-mode CLI entry point

### Modified Capabilities

- `research-demo-tui`: TUI demo changes from full-fake only to real-mode only, with phase progress panel and credential validation at startup. Requirement RED-001 ("traverses the real full-fake lifecycle") changes to real-mode lifecycle. RED-002 ("bounded and explicitly non-product") retains bounded scope but drops the full-fake constraint.

## Impact

- **Source**: new `_demo_core.py`, new `demo_real.py`, modified `demo.py` and `demo_tui.py`
- **Production code**: two backward-compatible field additions to `DeepResearchControlResult` in `domain/lifecycle.py` (`execution_trace: tuple[str, ...] = ()`, and `implementation_mode` widened from `Literal["full_fake"]` to `str`); `_result_from_snapshot()` in `runtime/research.py` populated accordingly. No graph topology, node, handler, or recipe validation changes
- **Makefile**: new `demo-real`, `demo-real-scripted` targets; `demo-tui` semantics change
- **Tests**: existing CLI and TUI demo tests updated for new output format and real mode; new unit tests for `_demo_core.py`
- **Runtime config**: `demo_real.py` and `demo_tui.py` require `ANTHROPIC_API_KEY` (and optionally web search tool credentials) — next-agent-build impact only, no Gateway restart
