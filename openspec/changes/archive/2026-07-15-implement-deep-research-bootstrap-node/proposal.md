## Why

The bootstrap node is still the change-01 fake: it selects its route from a fixture
sequence, and no bootstrap-owned step explicitly establishes the research bundle — sandbox
directories appear only lazily as a side-effect of later writes. Every later real phase
(HITL1, topic planning, the research waves) depends on a bootstrap that has
*actually* established the research bundle — an atomically created directory, a
schema/version marker, and a verified binding between the checkpointed control state and
the on-disk bundle — before any research work begins. Without a real bootstrap, a crash
between directory creation and checkpoint publication can leave a partial bundle that later
nodes mistake for an active research, and there is no deterministic point that refuses a
start whose bundle, state, and checkpoint disagree. This change upgrades only the bootstrap
node to real; identity derivation and start/resume/status/cancel semantics are unchanged.

## What Changes

- Replace the fake bootstrap route selection (`choose_fixture`) with a real bootstrap that
  atomically establishes the minimal research bundle directory tree (`request/` only) and
  writes a schema/version marker at `bundle_root/request/marker.json`, reusing the
  shared-workspace capability proven by change 04 (bounded POSIX lock, same-directory
  replace, durability sync). A partially created directory is cleaned up and recovered before
  any route is published, so it can never be observed as an active or completed bundle.
- Add a real bootstrap validation (the "gate" that replaces the fake fixture pass), built on
  gate-kernel failure codes, that verifies the on-disk marker is bound to the checkpointed
  control state — research_id, start_message_id, request_digest, and schema/version — and
  determines the bootstrap route from that validation. The bootstrap node stays non-gated
  and performs no research model call; the filesystem side-effect (directory + marker) is
  performed by the node through an injected runtime capability, and a pure binding check
  compares the marker to the checkpoint.
- On bootstrap failure or partial-directory state, perform deterministic cleanup and bounded
  retry with typed failure codes; never invoke a research LLM and never publish an
  inconsistent bundle or route. Unrecoverable failure (unsupported schema, identity
  mismatch, unavailable workspace) fails closed to a terminal lifecycle.
- Distinguish new start, duplicate same-message start, concurrent start, and an
  already-terminal same-thread research with typed lifecycle codes, with path/user/thread
  isolation and schema-mismatch rejection, and without cross-research interference. These
  transitions remain owned by the existing lifecycle handler; this change adds the
  bundle-level binding the bootstrap gate reads.
- Swap the real bootstrap into the mixed implementation map in place of the fake while every
  other phase remains fake, preserving the normalized topology and the full-fake lifecycle
  end-to-end path. The lifecycle result remains `implementation_mode=full_fake` because
  bootstrap produces no research findings or report.
- `backend/` and `frontend/` are not modified.

## Capabilities

### New Capabilities

- `bootstrap-node`: Real bootstrap node behavior — atomic minimal bundle directory
  establishment with a schema/version marker and partial-directory recovery, a real bootstrap
  binding-validation (built on gate-kernel failure codes) that verifies the on-disk marker
  against the checkpoint and determines the route replacing the fake fixture pass,
  deterministic failure cleanup/retry with no research LLM, same-thread active/completed
  edge-case handling, and mixed-graph integration with the rest of the graph fake.
  Requirement IDs: BON-001 through BON-005.

### Modified Capabilities

None. The new supporting files are registered in the canonical project-structure registry
and the generated `agent/AGENTS.md` block through the existing PRS-004 mechanical sync; no
`project-structure`, `research-graph-lifecycle`, `gate-kernel`, or `work-unit-kernel`
requirement text changes. Identity derivation and start/resume/status/cancel semantics
(REG-004), the bundle layout and path-containment contract (REG-010), the gate-kernel
invariants (GAK-001..006), and the implementation map (REG-001) are unchanged.

## Impact

- **Source:** add a runtime-owned bundle establishment capability under
  `agent/src/deerflow_deep_research/runtime/bootstrap_bundle.py` (reusing the change-04
  shared-workspace probe, POSIX lock, atomic replace, and durability sync) and a pure marker
  contract plus `BootstrapBundleStoreProtocol` and a pure binding-validation helper under
  `agent/src/deerflow_deep_research/domain/bootstrap.py`; replace the
  `UNAVAILABLE_REAL_FACTORY` sentinel in `graph/nodes/bootstrap/node.py` with the real factory
  and extend `graph/nodes/bootstrap/contracts.py` with the bootstrap binding/marker contract;
  add a `NodeCapability.BOOTSTRAP_BUNDLE` and a `bootstrap_bundle` slot to
  `NodeBuildDependencies`/`GraphInvocationContext` and a declare/forbid branch in the graph
  node wrapper; wire the store through the runtime dependency resolver for start/resume. The
  new files are registered in the canonical project-structure registry and the generated
  `agent/AGENTS.md` block via the existing PRS-004 mechanical sync. No second bundle, ledger,
  submit, or route authority is introduced.
- **Typed state/checkpoint data affected:** none. The bootstrap binding is validated, not
  stored: `research_id`, `start_message_id`, `request_digest`, `schema_version`, `phase`,
  and `generation` already exist on `ResearchState`/`ResearchCheckpoint` and are the binding
  the gate reads. No new checkpointed field is added, `RESEARCH_STATE_SCHEMA_VERSION` is not
  bumped, and existing version-2 checkpoints remain readable. Large content still never
  enters the checkpoint.
- **Graph nodes/components affected:** only `bootstrap` swaps from fake to real in the mixed
  graph; every other phase remains fake. Bootstrap remains a non-gated control node; the real
  node performs atomic bundle establishment, runs a pure binding-validation (reusing
  gate-kernel failure codes) that replaces the fake fixture pass, and sets the route directly.
  The top-level topology gains one terminal edge from bootstrap (`exhausted → END` in the
  builder, `bootstrap --exhausted--> blocked` in the canonical `NORMALIZED_EDGES`) so an
  unrecoverable binding failure fails closed instead of routing onward. The normalized node
  order and every other conditional edge are unchanged. Targeted evidence and rerun are not
  implemented here.
- **Node-agent roles used:** bootstrap is a deterministic control node. It performs no
  `run_agent` call and no model, web, MCP, ACP, or DeerFlow `task` subagent call; it uses
  only an injected runtime bundle-establishment capability plus a pure binding-validation.
  Planners, workers, and repair roles are unchanged. Agents cannot write the bundle marker,
  the route, or phase/gate state.
- **Sandbox artifacts read/written:** the bootstrap node writes the minimal
  `workspace/deep-research/<research_id>/` directory tree and a schema/version marker under
  the canonical `request` subtree, and reads the marker back for binding validation. No
  evidence ledger, work-spec, result, or DPT queue/index/status bundle file is created. No
  `rb_status.json` phase cursor is added.
- **DeerFlow extension surfaces:** the existing downstream reflection path
  `deerflow_deep_research.tool:deep_research_tool` and registered lifecycle handlers are
  unchanged. No `config.yaml` section, `extensions_config.json` key, public/custom skill,
  per-user Agent/SOUL, MCP, ACP, or lead-agent middleware surface is added or modified.
- **Diagnostics:** no new `ReadinessDiagnostic` dimension. Bootstrap reuses the change-04
  `work_unit_storage` readiness classification for the shared-workspace capability it
  depends on; an unsupported provider fails closed through the existing path before the
  bootstrap node runs.
- **Reload boundary:** no runtime configuration, mount, or
  `reload_boundary.STARTUP_ONLY_FIELDS` value changes. Source changes are available on the
  next agent build; a running non-reload Gateway must be restarted/redeployed to import new
  Python source, but there is no additional configuration-mandated restart.
- **Dependencies:** no new third-party runtime dependency; filesystem serialization uses
  platform/stdlib primitives on the verified mounted-workspace local/default-Docker paths
  already proven by change 04. Provisioner/remote/non-mounted sandbox modes fail closed in
  this version.
- **Non-goals:** no topic rewrite, profile derivation, or user questioning; no real research
  worker, source fetching, findings, or report generation; no DPT `rb_status.json` phase
  cursor; no second submit/ledger/retry/drain authority. No files under `backend/` or
  `frontend/` are modified.

New requirement IDs are BON-001 through BON-005 (`bootstrap-node`). No existing requirement
is modified; the new supporting files are registered through the existing PRS-004 registry
sync.
