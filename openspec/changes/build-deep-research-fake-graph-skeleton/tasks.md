Execution order is a hard dependency chain: groups `1 -> 2 -> ... -> 12`, and
tasks within each group run in numeric order. Group 1 is a hard viability gate;
do not create the business topology if reflected `Command`/artifact propagation
does not work on the pinned stack.

## 1. Reflected HITL And Host Viability Gates

- [ ] 1.1 Add a red integration test that resolves `deerflow_deep_research.tool:deep_research_tool` through DeerFlow's public reflected-tool loader, invokes it through the pinned async ToolNode path, and proves a tool-returned public `Command(goto=END)` preserves the active `tool_call_id`, one `ToolMessage(name="deep_research")`, and its version-1 `artifact.human_input` payload (`RUI-001`, `RUI-006`, `REG-003`).
- [ ] 1.2 Make the reflected-command fixture green using only public LangChain/LangGraph APIs; if `Command` or `ToolMessage.artifact` is lost, stop the change and revise the design without editing `backend/` or `frontend/` (`RUI-006`, `REG-003`).
- [ ] 1.3 Add a red default-dispatch test proving two ordinary reflected invocations in one process resolve the same lazily created GraphHost/memory saver while two isolated test hosts remain independent (`RUI-006`, `REG-005`).
- [ ] 1.4 Implement the process-local combined-host resolver without retaining request envelopes or SQL providers, keep test injection/reset deterministic, and make the existing `infra_probe` same-process revisit work through the default dispatch path; annotate the owner with `@impl RUI-006` (`RUI-001`, `RUI-006`).

## 2. Skeleton State And Pure Lifecycle Contracts

- [ ] 2.1 Add red unit tests for the versioned minimal skeleton state, bounded execution trace, lifecycle/phase/terminal enums, generation and repair/rerun counters, pending-HITL descriptor, consumed response ids, and deterministic Wave branch reducers; cover duplicate branch ids, unbounded trace/counter input, raw authority fields, and unknown schema versions (`REG-002`, `REG-003`, `REG-004`, `REG-005`).
- [ ] 2.2 Implement the pure domain skeleton contracts under `agent/src/deerflow_deep_research/domain/` with no IO or outer-layer imports, excluding user identity, host paths, sandbox/AppConfig/checkpoint objects, source bodies, evidence, ledger, and report data; annotate the owning surfaces with `@impl REG-002`, `@impl REG-003`, `@impl REG-004`, and `@impl REG-005` (`REG-002`..`REG-005`).
- [ ] 2.3 Add red tests for the frozen non-checkpointed invocation-context contract and per-node dependency lookup, including missing node, wrong logical name, mutable mapping, and capability/context authority leakage (`REG-001`, `RUI-006`).
- [ ] 2.4 Implement the domain-owned reduced invocation context used by LangGraph `context_schema`, keeping concrete runtime binding outside graph state and preserving the existing NodeBuildDependencies boundary (`REG-001`, `RUI-006`).

## 3. Explicit Topology And Implementation Selection

- [ ] 3.1 Add red graph-contract tests for the eleven stable logical node names, normalized edge/route representation, START/terminal reachability, no duplicate/unreachable node, no implicit filesystem discovery, and no internal component exposed as a top-level phase (`REG-001`, `REG-005`).
- [ ] 3.2 Implement `graph/topology.py` as the single normalized node/edge truth and `graph/routing.py` as pure typed-verdict routers; annotate the topology owner with `@impl REG-001` and snapshot owner with `@impl REG-005` (`REG-001`, `REG-005`).
- [ ] 3.3 Add red implementation-map tests for full-fake resolution, explicit mixed test overrides, unknown node/mode, incomplete map, unavailable real implementation, duplicate logical NodeSpec, and prohibition on silent real-to-fake fallback (`REG-001`).
- [ ] 3.4 Implement `graph/implementation_map.py` and extend the explicit registry/builder surface so every logical node resolves once from its package-root `NODE_SPEC`; fail before checkpoint invocation when real implementation is unavailable and annotate the owner with `@impl REG-001` (`REG-001`).

## 4. Canonical Node Packages

- [ ] 4.1 Add red package-shape and contract tests for `bootstrap`, `hitl1`, and `topic_planning`, including package-root-only `NODE_SPEC`, private contracts, deterministic fake factory, fail-closed real factory, and forbidden imports (`REG-001`, `REG-002`).
- [ ] 4.2 Implement the three packages with typed fixture inputs/results and bounded logical trace updates; do not call agent capabilities or IO (`REG-001`, `REG-002`).
- [ ] 4.3 Add red package-shape and contract tests for `wave0` and `wave1`, including their optional phase-local subgraph ownership and no sibling-node imports (`REG-001`, `REG-002`).
- [ ] 4.4 Implement the Wave package roots, typed contracts, fake entry factories, fail-closed real factories, and subgraph modules without exposing dispatch/join workers as top-level nodes (`REG-001`, `REG-002`).
- [ ] 4.5 Add red package-shape and contract tests for `wave2_synthesis`, `targeted_evidence`, and `hitl2`, including typed targeted-repair and HITL2 decision outputs (`REG-001`, `REG-002`, `REG-003`).
- [ ] 4.6 Implement those three packages with fixture-only fake behavior and no sandbox/model access (`REG-001`, `REG-002`, `REG-003`).
- [ ] 4.7 Add red package-shape and contract tests for `rerun`, `readiness`, and `final_delivery`, including generation increment, bounded readiness repair, and typed completed/stopped/cancelled terminal outcomes (`REG-001`, `REG-002`, `REG-004`).
- [ ] 4.8 Implement the final three packages with deterministic fake behavior and explicit unavailable-real errors (`REG-001`, `REG-002`, `REG-004`).

## 5. Deterministic Send Fan-Out And Fan-In

- [ ] 5.1 Add red Wave0 phase-subgraph tests that dispatch exactly three public LangGraph `Send` tasks, complete them in permuted order, reduce each unique branch once, reject duplicate/unknown branch ids, and join into one normalized parent result (`REG-002`).
- [ ] 5.2 Implement the Wave0 dispatcher/worker/join subgraph with deterministic fixture results and no persistent subgraph checkpointer; annotate the owner with `@impl REG-002` (`REG-002`).
- [ ] 5.3 Add the equivalent red tests for Wave1, including stable output across scheduler ordering and no advance before all three branches join (`REG-002`).
- [ ] 5.4 Implement the Wave1 phase-local Send/reducer/join subgraph and keep every internal component out of the top-level topology (`REG-002`).
- [ ] 5.5 Add spy-backed tests proving full-fake Wave execution never invokes a model, web/MCP/ACP tool, DeerFlow `task` subagent, node-agent capability, or sandbox research tool and writes no research artifact (`REG-002`).

## 6. Research Graph Recipe And Routing

- [ ] 6.1 Add red graph tests for the happy route, Wave0 repair then pass, Wave2 targeted-evidence repair, readiness repair, HITL2 rerun to a second generation, HITL2 stop, and bounded-counter exhaustion; assert routers read typed fields rather than free-form text (`REG-001`, `REG-002`, `REG-004`).
- [ ] 6.2 Implement the request-independent StateGraph recipe with the reduced `context_schema`, node wrappers that bind the selected NodeSpec factory at execution time, all approved edges, and no runtime authority in state; annotate the builder with `@impl REG-001` and route enforcement with `@impl REG-002` (`REG-001`, `REG-002`).
- [ ] 6.3 Add red mixed-map tests that replace one fake with an explicit test real implementation while preserving the identical topology/snapshot and refusing a production real selection whose owner is absent (`REG-001`).

## 7. HITL Interrupt And HumanMessage Correlation

- [ ] 7.1 Add red unit/graph tests for stable HITL1/HITL2 request ids, version-1 request payloads, checkpoint-before-return ordering, source `deep_research`, free-text/choice modes, and repeat projection replacing rather than duplicating the same outer ToolMessage (`REG-003`).
- [ ] 7.2 Implement graph-owned `interrupt()` calls plus runtime projection to the outer `Command`/`ToolMessage` contract using `ToolRuntime.tool_call_id`; annotate the bridge owner with `@impl REG-003` (`REG-003`, `RUI-006`).
- [ ] 7.3 Add red latest-HumanMessage selection tests for matching structured card response, plain visible client response, content blocks, post-suspension cursor ordering, empty value, wrong source/request id, hidden summary/dynamic context, AI/ToolMessage, pre-suspension message, duplicate message id, and model-supplied answer argument (`REG-003`, `REG-004`).
- [ ] 7.4 Implement runtime-owned response extraction using the latest eligible trusted-state HumanMessage only, require structured correlation when metadata exists, record consumed request/message ids, and pass the accepted value through `Command(resume=...)`; annotate the owner with `@impl REG-003` (`REG-003`).
- [ ] 7.5 Add fault-injection tests for failure after nested checkpoint but before outer ToolMessage return, retry projection with stable ids, and process restart immediately before resume (`REG-003`, `REG-005`).

## 8. Lifecycle Handlers And Namespace Semantics

- [ ] 8.1 Add red action-input tests for server-generated research ids with at least 128 bits of URL-safe entropy, action-specific probe/research id rules, forbidden answer/authority fields, redacted unknown actions, and no adapter access for unavailable/schema-invalid dispatch (`RUI-001`, `RUI-006`, `REG-004`).
- [ ] 8.2 Extend the strict reflected tool schema and dispatch result/Command normalization for `infra_probe | start | resume | status | cancel` without changing the reflection path; annotate the tool owner with `@impl RUI-006` (`RUI-001`, `RUI-006`).
- [ ] 8.3 Add red namespace and handler tests for start-new, duplicate start, read-only status, pending-only resume, completed resume, wrong user/thread, missing research id, unsupported schema, and infra-probe/research namespace separation (`RUI-003`, `RUI-004`, `RUI-006`, `REG-004`, `REG-005`).
- [ ] 8.4 Implement the four research ActionHandlers, shared trusted namespace derivation, runtime projection, state inspection, and typed redacted results while keeping SQL provider lifetime per action; annotate owners with `@impl REG-004`, `@impl REG-005`, and `@impl RUI-006` (`RUI-003`, `RUI-004`, `RUI-006`, `REG-004`, `REG-005`).
- [ ] 8.5 Add red cancel tests for suspended cancellation through an internal resume decision, repeated terminal idempotency, stopped/completed behavior, same-namespace lock serialization, and explicit non-claim of active cross-worker preemption (`REG-004`, `RUI-006`).
- [ ] 8.6 Implement cancel as a normal graph transition rather than raw checkpoint rewriting and preserve ordinary outer asyncio cancellation propagation/cleanup for actively executing actions (`REG-004`, `RUI-004`).

## 9. Topology Snapshot And Structural Governance

- [ ] 9.1 Add a red semantic snapshot/diagram test covering normalized logical nodes, labelled edges, terminal reachability, and exclusion of phase-local Wave components; make formatting-only ordering changes deterministic (`REG-001`, `REG-005`).
- [ ] 9.2 Generate and commit the topology snapshot/diagram from the normalized topology and document the regeneration command; annotate the generator or snapshot owner with `@impl REG-005` (`REG-005`).
- [ ] 9.3 Update `openspec/governance/project-structure.toml` with the new current topology/routing/implementation-map/skeleton/lifecycle and eleven node-package paths, regenerate the bounded `agent/AGENTS.md` structure block, update governance fixtures, and keep the existing node-package grammar unchanged (`PRS-001`, `PRS-003`, `PRS-004`, `REG-001`).
- [ ] 9.4 Run the architecture checker against valid and malformed new-node fixtures and require no unowned structural drift or forbidden dependency edge (`PRS-002`, `PRS-003`, `PRS-004`).

## 10. Zero-API End-To-End And Restart Recovery

- [ ] 10.1 Add a full public-surface memory E2E for start -> HITL1 response -> HITL2 approve -> readiness -> final, asserting two stable human-input messages, same-process host reuse, typed completed result, and no external calls (`REG-002`..`REG-005`, `RUI-006`).
- [ ] 10.2 Add public-surface E2E fixtures for Wave0 repair, HITL2 rerun to generation two, HITL2 stop, cancel, wrong-thread access, stale request id, duplicate response replay, completed resume, and status read-only behavior (`REG-002`..`REG-005`).
- [ ] 10.3 Add a subprocess fixture that starts to HITL on file-SQLite, exits after provider closure, then resumes in a fresh process from the matching HumanMessage; verify the same research namespace is recovered and outer/probe checkpoints remain untouched (`REG-003`, `REG-005`, `RUI-003`, `RUI-004`).
- [ ] 10.4 Run the environment-appropriate infra probe before and after fake lifecycle actions on the retained memory host and file-SQLite provider, proving probe visit semantics and research isolation remain green (`RUI-001`, `RUI-004`, `RUI-005`, `RUI-006`).
- [ ] 10.5 Assert memory and SQLite memory mode report same-process only, file-SQLite reports restart durable, and no test or documentation claims Postgres, Docker live smoke, multi-worker coordination, or cross-worker cancellation (`REG-005`).

## 11. Entry Guidance, Diagnostics, And Documentation

- [ ] 11.1 Add red public-skill and Agent/SOUL replay tests showing a research request calls `start`, a matching user reply calls `resume` with only the research id, status/cancel are described accurately, and the entry text does not contain topology, phase prompts, fake fixture controls, authority claims, or answer payload instructions (`RUI-006`, `REG-003`, `REG-004`).
- [ ] 11.2 Update the committed public skill and Agent/SOUL guidance, materialize/check it through the existing configurator fixtures, and preserve the same config tool/group/reflection and extensions enabled-state entries; changes take effect on next agent build (`RUI-006`).
- [ ] 11.3 Extend doctor/reflection tests only as needed to recognize the expanded action description and combined host while proving no startup-only config, mount, provider, sandbox, worker-count, launcher, or restart rule changes (`RUI-006`, `DEC-005`).
- [ ] 11.4 Synchronize `agent/README.md`, human-authored `agent/AGENTS.md`, the 01/master plans, topology regeneration docs, and OpenSpec traceability; keep deferred launcher/Docker/Postgres work out of this change (`REG-001`..`REG-005`, `RUI-006`, `PRS-004`).

## 12. Final Verification And Archive Gates

- [ ] 12.1 Run `make -C agent lock-check`, `make -C agent format`, `make -C agent lint`, the complete agent-owned zero-API test suite, the reflected-command viability gate, the file-SQLite restart E2E, and agent-scoped blocking-IO checks; require no real LLM/network call and record skips honestly (`RUI-006`, `REG-001`..`REG-005`).
- [ ] 12.2 Run isolated `configure.py --check`/materialization parity and doctor checks, verifying the public skill/Agent updates are next-agent-build only and the existing startup fingerprint/provider/mount contract is unchanged (`DEC-002`..`DEC-005`, `RUI-006`).
- [ ] 12.3 Run `python3 openspec/governance/check_project_architecture.py` and require the registry, generated guide block, current paths, import boundaries, and all node packages to conform (`PRS-001`..`PRS-004`, `REG-001`).
- [ ] 12.4 Run `python3 openspec/governance/check_project_reqs.py` and require zero duplicate, unregistered, orphan, and reused-retired IDs (`RUI-006`, `REG-001`..`REG-005`).
- [ ] 12.5 Run `python3 openspec/governance/check_project_specs.py` and require zero main-spec structure violations (`RUI-006`, `REG-001`..`REG-005`).
- [ ] 12.6 Run `openspec validate build-deep-research-fake-graph-skeleton --type change --strict`, resolve every schema/scenario error, verify every new requirement has task coverage plus an owning `@impl` annotation, and confirm no files under `backend/` or `frontend/` changed (`RUI-006`, `REG-001`..`REG-005`).
