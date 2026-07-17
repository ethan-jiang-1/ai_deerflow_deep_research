## Why

Deep Research now has broad deterministic coverage and a working live/release lane, but the distribution is still hollow at the deterministic agent-workflow layer: the declared `workflow` selector collects no tests, several reusable scenario families are metadata rather than executable replays, and the shortest live canaries stop before the Wave1/Wave2 provider-shape failures that dominated recent full-real diagnosis. Tightening these assets now will move failures to shorter, stable seams before another feature cycle makes full-pipeline debugging expensive again.

## What Changes

- Make deterministic workflow authenticity mechanically selectable and auditable: tests that claim `SCRIPTED_REAL_WORKFLOW` must traverse the applicable real node, bridge, middleware, policy, validator, authority store, and gate seams, and a dedicated workflow lane must collect and execute them.
- Turn the first-wave scenario catalog into typed executable replay assets. Every declared scenario must bind real scripted model/tool/fault inputs to an executor, derive assertions from authoritative checkpoint, ledger, and sandbox outputs, and fail governance when it is only descriptive metadata.
- Add a redacted provider-shape replay corpus for historical Wave0, Wave1, and Wave2 output variations, linked to their live/release discoveries and checked for normalization, canonical ordering, citation binding, and fail-closed behavior.
- Extend live evaluation with short, directly seeded Wave1, Wave2 synthesis, and targeted-evidence canaries so provider-sensitive late nodes are exercised without adding another full-pipeline E2E.
- Replace placeholder quality calculations with pure metrics over validated evidence, findings, question bindings, canonical sources, and citation maps. Quality values remain observational until a separately reviewed baseline promotes a threshold.
- Strengthen requirement, incident, node, scenario, and lane governance so selector existence alone cannot establish authenticity or stable-seam coverage.
- Keep one manual full-real release acceptance lane. No additional routine full-pipeline E2E is introduced, and test count or line coverage is not an acceptance target.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `evaluation-hardening` (`EVH-001..EVH-010`): make replay scenarios, workflow authenticity, provider-shape regression assets, late-node live canaries, quality metrics, and coverage governance executable and mechanically verifiable.

## Impact

- Affected project-owned surfaces: `agent/tests/scenarios/`, `agent/tests/eval/`, focused tests under `agent/tests/{graph,integration,unit,contract,live}/`, test fixtures/assets, `agent/scripts/check_test_assets.py`, requirement-coverage governance, `agent/Makefile`, `agent/pyproject.toml`, agent CI workflows, `agent/README.md`, `agent/AGENTS.md`, and `agent/docs/regression-descent.md`.
- Affected graph paths are test execution of `bootstrap`, `hitl1`, `topic_planning`, `wave0`, `wave1`, `wave2_synthesis`, `targeted_evidence`, `hitl2`, `rerun`, `readiness`, and `final_delivery`; production graph topology and checkpoint schemas do not change.
- Tests read or create only isolated test-owned checkpoint state and sandbox artifacts under the existing request, work, submission-ledger, synthesis, targeted-evidence, and final-delivery layouts. The authority split remains checkpoint control state, validated submission ledger, and sandbox content.
- No runtime configuration, model/tool registration, mount, dependency, public tool schema, Agent/SOUL, skill, MCP, ACP, or DeerFlow task-subagent behavior changes. The existing `config.yaml` and `extensions_config.json` surfaces are unused by this change, aside from credentialed live fixtures constructing isolated test configuration. No next-agent-build or Gateway restart impact is introduced.
- No files under `backend/` or `frontend/` are modified. Any change to those upstream mirrors is a separate breaking escalation.
