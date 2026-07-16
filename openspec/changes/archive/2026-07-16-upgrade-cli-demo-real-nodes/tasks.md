## 1. Demo script

- [x] 1.1 Add `--real` flag to `demo.py` argument parser and `run_demo()` signature.
- [x] 1.2 When `--real`: construct `implementation_modes` dict with hitl2, rerun, readiness, final_delivery = "real".
- [x] 1.3 Use `build_research_graph()` + minimal `ResearchGraphRecipe` to bypass dependency checks.

## 2. Makefile (agent/Makefile)

- [x] 2.1 Add `demo-real` target to `agent/Makefile` (alongside existing `demo`, `demo-scripted`, `demo-tui`): `uv run --extra operations python scripts/demo.py --scripted --real`

## 3. Verification

- [x] 3.1 Test `make demo` — full-fake unchanged.
- [x] 3.2 Test `make demo-real` — runs with real non-agent nodes, reaches COMPLETED.
- [x] 3.3 Run `make test` — full suite green.
