## 1. Production code: expose `execution_trace` in control result

- [x] 1.1 Add `execution_trace: tuple[str, ...] = ()` field to `DeepResearchControlResult` in `domain/lifecycle.py`
- [x] 1.2 Widen `implementation_mode` from `Literal["full_fake"]` to `str = "full_fake"` in `DeepResearchControlResult`
- [x] 1.3 Populate `execution_trace` and `implementation_mode` in `_result_from_snapshot()` in `runtime/research.py`

## 2. Shared demo core module (`_demo_core.py`)

- [x] 2.1 Create `agent/scripts/_demo_core.py`
- [x] 2.2 Add `build_demo_recipe(*, mode, work_unit_store_factory)`
- [x] 2.3 Add `build_demo_host(*, recipe)`
- [x] 2.4 Add `check_credentials_available()`
- [x] 2.5 Add `display_phase_progress(phases, *, suspended_at)`
- [x] 2.6 Write `agent/tests/unit/test_demo_core.py`

## 3. Enhance CLI fake demo (`demo.py`)

- [x] 3.1 Refactor `demo.py`: remove migrated code, import from `_demo_core`
- [x] 3.2 Replace JSON dumps with `display_phase_progress()` calls driven by `execution_trace` from control result dict
- [x] 3.3 After each `run_deep_research()` call, extract `execution_trace` from result dict, diff against previous trace
- [x] 3.4 Preserve `--question` and `--scripted` flags, `--scripted` defaults, and `"not completed research"` final message
- [x] 3.5 Update `agent/tests/integration/test_demo_cli.py`

## 4. New CLI real demo (`demo_real.py`)

- [x] 4.1 Create `agent/scripts/demo_real.py` with `@impl DPL-004`
- [x] 4.2 Build recipe with `build_demo_recipe(mode="real", ...)`, run lifecycle with phase progress display
- [x] 4.3 Support `--question` and `--scripted` flags with non-interactive policy context

## 5. Convert TUI demo to real-only (`demo_tui.py`)

- [x] 5.1 Refactor imports: `from _demo_core import ...` instead of `from demo import ...`
- [x] 5.2 Call `check_credentials_available()`; if False, display error and exit
- [x] 5.3 Remove `full_fake` banner text; update banner to reflect real mode
- [x] 5.4 Add phase progress tracking via `execution_trace` from result dict
- [x] 5.5 Update `agent/tests/integration/test_demo_tui.py` with mock patching

## 6. Makefile and governance

- [x] 6.1 Update `agent/Makefile`
- [x] 6.2 Register `DPL: demo-pipeline` and IDs `DPL-001` through `DPL-005` in `openspec/governance/req-registry.yaml`
- [x] 6.3 Run `python3 openspec/governance/check_project_reqs.py` and `python3 openspec/governance/check_project_specs.py` — both must PASS
- [x] 6.4 Run `cd agent && make test` — all existing tests pass (updated where needed)
- [x] 6.5 Run `cd agent && make demo-scripted` — fake pipeline completes with phase progress display
- [x] 6.6 Run `cd agent && make lint` — ruff check + format clean
