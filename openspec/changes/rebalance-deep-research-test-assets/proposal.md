## Why

Deep Research now has broad deterministic coverage and a working live/release lane, but the distribution is still hollow at the deterministic agent-workflow layer: the declared `workflow` selector collects no tests, several reusable scenario families are metadata rather than executable replays, and the shortest live canaries stop before the Wave1/Wave2 provider-shape failures that dominated recent full-real diagnosis. Tightening these assets now will move failures to shorter, stable seams before another feature cycle makes full-pipeline debugging expensive again.

## What Changes

- Make deterministic workflow authenticity mechanically selectable and auditable: tests that claim `SCRIPTED_REAL_WORKFLOW` must traverse the applicable real lifecycle/graph or agent-loop seams, and a dedicated workflow selection must collect them without overlapping the deterministic correctness selections.
- Turn the first-wave scenario catalog into typed executable deterministic cases. Separate lane-neutral risk families from lane-specific cases; each case owns the invariants and metrics its endpoint can actually prove, every family binds to at least one collected deterministic case, and governance rejects descriptive-only metadata.
- Add a redacted provider-shape regression corpus for historical Wave0, Wave1, and Wave2 output variations, linked to their live/release discoveries and checked for normalization, canonical ordering, citation binding, and fail-closed behavior.
- Extend live evaluation with short, directly seeded Wave1, Wave2 synthesis, and targeted-evidence canaries so provider-sensitive late nodes are exercised without adding another full-pipeline E2E.
- Replace placeholder quality calculations with typed pure metrics for structural citation binding, semantic citation precision, final citation completeness, synthesis finding support, must-answer coverage, canonical-URL and host diversity, contradiction recall, and unsupported claims over validated authorities and labeled replay expectations. Missing authority, empty denominators, or semantic labels produce an explicit unavailable result rather than a vacuous score. Quality values remain observational until a separately reviewed baseline promotes a threshold.
- Strengthen requirement, incident, node, scenario, and lane governance around one collected-selector evidence-claim registry so selector existence alone cannot establish authenticity or stable-seam coverage.
- Establish one durable test-evidence authority/lifecycle policy under `openspec/governance/`, referenced concisely from OpenSpec authoring rules and the agent guide. The `evaluation-hardening` main spec owns approved semantics, its one active delta owns pending modifications until archive/sync, and archived artifacts are historical; the policy explains where exact evidence metadata and executable checks live, how synchronized changes are reviewed, and how future changes choose the lowest responsible seam, justify trace-replay/live/E2E escalation, and isolate the mutable process state they actually touch without duplicating the executable test catalog.
- Preserve successful full-real proof as a minimal committed redacted attestation instead of relying on gitignored local `.reports`, and retire or update contradictory committed release-status documents.
- Keep one manual full-real release acceptance lane. No additional routine full-pipeline E2E is introduced, and test count or line coverage is not an acceptance target.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `evaluation-hardening` (`EVH-001`, `EVH-002`, `EVH-005..EVH-010`): make deterministic scenario cases, workflow authenticity, provider-shape regression assets, late-node live canaries, quality metrics, coverage governance, and the archive-durable test-evidence authority chain executable and mechanically verifiable. Existing fault-injection and adversarial-isolation requirements `EVH-003/004` remain semantically unchanged and gain cases through the revised corpus.

## Impact

- Affected project-owned surfaces: `agent/tests/scenarios/`, `agent/tests/eval/`, focused tests under `agent/tests/{graph,integration,unit,contract,live}/`, test fixtures/assets, `agent/scripts/check_test_assets.py`, requirement-coverage governance, `agent/Makefile`, `agent/pyproject.toml`, agent CI workflows, `agent/README.md`, `agent/AGENTS.md` including its generated structure block, test-evidence documents under `agent/docs/`, `openspec/governance/test-evidence-policy.md`, `openspec/governance/project-structure.toml` under the existing `PRS-004` exact-enumeration contract, `openspec/governance/README.md`, and the authoring rules in `openspec/config.yaml`.
- Affected graph paths are test execution of `bootstrap`, `hitl1`, `topic_planning`, `wave0`, `wave1`, `wave2_synthesis`, `targeted_evidence`, `hitl2`, `rerun`, `readiness`, and `final_delivery`; production graph topology and checkpoint schemas do not change.
- Tests read or create only isolated test-owned checkpoint state and sandbox artifacts under the existing request, work, submission-ledger, synthesis, targeted-evidence, and final-delivery layouts. The authority split remains checkpoint control state, validated submission ledger, and sandbox content.
- No runtime configuration, model/tool registration, mount, dependency, public tool schema, Agent/SOUL, skill, MCP, ACP, or DeerFlow task-subagent behavior changes. Root runtime `config.yaml` and `extensions_config.json` remain unused by this change, aside from credentialed live fixtures constructing isolated test configuration; editing OpenSpec's separate `openspec/config.yaml` changes planning guidance only. No next-agent-build or Gateway restart impact is introduced.
- No files under `backend/` or `frontend/` are modified. Any change to those upstream mirrors is a separate breaking escalation.
