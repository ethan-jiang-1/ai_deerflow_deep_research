## 1. Demo Contract And Dependency

- [x] 1.1 Add red tests for the standalone Textual happy path, invalid decision, explicit cancel, full-fake disclaimer, and no product-service dependency (`RED-001`, `RED-002`).
- [x] 1.2 Add a dedicated agent-only Textual optional extra and locked dependency; keep normal runtime dependencies unchanged (`RED-002`).

## 2. Thin Textual Demo

- [x] 2.1 Implement `agent/scripts/demo_tui.py` as a thin stage UI over the existing Change 01 lifecycle helpers, with no second graph or persisted authority (`RED-001`).
- [x] 2.2 Add `make -C agent demo-tui`, visible request/status/HITL/terminal panels, advertised-decision validation, and explicit lifecycle cancel (`RED-001`, `RED-002`).

## 3. Documentation And Verification

- [x] 3.1 Document the standalone-demo boundary and commands in `agent/README.md` and the backlog plan; do not claim formal DeerFlow TUI/Web compatibility (`RED-002`).
- [x] 3.2 Run the focused pilot tests, full agent suite, lint/format, governance, strict OpenSpec validation, diff checks, and confirm no `backend/` or `frontend/` changes (`RED-001`, `RED-002`).
