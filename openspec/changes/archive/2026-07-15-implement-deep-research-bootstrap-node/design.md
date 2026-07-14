## Context

The bootstrap node is the first node every Deep Research run enters (`builder.py: START -> bootstrap`).
Today it is the change-01 fake: `graph/nodes/bootstrap/fake.py` calls
`choose_fixture(state, "bootstrap")` and emits a route (`needs_input` or `profile_complete`)
through `node_update`. `graph/nodes/bootstrap/node.py` is the `UNAVAILABLE_REAL_FACTORY`
sentinel, so the mixed implementation map (`graph/implementation_map.py`) refuses
`mode="real"` for bootstrap with `implementation_unavailable`.

Verified current behavior (from source, not the plan):

- **Identity and start semantics already live in the runtime layer.**
  `runtime/research.py:derive_research_id` derives the domain-separated `r_<43>` research id
  from `effective_user_id` + `outer_thread_id`; `digest_request` derives the `d_<43>` request
  digest. `StartResearchHandler.execute` enforces start idempotency (same `start_message_id`
  + `request_digest` resumes the same lifecycle) and conflict detection (different message or
  digest on an existing checkpoint → `THREAD_RESEARCH_EXISTS`). These are owned by REG-004 and
  are NOT redesigned here.
- **No bootstrap-owned bundle establishment exists.** Verified by tracing
  `StartResearchHandler.execute` → `WorkUnitStore.create` → `verify_runtime_work_unit_storage`:
  the only `mkdir` on the start path is `runtime/work_unit_storage.py:209`
  (`diagnostics.mkdir(parents=True, exist_ok=True)`), which the verifier creates *ephemerally*
  and removes in its `finally` block; `runtime/work_unit_store.py:146` (`_open_directory`) is
  lazy, triggered by later work-unit writes, not during start. The bootstrap node performs no
  filesystem I/O today. The plan's "01 fake is a non-atomic simple mkdir" is the approved
  target, not the current code.
- **Bootstrap is non-gated.** `engine/gate_fixtures.py:build_fixture_gate_defs` explicitly
  excludes bootstrap ("Non-gated nodes: bootstrap, ..."); `engine/fake_control.choose_fixture`
  sets the bootstrap route directly. `graph/builder.py:_node_wrapper` runs the gate only when
  `gate_defs.get(logical_name)` is present, and for non-work-unit nodes it feeds the gate the
  *incoming* checkpoint state (not the node's result).
- **The gate kernel is pure.** `engine/gate_kernel.evaluate_gate` performs no I/O and no
  mutation (GAK-006); `domain/failure_codes.py` is a closed typed registry (GAK-002). GAK-003
  makes the gate the sole writer of `route` for gated phases.
- **Bundle paths are owned by `domain/bundle.py`.** `bundle_root(research_id)` =
  `workspace/deep-research/<research_id>`; `REQUEST_SUBTREE = "request"` is reserved but
  unused. Path containment is enforced by `resolve_contained_path`.
- **Node capability injection follows one pattern.** `NodeBuildDependencies` carries
  `graph_context` (a frozen `GraphContextView` with a *virtual* `workspace_root`), `capabilities`
  (the `NodeExecutionCapabilities` agent bridge), and an optional `work_units`
  (`WorkUnitControllerDependencies`). `GraphInvocationContext` holds the per-invoke store;
  `_node_wrapper` attaches `work_units` only for nodes declaring
  `NodeCapability.WORK_UNIT_CONTROLLER`. The runtime-owned `WorkUnitStore`
  (`runtime/work_unit_store.py`) is the only thing that translates the virtual root to a real
  host/sandbox path and performs POSIX-locked, atomic-replace, fsync'd file I/O (change 04).

Constraints: `backend/` and `frontend/` are untouched; new code lives under `agent/`; blocking
file I/O stays off the event loop (`asyncio.to_thread`); no new third-party dependency; the
lifecycle result stays `implementation_mode=full_fake` (no findings/report).

## Goals / Non-Goals

**Goals:**

- Replace the fake bootstrap route selection with a real bootstrap that atomically establishes
  the minimal research bundle directory tree and a schema/version marker, with
  partial-directory recovery.
- Add a real bootstrap validation (the "gate" that replaces the fixture pass) that verifies the
  on-disk marker is bound to the checkpointed control state, and determines the route from that
  validation — with no research LLM.
- Make unrecoverable bootstrap failure fail closed to a terminal lifecycle; make recoverable
  failure deterministic cleanup + bounded retry.
- Let the mixed implementation map select the real bootstrap while every other phase stays
  fake, preserving the normalized topology and the full-fake end-to-end path.
- Reuse the change-04 shared-workspace capability (probe + POSIX lock + atomic replace + fsync)
  rather than introduce a second filesystem authority.

**Non-Goals:**

- No topic rewrite, profile derivation, or user questioning (HITL1/change 06 owns ask-vs-proceed).
- No redesign of identity derivation, start idempotency, or conflict detection (REG-004).
- No new checkpointed state field and no `RESEARCH_STATE_SCHEMA_VERSION` bump; the binding is
  validated, not stored.
- No DPT `rb_status.json` phase cursor; no evidence ledger, work-spec, or submit path changes.
- No real research worker, source fetching, findings, or report generation.
- No `backend/` or `frontend/` modification.

## Decisions

### D1: Bootstrap stays non-gated; the node owns establishment, validation, and route

The real bootstrap node (`build_real`) performs establishment + binding validation + route
selection itself, exactly as the fake bootstrap owns its route today. It does **not** register
a `GateDefinition` and is not added to `default_gate_defs()`.

**Rationale.** Bootstrap is structurally a non-gated control node, not a gated validation
phase. The graph has two route patterns: gated phases (wave0, wave1, wave2_synthesis,
readiness, final_delivery) own repair loops and receive their route from `evaluate_gate` via
a registered `GateDefinition`; non-gated control nodes (bootstrap, hitl1, topic_planning,
targeted_evidence, hitl2, rerun) set their route directly. Bootstrap has no repair loop and
routes into `hitl1`, so it belongs in the non-gated control-node set with its peers — making
it real does not change which set it is in. On top of that, the plan's "bootstrap gate
validates the directory, state, and checkpoint/bundle binding" requires reading the on-disk
marker — filesystem I/O — and the gate kernel is pure (GAK-006) with `_node_wrapper` feeding
non-work-unit nodes only their *incoming* state, so a registered gate could not observe the
marker the node just wrote; the pure portion (checkpoint field consistency) is already
enforced by `ResearchCheckpoint.__post_init__`. The real validation therefore lives in the
node (which has the injected filesystem capability), reusing gate-kernel `FailureCode`/
`Failure` types, and sets the route directly — exactly the non-gated pattern.

**"Depends on the gate kernel" is honored by reuse, not registration.** The bootstrap
validation produces typed `Failure` objects with `FailureCode` values from the closed registry
(GAK-002), uses the gate-kernel failure classifications, and is a pure function over
(marker, checkpoint) that performs no I/O and no mutation (GAK-006 style). The node calls it
after the filesystem probe. Terminal fail-closed mirrors the gate kernel's BLOCKED→terminal
behavior.

**Alternatives considered.** (a) Register a bootstrap `GateDefinition` whose pure rules
validate the *incoming checkpoint state*. Rejected: the gate cannot see the on-disk marker
(the node writes it during the same step), so it could not perform the directory/binding
validation the plan requires; it would only re-check fields already enforced by
`ResearchCheckpoint.__post_init__`. (b) Make bootstrap genuinely gated via a bootstrap
gate-view — a `BootstrapGateView` the node returns, the wrapper pops/validates/injects, and a
`GateDefinition` reads (the work-unit `WorkUnitGateView` pattern applied to bootstrap).
Rejected as disproportionate: `WorkUnitGateView` is a rich, work-unit-*component*-shaped
structure with extensive cross-validation, built for the nested work-unit subgraph's complex
state; standing up a *second* gate-view machinery in `_node_wrapper` (new view type + key +
wrapper branch + `GateDefinition` + registration) for a single marker↔checkpoint comparison
is heavier than the check warrants and sets a precedent of per-capability gate-view branches.
The non-gated node-level validation delivers the plan's required validation (directory marker
+ state + binding, replacing the fixture pass, depending on the gate kernel via `FailureCode`)
without that cost. The gated set is reserved for validation phases with repair loops; bootstrap
is not one, so the non-gated route is the structurally correct home, not merely the lighter one.

**GAK-003 note.** GAK-003's "gate is the sole writer of route" applies to gated phases. The
fake bootstrap already writes `route` directly (non-gated); the real bootstrap continues this
non-gated pattern. No gated phase loses its gate-owned route.

### D2: Route outcomes are `needs_input` (success) or `exhausted` (terminal); never `profile_complete` from the real bootstrap

On successful establishment + binding validation, the real bootstrap routes `needs_input` →
`hitl1`, handing the bound original request and research identity to HITL1 (change 06), which
decides whether to ask or proceed. The real bootstrap does not derive profile completeness
(non-goal), so it never emits `profile_complete`; that label remains reachable only via the
fake fixture plan (full-fake mode). On unrecoverable failure the node sets
`phase_status=TERMINAL`, `terminal_status=BLOCKED`, `terminal_reason=GATE_BLOCKED` and routes
`exhausted`. The topology gains one edge — `bootstrap --exhausted--> END` — reusing the
existing `exhausted` label already in `_KNOWN_ROUTE_LABELS`. The `exhausted` label is reused
deliberately: it is the established terminal→`END` label used by the wave/readiness/final
fail-closed routes, so bootstrap's terminal fail-closed routes consistently with them; the
*cause* (establishment or binding failure) is recorded in `terminal_reason` (`GATE_BLOCKED`),
not in the route label. Every other conditional edge and the normalized node order are unchanged.
The terminal edge is added in both topology representations: `graph/builder.py` maps
`exhausted → END` (the LangGraph sink) and `graph/topology.py:NORMALIZED_EDGES` records
`bootstrap --exhausted--> blocked` (the semantic terminal in `TERMINALS`, matching every other
phase's `exhausted` target); the rendered topology snapshot is regenerated.

### D3: Atomic establishment via a new runtime `BootstrapBundleStore` that reuses the change-04 shared-workspace capability

A new `runtime/bootstrap_bundle.py` owns `BootstrapBundleStore`, the sole writer of the bundle
directory tree and marker. It reuses the change-04 workspace probe
(`runtime/work_unit_storage.py`) so it fails closed with `work_unit_storage_unavailable` on an
unsupported provider before any write, and reuses the same POSIX-lock + same-directory-replace
+ fsync primitives as `WorkUnitStore`. Like `WorkUnitStore.create`, `BootstrapBundleStore.create`
calls `verify_runtime_work_unit_storage` to confirm the shared-workspace capability before
establishing; this ephemeral probe is idempotent and may run alongside the work-unit store's
own probe in `_context` — both confirm readiness independently and leave no persistent
artifact. Establishment is atomic: the minimal tree (`request/` only; all other subtrees
remain lazy, created by later phases as today) and the marker are written under the
research-scoped lock, and a partial creation is cleaned up and retried internally (bounded)
before the method returns. The store derives the real bundle root from
`TrustedRuntimeEnvelope.workspace_host_path` (the same source `WorkUnitStore` uses) and
translates the virtual `workspace_root`; the node never sees a real path.

**Marker contract** (frozen `BootstrapMarker` in `domain/bootstrap.py`; path helper
`marker_path(research_id)` → `workspace/deep-research/<research_id>/request/marker.json`,
added to `domain/bundle.py` alongside the existing `REQUEST_SUBTREE`): a versioned JSON
`{"schema_version": 1, "research_id": "r_…", "start_message_id": "…", "request_digest": "d_…", "state_schema_version": 2}`,
written under the canonical `request/` subtree. `request_digest` is the authoritative digest
of the latest `HumanMessage` text — the start message is the sole question authority and tool
payloads cannot supply a question — bound via the checkpoint. The marker is explicitly not a
DPT `rb_status.json` phase cursor and carries no phase/generation program counter; `generation`
remains owned by the checkpoint (REG-006) and the real bootstrap does not increment it.

**Alternative considered: reuse `WorkUnitStore` directly.** Rejected because the work-unit
store is the evidence-ledger authority; folding bundle-directory lifecycle into it would
conflate two authorities and muddy the ledger's invariants. **Alternative considered:
establish the bundle in `StartResearchHandler` before `ainvoke`.** Rejected because the plan
scopes the replacement to the bootstrap node, and establishment belongs with the node that
validates and routes on it.

### D4: Inject the store through a new `NodeCapability.BOOTSTRAP_BUNDLE`, mirroring the work-unit pattern

To give the non-agent bootstrap node a filesystem capability without widening
`NodeExecutionCapabilities` (which is the agent bridge) or hardcoding bootstrap in the
resolver, this change adds the minimal general mechanism, exactly parallel to work units:

- `domain/node_spec.py`: add `NodeCapability.BOOTSTRAP_BUNDLE = "bootstrap_bundle"`.
- `domain/bootstrap.py` (new): the frozen marker contract and a runtime-checkable
  `BootstrapBundleStoreProtocol` (`establish_bundle`, `read_marker`).
- `domain/invocation.py`: add `bootstrap_bundle: BootstrapBundleStoreProtocol | None = None`
  to `GraphInvocationContext`.
- `domain/node_spec.py:NodeBuildDependencies`: add `bootstrap_bundle: BootstrapBundleStoreProtocol | None = None`.
- `graph/builder.py:_node_wrapper`: a branch that attaches `context.bootstrap_bundle` for
  nodes declaring `BOOTSTRAP_BUNDLE` and forbids it otherwise (mirroring the
  `declares_work_units` checks).
- `graph/nodes/bootstrap/__init__.py`: `NODE_SPEC.capabilities = frozenset({NodeCapability.BOOTSTRAP_BUNDLE})`.
- `runtime/research.py:ResearchActionHandler._context`: construct `BootstrapBundleStore` for
  start/resume and set it on `GraphInvocationContext`; `include_work_units=False` path
  (status/cancel) also excludes the bootstrap store, so both remain checkpoint-only.

**Alternative considered: extend `NodeExecutionCapabilities` with an `establish_bundle`
method.** Rejected because that protocol is the per-node agent bridge and every node's
capabilities would have to implement it. **Alternative considered: construct the store inside
`RuntimeNodeDependencyResolver.resolve` for `logical_name=="bootstrap"`.** Rejected because it
hardcodes a node name in the resolver; the `NodeCapability` mechanism is the general pattern
already used for work units.

### D5: No new checkpoint field; the binding is validated, not stored

The marker lives in the sandbox; the checkpoint already carries `research_id`,
`start_message_id`, `request_digest`, `schema_version`, `phase`, and `generation`. The
bootstrap validation compares the marker to these existing fields. No new `ResearchState` field
is added, `RESEARCH_STATE_SCHEMA_VERSION` stays 2, and existing checkpoints remain readable
(REG-011 unchanged). This keeps the three-authority boundary clean: the marker is sandbox
content, the checkpoint is control authority, and the bootstrap validation is the deterministic
check that they agree.

### D6: Failure handling — bounded internal retry for recoverable failures; terminal fail-closed for unrecoverable

`BootstrapBundleStore.establish_bundle` is idempotent-recoverable on entry: a missing
directory, a partial tree, or a stale/existing marker that does not match the checkpoint is
cleaned up and re-established, and recoverable failures (partial directory, transient lock
contention) retry internally up to a small bound. (Bootstrap only runs on a fresh start —
`StartResearchHandler` denies a new start on a thread that already has a checkpoint — so any
pre-existing marker is stale residue of a crashed prior attempt, safe to overwrite.) The node
never invokes a research LLM. After a successful establishment the node reads the marker back
and runs the pure binding validation; a divergence *after* a fresh establish indicates
corruption (the marker was just written + fsync'd bound to this checkpoint), so it is
unrecoverable → the node sets terminal BLOCKED + `route=exhausted` → END. An unavailable
workspace surfaces as `work_unit_storage_unavailable` through the existing change-04 denial
path; status/cancel never construct the store and remain checkpoint-only.

### D7: Edge cases remain owned by the lifecycle handler; bootstrap adds bundle-level signals

New start, duplicate same-message start, concurrent start, and already-terminal same-thread
research are distinguished by `StartResearchHandler` (REG-004) — unchanged. The bootstrap
node adds the bundle-level signal: it refuses to proceed if the on-disk marker does not match
the checkpoint binding (path/user/thread isolation and schema-mismatch rejection happen at the
marker/checkpoint comparison). No second start-semantics authority is introduced.

## Risks / Trade-offs

- **[Injection plumbing breadth]** Adding `NodeCapability.BOOTSTRAP_BUNDLE` + context/dependency
  fields + a wrapper branch touches several modules. → Mitigation: mirror the work-unit
  pattern line-for-line; TDD each touchpoint with red-before-green; the wrapper's
  declare/forbid checks are copied from the proven `declares_work_units` checks.
- **[Non-gated route write vs GAK-003]** A strict reading of GAK-003 could read the bootstrap
  node's direct route write as a violation. → Mitigation: GAK-003 governs gated phases; the
  fake bootstrap already writes route directly. The design documents this non-gated exception
  explicitly so a future "gate everything" change would have to promote bootstrap to gated and
  solve the marker-visibility problem first.
- **[Marker filesystem I/O on the event loop]** → Mitigation: all store I/O runs through
  `asyncio.to_thread` with host-descriptor-relative cleanup, exactly like `WorkUnitStore`.
- **[Workspace unavailable mid-run]** If the workspace becomes unavailable after start but
  during bootstrap, the store raises `work_unit_storage_unavailable`. → Mitigation: the handler
  surfaces it as a denial; the store is constructed in `_context` (not status/cancel), so
  status/cancel stay checkpoint-only and cancellation still works during an outage.
- **[Partial directory observed as active]** A crash between subtree creation and marker write
  could leave a partial bundle. → Mitigation: establishment is under the research-scoped lock
  and the marker is written last via atomic replace; a recovery pass on re-entry detects a
  missing/mismatched marker, cleans the partial tree, and re-establishes before routing.
- **[Topology edge addition]** Adding a bootstrap terminal edge touches two synchronized
  representations (`builder.py` and `topology.py:NORMALIZED_EDGES`) plus the rendered snapshot
  doc. → Mitigation: the edge reuses the existing `exhausted` label and `blocked` terminal used
  by every other phase; `test_topology_unchanged` uses membership assertions (not exact-set
  equality), `test_explicit_mixed_override_preserves_identical_graph_shape` compares mixed vs
  fake (both gain the edge, so still equal), and the `test_topology_snapshot` golden is
  regenerated in task 5.2; the full-fake path is unaffected (fake bootstrap never emits
  `exhausted`).

## Migration Plan

- **Deploy:** source-only change. New files (`runtime/bootstrap_bundle.py`,
  `domain/bootstrap.py`) plus edits to `domain/node_spec.py`, `domain/invocation.py`,
  `domain/bundle.py`, `graph/builder.py`, `graph/nodes/bootstrap/{__init__,node,contracts}.py`,
  and `runtime/research.py` take effect on the next agent build. No `config.yaml`, `extensions_config.json`, mount, or
  `reload_boundary.STARTUP_ONLY_FIELDS` change — no Gateway restart is mandated by
  configuration (a running non-reload Gateway still must be restarted/redeployed to import new
  Python source).
- **Activate the mixed graph:** the real bootstrap is selected by setting
  `implementation_modes["bootstrap"]="real"` (others `"fake"`) in the research recipe; the
  full-fake path continues to select `"fake"` for all nodes.
- **Rollback:** revert `graph/nodes/bootstrap/node.py` to `UNAVAILABLE_REAL_FACTORY`, remove
  the new files, restore the registry/generated guide block, and drop the `exhausted` edge.
  Existing checkpoints remain valid (no schema change).

## Open Questions

- Should the marker later carry a phase/generation cursor for crash-restart introspection?
  Deferred — non-goal here; the checkpoint already owns phase/generation, and adding a cursor
  would risk duplicating control authority (REG-009).
- Should bootstrap participate in `gate_attempts_by_phase`/fatigue? No — it is non-gated and
  has no repair loop; its retry is an internal store concern, not a gate budget.
