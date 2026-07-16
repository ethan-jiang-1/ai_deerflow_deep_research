## 1. Production code: expose `execution_trace` in control result

- [x] 1.1 Add `execution_trace: tuple[str, ...] = ()` to `DeepResearchControlResult` in `domain/lifecycle.py`
- [x] 1.2 Widen `implementation_mode` from `Literal["full_fake"]` to `str = "full_fake"`
- [x] 1.3 Populate `execution_trace` and `implementation_mode` in `_result_from_snapshot()` in `runtime/research.py`

## 2. Shared demo core module (`_demo_core.py`)

- [x] 2.1 Create `agent/scripts/_demo_core.py`
- [x] 2.2 Add `build_demo_recipe(*, mode, work_unit_store_factory)`
- [x] 2.3 Add `build_demo_host(*, recipe)`
- [x] 2.4 Add `check_credentials_available()` — multi-key: DEEPSEEK, Anthropic, OpenAI
- [x] 2.5 Add `display_phase_progress(phases, *, suspended_at)`
- [x] 2.6 `DemoAppConfig` auto-detects models from env vars; provides sandbox config stub
- [x] 2.7 `DemoAdapter` uses real `LocalSandbox` with path mappings (not bare `object()`)
- [x] 2.8 Patch `BootstrapBundleStore`/`RequestBundleStore`/`WorkUnitStore.create` to skip POSIX storage probe
- [x] 2.9 Write `agent/tests/unit/test_demo_core.py`

## 3. Enhance CLI fake demo (`demo.py`)

- [x] 3.1 Refactor `demo.py`: remove migrated code, import from `_demo_core`
- [x] 3.2 Replace JSON dumps with `display_phase_progress()` driven by `execution_trace`
- [x] 3.3 Diff against previous trace, preserve `--question`/`--scripted`
- [x] 3.4 Update `agent/tests/integration/test_demo_cli.py`

## 4. New CLI real demo (`demo_real.py`)

- [x] 4.1 Create `agent/scripts/demo_real.py` with `@impl DPL-004`
- [x] 4.2 Build recipe with `build_demo_recipe(mode="real", ...)`
- [x] 4.3 `--question` and `--scripted` with `non_interactive_policy` context

## 5. Convert TUI demo to real-only (`demo_tui.py`)

- [x] 5.1 Refactor imports: `from _demo_core import ...`
- [x] 5.2 Multi-key credential check with clear error message
- [x] 5.3 Pipeline progress table (Rich Table with ✓/⏸/● markers)
- [x] 5.4 Welcome panel explaining 11-phase pipeline and usage
- [x] 5.5 Update `agent/tests/integration/test_demo_tui.py`

## 6. Makefile, config, and env

- [x] 6.1 `agent/Makefile`: `demo-real`, `demo-real-scripted`, `demo-tui` with `--env-file .env`
- [x] 6.2 `agent/.env`: `DEEPSEEK_API_KEY` + `TAVILY_API_KEY` (gitignored)
- [x] 6.3 `config.yaml` at repo root: models + sandbox + tools (gitignored)
- [x] 6.4 Register `DPL: demo-pipeline` in `openspec/governance/req-registry.yaml`
- [x] 6.5 `cd agent && make test` — 562 passed
- [x] 6.6 `cd agent && make demo-scripted` — fake pipeline completes
- [x] 6.7 `cd agent && make lint` — clean

## 7. Bugs found and fixed during real-mode testing

- [x] 7.1 **`non_interactive_policy` never forwarded**: `tool.py:run_deep_research()` constructed `ResearchActionInput` without `non_interactive_policy=` kwarg → HITL auto-skip never triggered. Added the missing parameter.
- [x] 7.2 **Tools resolver can't find tools**: `_default_tools_resolver` reads from `envelope.app_config` (DemoAppConfig with `tools=[]`). Added fallback to `get_app_config()`.
- [x] 7.3 **Tool name mismatch**: Wave0/Wave1 policies expected `tavily_search` but actual Tavily tools are `web_search`/`web_fetch`. Added both to `WAVE0_WORKER_TOOL_NAMES` and `WAVE1_WORKER_TOOL_NAMES`.
- [x] 7.4 **Wave0 budget too tight**: Default `max_model_calls=3, max_total_tool_calls=12` exhausted before gate passed. Increased to `6/30` for demo.
- [ ] 7.5 **wave0 gate rejects valid output**: LLM output parsing is brittle — gate conditions sometimes reject legitimate results, causing retries to exhaust. Needs gate-tuning or output-format hardening (not a demo bug, but a research pipeline quality issue).
