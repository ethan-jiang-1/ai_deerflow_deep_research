## 1. Non-interactive policy — tool + state

- [x] 1.1 Modify `tool.py`: allow non-interactive when `non_interactive_policy` dict with `auto_profile` and `auto_proceed` is present. Pass through `ResearchActionInput`. @impl RUO-001
- [x] 1.2 Add `non_interactive_policy: dict | None = None` to `ResearchActionInput`. @impl RUO-001
- [x] 1.3 Inject `non_interactive_policy` into initial graph `values` in `StartResearchHandler._invoke_graph`. @impl RUO-001
- [x] 1.4 Add `non_interactive_policy` to ResearchCheckpoint and ResearchState with safe default None. @impl RUO-001
- [x] 1.5 Add ownership entry for `non_interactive_policy`. @impl RUO-001

## 2. Non-interactive policy — HITL nodes

- [x] 2.1 Modify HITL1 `node.py`: before `interrupt()`, check `auto_profile`; if True, generate default profile with `degraded_profile=True`, skip interrupt, route `accepted`. @impl RUO-002
- [x] 2.2 Modify HITL2 `node.py`: before `interrupt()`, check `auto_proceed`; if True, skip interrupt, route `proceed` with audit note. @impl RUO-002
- [x] 2.3 Add tests for HITL1 auto-profile and HITL2 auto-proceed. @impl RUO-002

## 3. Orphan detection

- [x] 3.1 Add orphan detection in work-unit store: on replay, detect running attempts with stale generation, transition to failed. @impl RUO-003
- [x] 3.2 Add tests for orphan detection. @impl RUO-003

## 4. Verification

- [x] 4.1 Run `make format && make lint`.
- [x] 4.2 Run `make test`; verify full-fake unchanged.
- [x] 4.3 Run governance checks — both PASS.
- [x] 4.4 Verify no `backend`/`frontend` changes.
