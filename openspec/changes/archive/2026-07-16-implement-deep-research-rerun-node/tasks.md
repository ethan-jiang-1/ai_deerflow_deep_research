## 1. Contracts and constants

- [x] 1.1 Add red tests for updated `RerunRequest` and new `RerunScope`, `RerunPlan` contracts in `test_rerun_contracts.py`. Verify `RerunPlan` is a `FrozenContract`, `RerunScope` enum has three values (`full`, `topic`, `finding`), and `RerunPlan` carries all fields (generation, parent_generation, scope, reason, target_topic_ids, target_finding_ids, retain_topic_ids). @impl REN-001
- [x] 1.2 Update `graph/nodes/rerun/contracts.py`: replace `RerunRequest(generation)` with expanded contracts, add `RerunScope` enum and `RerunPlan` dataclass. Update `CONTRACTS` tuple. Update `NODE_SPEC` in `__init__.py` to reference new contracts. @impl REN-001
- [x] 1.3 Add red tests for `max_rerun_generations` policy field in `test_rerun_planner.py` — verify the rerun node checks `generation >= max_rerun_generations` and routes to `exhausted` when at ceiling. Verify fake graph still uses the hardcoded `MAX_FAKE_RERUN_GENERATIONS` constant. @impl REN-005
- [x] 1.4 Add `max_rerun_generations` to graph execution policy type; thread it through `NodeBuildDependencies` to the rerun node factory. Remove the hardcoded `<= MAX_FAKE_RERUN_GENERATIONS` upper bound from `ResearchCheckpoint.__post_init__` (retain `>= 0` check). `MAX_FAKE_RERUN_GENERATIONS` remains in `lifecycle.py` for the fake node. @impl REN-005
- [x] 1.5 Add red test verifying `NodeBuildDependencies` carries `max_rerun_generations` and reaches the rerun factory; verify fake factory does not receive the policy field (fake uses its own constant). @impl REN-005

## 2. New checkpoint fields

- [x] 2.1 Add red tests for new state fields (`hitl2_rerun_payload`, `rerun_scope`, `rerun_reason`, `parent_generation`, `active_topic_filter`) — verify they serialize/deserialize through checkpoint, have safe defaults (`hitl2_rerun_payload` defaults to `None`, `parent_generation` starts at `-1`, `active_topic_filter` defaults to empty tuple). @impl REN-001, REN-002, REN-003
- [x] 2.2 Add `hitl2_rerun_payload`, `rerun_scope`, `rerun_reason`, `parent_generation`, `active_topic_filter` to `ResearchCheckpoint` and `ResearchState` with safe defaults. Add field ownership entries to `OWNERSHIP_TABLE`: `hitl2_rerun_payload` writer=`GATE` (HITL2 is the writer), reader=`CONTROLLER`; others writer=`CONTROLLER`, readers=`CONTROLLER`, `PLANNER`, and `GATE`. `RESEARCH_STATE_SCHEMA_VERSION` not bumped. @impl REN-001, REN-002, REN-003

## 3. Rerun planner (scope extraction + invalidation)

- [x] 3.1 Add red tests for `build_rerun_scope(state)` in `test_rerun_planner.py`: full scope from `hitl2_rerun_payload`, topic scope with named targets, finding scope with named findings, `None` payload defaulting to full, invalid scope key raising `ValueError`, invalid target IDs defaulting to full. Verify the returned `RerunScope` does not contain generation. @impl REN-001
- [x] 3.2 Implement `graph/nodes/rerun/planner.py` with `build_rerun_scope(state)` — reads `hitl2_rerun_payload` from checkpoint, validates scope key and target IDs against `topic_registry`, produces typed `RerunScope`. Default to `FULL` when payload is `None`, absent, or contains invalid IDs. This is a pure parsing function; generation is not involved. @impl REN-001
- [x] 3.3 Add red tests for `apply_invalidation(state, scope)` — verify `synthesis_ref` cleared, `decision_brief_ref` cleared, `report_refs` emptied, `repair_counts` cleared (backward compat), `hitl2_rerun_payload` consumed (set to `None`), `accepted_submission_refs` preserved, `topic_registry` preserved. Verify no sandbox file operations (use a spy/fake on sandbox access). @impl REN-003
- [x] 3.4 Implement `apply_invalidation(state, scope)` in planner — deterministic ref-clearing including `repair_counts = {}` and `hitl2_rerun_payload = None`. @impl REN-003
- [x] 3.5 Add red tests for generation increment — monotonic increase from 0→1, rejection of decrease by reducer, `parent_generation` recorded. @impl REN-002
- [x] 3.6 Implement `apply_generation_increment(state)` in planner. @impl REN-002

## 4. Scoped WorkSpec materialization

- [x] 4.1 Add red tests for `materialize_rerun_workspecs(state, scope)` — FULL scope creates no WorkSpecs (routes to topic_planning instead), TOPIC scope creates WorkSpecs for target topics only (retained topics untouched), FINDING scope with stale sources vs deep-evidence-only creates correct WorkSpec types. @impl REN-004
- [x] 4.2 Implement `materialize_rerun_workspecs(state, scope)` in planner — delegates to existing work-unit controller for WorkSpec creation, updates `pending_work_ids`. FULL scope is a no-op (returns empty). Retained topics' `accepted_submission_refs` preserved unchanged. @impl REN-004

## 5. Downstream planner topic filter (wave0/wave1)

- [x] 5.1 Add red tests for `materialize_wave0_intents` with `topic_filter` parameter — when filter is `("B",)`, only topic B gets a WorkIntent; when filter is `None`/empty, all topics get WorkIntents (backward compatible). @impl REN-004
- [x] 5.2 Add `topic_filter: tuple[str, ...] | None = None` parameter to `materialize_wave0_intents` in `graph/nodes/wave0/subgraph.py`. When non-empty, skip entries whose `topic_id` is not in the filter set. @impl REN-004
- [x] 5.3 Add red tests for wave1 planner equivalent — `materialize_wave1_intents` with `topic_filter` parameter, same semantics. @impl REN-004
- [x] 5.4 Add `topic_filter` parameter to wave1's intent materializer. @impl REN-004
- [x] 5.5 Thread `active_topic_filter` from checkpoint state through `run_wave0_work_units_real` and `run_wave1_work_units_real`. When `active_topic_filter` is non-empty, pass it as `topic_filter`; when empty, pass `None`. @impl REN-004

## 6. Back-edge routing

- [x] 6.1 Add red tests for `determine_rerun_route(state, scope)` — `FULL` → `topic_planning`, `TOPIC` → `wave0`, `FINDING` with stale sources → `wave0`, `FINDING` with deep-evidence-only → `wave1`, generation at ceiling → `exhausted` with BLOCKED. @impl REN-005
- [x] 6.2 Implement `determine_rerun_route(state, scope)` in planner. @impl REN-005
- [x] 6.3 Add red tests for gate state reset — `gate_attempts_by_phase` and `repair_budget_by_phase` cleared for affected phases; unaffected phases retain state. @impl REN-006
- [x] 6.4 Implement gate state reset as part of the rerun node's state update, scoped to affected phases only. @impl REN-006
- [x] 6.5 Update `graph/builder.py` rerun conditional edge map: KEEP the existing `"next": "topic_planning"` key (fake backward compat), ADD `"topic_planning": "topic_planning"` (real FULL), `"wave0": "wave0"` (real TOPIC/FINDING), `"wave1": "wave1"` (real FINDING deep). `"exhausted": END` unchanged. @impl REN-005, REN-007
- [x] 6.6 Update `graph/topology.py` — ADD new `TopologyEdge` entries for `rerun → wave0` (label `"wave0"`) and `rerun → wave1` (label `"wave1"`). KEEP existing `TopologyEdge("rerun", "next", "topic_planning")` for fake compat. Run `topology_snapshot.py` to regenerate snapshot. @impl REN-005, REN-007

## 7. Real factory assembly

- [x] 7.1 Add red tests for `build_real(dependencies)` in `test_rerun_node.py` — full lifecycle: receives HITL2 rerun decision, produces RerunPlan, invalidates projections, increments generation, creates WorkSpecs, routes correctly. Test all three scope paths and the exhausted path. @impl REN-001..007
- [x] 7.2 Implement `build_real` in `graph/nodes/rerun/node.py`: orchestrate `build_rerun_scope` → `apply_invalidation` → `apply_generation_increment` → `materialize_rerun_workspecs` → `determine_rerun_route` → assemble `RerunPlan` → return state update. Code-only, no `capabilities.run_agent()`. @impl REN-001..007

## 8. Recipe wiring and mixed-graph integration

- [x] 8.1 Add red tests in existing recipe/capability tests that recipe detects `rerun=real`, accepts when `hitl2=real` is set, and rejects when `hitl2=real` is absent with a typed dependency error. @impl REN-007
- [x] 8.2 Wire `runtime/research.py` with the dependency guard: `rerun=real` requires `hitl2=real`. @impl REN-007
- [x] 8.3 Add red test for real rerun requiring full real chain — selecting `rerun=real` with any upstream node still `fake` transitively fails. @impl REN-007

## 9. Full-fake and mixed-graph E2E

- [x] 9.1 Add full-fake regression test: fake rerun at generation 0 bumps to 1 and routes `next` → `topic_planning`; at generation 1 bumps to 2 and routes `exhausted` → blocked. Verify no scope, no invalidation, no WorkSpec creation. @impl REN-007
- [x] 9.2 Add mixed-graph test: all upstream nodes real through hitl2, rerun real, readiness and final_delivery still fake. Verify topology unchanged, real rerun routes correctly, full-fake rerun path preserved.
- [x] 9.3 Add contract test for `NodeSpec` real factory: verify `build_real` is no longer `UNAVAILABLE_REAL_FACTORY`.

## 10. Documentation and governance

- [x] 10.1 Register new paths in `project-structure.toml`; render AGENTS.md; pass architecture check.
- [x] 10.2 Update `agent/AGENTS.md` and `agent/README.md` with real rerun node capability.
- [x] 10.3 Update `_backlog/plans/deep-research-14-rerun-node.md` — mark as implemented after archive.

## 11. Verification

- [x] 11.1 Run `cd agent && make test-unit && make test-contract`; fix all failures.
- [x] 11.2 Run `cd agent && make test`; verify complete suite green.
- [x] 11.3 Run `cd agent && make format && make lint && make lock-check`.
- [x] 11.4 Run `python3 openspec/governance/check_project_reqs.py` — must PASS with REN-001..007 registered.
- [x] 11.5 Run `python3 openspec/governance/check_project_specs.py` — must PASS with no delta headers in main specs.
- [x] 11.6 Run `openspec validate implement-deep-research-rerun-node --strict`.
- [x] 11.7 Verify no `backend/` or `frontend/` changes.
