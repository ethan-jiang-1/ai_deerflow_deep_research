## Context

The existing `demo.py` and `demo_tui.py` share substantial infrastructure: `DemoAdapter` (custom `RuntimeAdapter` with temp directories), synthetic tool-call construction helpers (`_tool_call`, `_runtime`, `_suspension`), and lifecycle orchestration patterns. Currently `demo_tui.py` imports directly from `demo.py` — fragile coupling with no shared abstraction.

Three demo variants are needed: CLI fake (enhanced with phase display), CLI real (new), and TUI real (converted). All three share the same adapter, helpers, phase metadata, and recipe-building logic.

The graph's `ResearchState.execution_trace` field — a `tuple[str, ...]` appended by each node's `node_update()` call — already records the authoritative execution path. This is ground truth, not a guess.

## Goals / Non-Goals

**Goals:**
- Extract shared demo infrastructure into `agent/scripts/_demo_core.py`
- Display pipeline phase progress driven by checkpoint `execution_trace` diffs
- Provide a clean real-mode CLI entry point (`demo_real.py`) that correctly passes `ALL_REAL_MODES` through `ResearchGraphRecipe.create()`
- Convert TUI to real-only with phase progress panel
- Keep `demo.py` as the zero-dependency fake entry point, backward-compatible

**Non-Goals:**
- No `--real` flag on `demo.py` — real mode is a separate script, separate concern
- No changes to graph topology, nodes, handlers, or recipe validation logic
- No changes to `backend/` or `frontend/`
- No streaming/astream_events integration in this change (checkpoint-driven progress is sufficient)
- No partial-real (mixed fake/real) mode support in demos
- Minimal production code changes limited to two backward-compatible field additions in `DeepResearchControlResult` (see Decision 6)

## Decisions

### Decision 1: Separate scripts for fake and real (`demo.py` + `demo_real.py`)

**Choice**: Two independent CLI scripts rather than one script with `--real` flag.

**Alternatives considered**:
- Single `demo.py --real`: rejected because fake and real have fundamentally different dependency boundaries (zero-API vs. model+web credentials), setup logic (no bridge vs. `RuntimeNodeAgentBridge`), and error paths. A flag would force `if real: ... else: ...` branches throughout the script.
- Previous `--real` attempts (commits 8093821, 9c5c0c4) were both reverted — the flag approach proved fragile.

**Rationale**: One script, one responsibility. `demo.py` stays the zero-dependency quick smoke. `demo_real.py` owns the credential check, bridge setup, and real-specific error messages. The Makefile already isolates them as separate targets (`make demo` vs `make demo-real`).

### Decision 2: Shared code in `_demo_core.py` (not in `deerflow_deep_research` package)

**Choice**: `agent/scripts/_demo_core.py` as an internal module imported by all three scripts.

**Alternatives considered**:
- Put shared code in `deerflow_deep_research.demo` package: rejected — demo infrastructure is not production code and should not ship in the installable package.
- Keep copying between scripts: rejected — current state (`demo_tui.py` imports from `demo.py`) is fragile.

**Rationale**: The underscore prefix signals "internal to scripts/". All three scripts live in the same directory, so `from _demo_core import ...` works without `sys.path` manipulation. Tests already use `sys.path.insert(0, str(SCRIPTS))` for the same pattern.

**Contents of `_demo_core.py`**:
| Symbol | Description |
|--------|-------------|
| `DemoAppConfig` | Stub app config (`checkpointer=None, database=None`) |
| `DemoAdapter` | Custom `RuntimeAdapter` with temp dirs and `WorkUnitStore` factory |
| `_tool_call(action, call_id, research_id)` | Builds synthetic `AIMessage` with `deep_research` tool call |
| `_runtime(messages, call_id, context=None)` | Builds fake `SimpleNamespace` runtime; `context` dict for `non_interactive_policy` |
| `_suspension(command)` | Extracts `(control_result, hitl_request)` from suspension `Command` |
| `PHASE_META` | `dict[str, tuple[str, str]]` — logical_name → (Chinese label, description) |
| `ALL_REAL_MODES` | `{name: "real" for name in LOGICAL_NODES}` |
| `build_demo_recipe(*, mode, work_unit_store_factory)` | Returns `ResearchGraphRecipe` for "fake" or "real" |
| `build_demo_host(*, recipe)` | Returns `GraphHost` with research handlers registered |
| `create_hitl_response(...)` | Builds `HumanMessage` with `human_input_response` payload |
| `check_credentials_available()` | Returns `True` if `ANTHROPIC_API_KEY` is set in environment |
| `display_phase_progress(phases, *, suspended_at)` | Prints `→ name  desc` for completed, `⏸ name  desc` for suspended |

### Decision 3: Checkpoint-driven phase progress via control result (not streaming)

**Choice**: After each `run_deep_research()` call returns, extract `execution_trace` from the `DeepResearchControlResult` dict and diff against the previous trace to determine which phases completed.

**Alternatives considered**:
- **LangGraph streaming (`astream_events`)**: Requires modifying `ResearchActionHandler.execute()` to accept progress callbacks. More granular (per-node events in real time), but adds complexity. Reserved for future TUI enhancement.
- **Hardcoded phase lists** (previous reverted attempt): Wrong — display doesn't reflect actual graph execution. Rejected decisively.

**Rationale**: `execution_trace` is the graph's own audit trail — each node calls `node_update()` which appends the node name via `merge_trace` reducer. Comparing trace before/after `ainvoke` shows exactly which nodes ran. No graph changes needed. Fake-mode nodes are instant so batch display is fine; real-mode nodes take longer but the checkpoint still tells the truth after each `ainvoke` returns.

```
# Core logic in each demo script:
# After each run_deep_research() returns (Command or dict):
result_dict = control_result  # extracted from Command suspension or terminal dict
current_trace = tuple(result_dict.get("execution_trace", ()))
new_phases = [p for p in current_trace if p not in previous_trace]
display_phase_progress(new_phases, suspended_at=result_dict.get("phase"))
previous_trace = current_trace
```

### Decision 4: Real mode through `ResearchGraphRecipe.create()` validation path

**Choice**: `demo_real.py` and `demo_tui.py` construct the recipe via:
```python
ResearchGraphRecipe.create(
    implementation_modes=ALL_REAL_MODES,
    work_unit_store_factory=adapter.create_work_unit_store,
    node_agent_bridge_factory=RuntimeNodeAgentBridge,
)
```

**Alternatives considered**:
- Bypassing `create()` and calling `build_research_graph()` directly (previous reverted attempt): Rejected — skips the dependency chain validator. If a node's real factory is unavailable, the error should come from `resolve_implementations()`, not a cryptic runtime failure.
- Partial real (e.g., only hitl2/rerun/readiness/final_delivery real): Rejected — user wants full pipeline; partial adds complexity without value.

**Rationale**: `ResearchGraphRecipe.create()` validates that all 11 nodes have real factories and enforces the dependency chain. `RuntimeNodeAgentBridge` is the production bridge that resolves model and tool capabilities from `envelope.app_config`. The demo's `DemoAppConfig` is minimal — model resolution falls through to environment variables.

### Decision 5: TUI real-only

**Choice**: `demo_tui.py` removes fake mode entirely. Starts up only if credentials are available.

**Alternatives considered**:
- Keep fake TUI: Rejected — user explicitly said "没有fake TUI". Fake TUI provides no value (all phases instant, progress bar meaningless).

**Rationale**: The TUI exists to show real research progress. Credential check at startup with clear error message. Tests updated to use mock bridge or marked `@requires_llm`.

### Decision 6: Two backward-compatible field additions to `DeepResearchControlResult`

**Choice**: Add `execution_trace: tuple[str, ...] = ()` to `DeepResearchControlResult`, and widen `implementation_mode` from `Literal["full_fake"]` to `str = "full_fake"`.

**Alternatives considered**:
- Read trace from checkpoint via a new `GraphHost` method: Rejected — adds API surface to the host for demo-only needs.
- Keep `implementation_mode` hardcoded: Rejected — real-mode results would misleadingly report `"full_fake"`.

**Rationale**: Both are backward-compatible Pydantic field changes (default values ensure existing serialization is unchanged). `execution_trace` is populated from `checkpoint.execution_trace` in `_result_from_snapshot()`. `implementation_mode` is set from the recipe's resolved mode map. Neither changes graph topology, node behavior, or handler logic. These are the only two production code changes in this change.

## Risks / Trade-offs

| Risk | Mitigation |
|------|-----------|
| **Checkpoint progress may batch phases** — in real mode, `ainvoke` runs multiple nodes before returning; display shows them all at once | Acceptable for this change. Future: TUI can poll `aget_state()` on an interval for finer granularity |
| **`demo_real.py` requires credentials** — first-run experience may fail if `ANTHROPIC_API_KEY` not set | Clear error message listing required env vars. `make demo-real` docs mention prerequisites |
| **TUI test breakage** — existing TUI tests assume `full_fake` | Tests updated: use `FakeToolCallingModel`-based mock bridge for TUI tests without real credentials; keep behavioral assertions |
| **`_demo_core.py` import path** — `scripts/` is not a Python package | Same pattern as current `demo_tui.py: from demo import ...`. Both scripts run from `scripts/` directory via `make` targets which set `cwd` correctly |

## Field Notes: What actually broke in real-mode testing

The spec and tasks above describe the *planned* implementation (all `[x]` checked). When we attempted `make demo-real` and `make demo-tui` with real credentials (2026-07-16), the following issues surfaced. Each is a **deviation from the original spec** that required code changes not foreseen in the task list.

### 1. Credential check was Anthropic-only

**Symptom**: `check_credentials_available()` returned `False` despite `DEEPSEEK_API_KEY` being set.

**Root cause**: `_demo_core.py:check_credentials_available()` checked only `ANTHROPIC_API_KEY`.

**Fix**: Expanded to a tuple of known env vars (`DEEPSEEK_API_KEY`, `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`). All error messages in `demo_tui.py` and `demo_real.py` updated to list all three.

**Files**: `_demo_core.py`, `demo_tui.py`, `demo_real.py`

### 2. `DemoAppConfig` had no model configuration

**Symptom**: `create_chat_model(app_config=DemoAppConfig())` → `AttributeError: 'DemoAppConfig' has no attribute 'models'`.

**Root cause**: The original `DemoAppConfig` was `class DemoAppConfig: checkpointer=None; database=None` — two bare class attributes. `create_chat_model()` needs `config.models[0].name` and `config.get_model_config(name)`.

**Fix**: `DemoAppConfig` now auto-detects available API keys and builds real Pydantic `ModelConfig` entries:
- `DEEPSEEK_API_KEY` → `PatchedChatDeepSeek` with `deepseek-v4-pro` (primary) and `deepseek-v4-flash` (fallback)
- `ANTHROPIC_API_KEY` → `langchain_anthropic:ChatAnthropic` with `claude-sonnet-4-5-20250901`
- `OPENAI_API_KEY` → `langchain_openai:ChatOpenAI` with `gpt-4o`

Uses `base_url` (not `api_base`) for DeepSeek — `PatchedChatDeepSeek` is NOT in `_OPENAI_COMPAT_USE_PATHS`, so the `api_base→base_url` normalization does NOT apply to it.

**Files**: `_demo_core.py` (rewrote `DemoAppConfig`, added `_MODEL_REGISTRY`, `_resolve_demo_models()`)

### 3. `DemoAdapter` used bare `object()` as parent sandbox

**Symptom**: `verify_runtime_work_unit_storage()` → `WorkUnitStorageCheck("not_ready", "thread_mount_unavailable")` because `provider.get(parent.id)` failed on `object()`.

**Root cause**: `DemoAdapter.__init__` set `parent_sandbox=object()`. The work-unit storage verifier expects a real `Sandbox` with an `id` attribute that the provider can look up.

**Fix**: Create a proper `LocalSandbox` with path mappings for `/mnt/user-data/{workspace,uploads,outputs}`, and register it as the provider's `_generic_sandbox` via `_prime_demo_sandbox()`. Also added `_DemoSandboxConfig` to `DemoAppConfig` so `classify_work_unit_storage()` returns `"ready"`.

**Files**: `_demo_core.py` (added `LocalSandbox` + `PathMapping` imports, `_prime_demo_sandbox()`, `_DemoSandboxConfig`)

### 4. Work-unit storage probe fails in demo temp directories

**Symptom**: Even with `LocalSandbox` registered, `_verify_runtime_work_unit_storage()` raised `_ProbeCleanupError` — the POSIX probe's cleanup step failed in the temp directory context.

**Root cause**: The probe writes test files through host paths, reads them back through sandbox virtual paths, verifies content equality, then cleans up via `parent.execute_command("rm -f ...")`. In the demo's temp-directory context, cleanup ordering or sandbox path resolution differed from production.

**Fix**: Patched `BootstrapBundleStore.create`, `RequestBundleStore.create`, and `WorkUnitStore.create` to use a no-op `_demo_storage_verifier` that returns `WorkUnitStorageCheck("ready", ...)` directly. The patch only overrides the *default* `storage_verifier` kwarg — explicit callers (tests, Gateway) that pass their own verifier are unaffected.

**Files**: `_demo_core.py` (added `_demo_storage_verifier`, `_install_demo_storage_patch()` called at module import)

### 5. `config.yaml` required at project root for sandbox provider resolution

**Symptom**: `get_sandbox_provider()` → `get_app_config()` → `FileNotFoundError: config.yaml not found`.

**Root cause**: Several infrastructure code paths (sandbox provider, work-unit storage classifier) call `get_app_config()` which reads `config.yaml` from the project root. The demo previously assumed no config file was needed.

**Fix**: Created a minimal `config.yaml` at repo root with:
```yaml
models: [deepseek-v4-pro, deepseek-v4-flash]
sandbox: {use: deerflow.sandbox.local:LocalSandboxProvider, allow_host_bash: true}
```
The file is gitignored (already in root `.gitignore`).

**Files**: `config.yaml` (new, repo root)

### 6. Makefile didn't load `.env`

**Symptom**: `DEEPSEEK_API_KEY` was in `agent/.env` but `uv run` didn't pick it up.

**Root cause**: `uv run` does not auto-load `.env` files unless `--env-file` is passed.

**Fix**: Added `--env-file .env` to `demo-tui`, `demo-real`, and `demo-real-scripted` Makefile targets.

**Files**: `agent/Makefile`

### 7. Non-interactive mode: `non_interactive_policy` was never passed to `ResearchActionInput`

**Symptom**: `make demo-real-scripted` always suspended at HITL1 despite `auto_profile=True`. Debug revealed `state.get("non_interactive_policy")` was always `None`.

**Root cause**: `tool.py:run_deep_research()` line 175 constructed `ResearchActionInput(...)` **without** the `non_interactive_policy` keyword argument. The variable was extracted from `runtime.context` (lines 139-142) and validated (lines 143-155) but never forwarded to the dataclass constructor. `StartResearchHandler.execute()` relies on `action_input.non_interactive_policy` to populate the initial checkpoint state.

**Fix**: Added `non_interactive_policy=non_interactive_policy` to the `ResearchActionInput(...)` constructor call. This is a **one-line production-code change** in `agent/src/deerflow_deep_research/tool.py:181`.

**Result**: Pipeline now runs through bootstrap → HITL1 (auto_profile, no interrupt) → topic_planning (LLM plan generation succeeds) → wave0. Wave0 needs web search tools — without them it exhausts retries and the graph terminates BLOCKED.

**Status**: **Fixed.** Wave0 tool configuration is a separate concern (requires Tavily/DuckDuckGo API keys or equivalent).

**Files**: `agent/src/deerflow_deep_research/tool.py`

### 8. VS Code: ruff isort + f-string warnings

**Not a demo bug, but encountered during setup.** The backend's `.vscode/settings.json` had `"source.organizeImports": "explicit"` which conflicted with ruff's own import formatting. Removed that line. Added `F541` (f-string without placeholders) and `I001` (unsorted imports) to `ruff.lint.ignore` in the root `.vscode/settings.json`.

**Files**: `backend/.vscode/settings.json`, `.vscode/settings.json`

### Summary of unplanned changes

| # | Issue | Production code touched? | Demo code touched? |
|---|-------|------------------------|-------------------|
| 1 | Credential check | No | Yes |
| 2 | DemoAppConfig models | No | Yes |
| 3 | parent_sandbox=object() | No | Yes |
| 4 | Storage probe failure | No | Yes |
| 5 | config.yaml missing | No | New file |
| 6 | Makefile --env-file | No | Yes |
| 7 | `non_interactive_policy` missing from ResearchActionInput | **Yes** (1 line: `tool.py`) | Yes |
| 8 | VS Code settings | No | No (IDE config) |

**Key takeaway**: The original design assumed the demo could run against the full production infrastructure (sandbox provider, storage verification, model factory) with only `DemoAppConfig` as a shim. In practice, four additional infrastructure layers needed demo-specific handling: model config resolution, sandbox identity, storage probe, and config file presence. The patches in `_demo_core.py` isolate these from production code — zero changes to `agent/src/`.
