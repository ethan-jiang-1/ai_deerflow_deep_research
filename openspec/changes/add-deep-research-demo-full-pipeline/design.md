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
