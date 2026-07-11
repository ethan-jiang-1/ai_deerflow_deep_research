## Context

No downstream `agent/` package exists yet. DeerFlow currently registers only `lead_agent` in `backend/langgraph.json`; configured tools are reflected from `config.yaml -> tools[].use`, and the public embedded-agent factory is `deerflow.agents.create_deerflow_agent()`.

The approved roadmap maps DPT's implicit Phase-Agent/Markdown controller to an explicit nested Python `StateGraph`. Change 00 establishes only the runtime and development substrate for that graph. It must remain additive because `backend/` and `frontend/` are upstream mirrors.

Four verified constraints shape the design:

- `backend/Makefile`, root `scripts/serve.sh`, and `docker/docker-compose.yaml` launch the Gateway with an inline `PYTHONPATH=.` from `backend/`. Merely exporting another `PYTHONPATH` before invoking those commands would not load `agent/src`.
- Gateway cancellation sets a process-local run `abort_event` and cancels the outer asyncio task, but that event is not a public `ToolRuntime.context` field. The downstream tool can rely on normal `CancelledError` propagation and must verify it; it cannot read a fictional cancellation token.
- `resolve_runtime_user_id(runtime)` deliberately falls back to synthetic `default` when explicit runtime/auth context is missing. That behavior is useful to generic DeerFlow tools but is too permissive for this authority boundary; Deep Research must require the server-injected `runtime.context["user_id"]` and prove the Gateway injection path.
- `SandboxMiddleware` is lazy. On a fresh thread, `runtime.state["sandbox"]` may be absent when `deep_research` starts; the tool must call DeerFlow's public async sandbox initializer and validate the resulting parent sandbox instead of failing every first call or creating a second lifecycle.

The implementation targets Python >=3.12 and directly compatible runtime floors `deerflow-harness>=2.1.0,<2.2`, `langchain>=1.2.15`, `langgraph>=1.1.9`, and `pydantic>=2.12.5`. The independent project commits `agent/uv.lock`. Its operations extra uses `ruamel.yaml>=0.18,<0.19` for comment-preserving config edits; that extra is used by project scripts and is not required by the reflected Gateway tool. Optional SQLite/Postgres packages remain supplied by the selected DeerFlow harness extras.

## Goals / Non-Goals

**Goals:**

- Freeze one downstream source tree, import direction, node surface, and mirrored test layout before business nodes are added.
- Make the package and one `infra_probe` action loadable in local development, local production, and Docker without editing upstream source.
- Materialize runtime configuration, a public entry skill, and a per-user dedicated Agent idempotently and without treating them as security controls.
- Establish a trusted `RuntimeAdapter`, runtime-owned node execution bridge, isolated checkpoint namespace, and resource-correct `GraphHost` over DeerFlow's official checkpointer provider.
- Establish the bounded embedded-agent factory, explicit resource budgets, and fail-closed policy interfaces required by all later agentic nodes.
- Prove behavior with zero-API tests and a one-node smoke graph.

**Non-Goals:**

- No full phase topology, `ResearchState`, gate kernel, work-unit ledger, HITL flow, rerun flow, or real research node.
- No real model call, web search, evidence collection, DPT bundle control file, or final artifact publication.
- No modification under `backend/` or `frontend/`, no second registered Gateway graph, and no lead-agent middleware injection.
- No promise of restart recovery with the memory checkpointer.

## Decisions

### 1. Treat the approved mapping as the controller baseline

The downstream controller will be a nested Python `StateGraph`; node-specific Markdown remains prompt/contract material. Change 00 corrects the OpenSpec context before generating implementation tasks so later changes cannot reintroduce the superseded Phase-Agent controller.

Alternative considered: keep the lead Agent as controller and encode phase transitions in deferred skills. Rejected because it duplicates DPT's substrate rather than mapping its graph semantics onto LangGraph, makes phase/gate authority prompt-dependent, and contradicts the approved master plan.

### 1A. Freeze the handoff from change 00 to change 01

Change 00 owns runtime loading, trusted context, checkpoint/provider lifecycle, a generic typed action-handler registry, and a business-free `infra_probe`. Repeating the probe with the same opaque id proves checkpoint recovery; it is not called resume.

Change 01 owns the full fake topology, real LangGraph interrupts, outer human-input bridge, and public `start | resume | status | cancel` research protocol. It adds those typed handlers to the generic registry. Change 00 must return `action_unavailable` for unregistered research actions and must not define named lifecycle methods, a fake HITL, or a research state machine.

This boundary keeps the infrastructure probe from becoming an accidental second skeleton graph.

### 2. Own one standalone package with enforced layers

The canonical source root is `agent/src/deerflow_deep_research/`. Change 00 creates the owning layer packages and the concrete infrastructure modules it implements, and records the complete future tree in `agent/AGENTS.md`. The tree below marks later-owned packages explicitly; 00 does not create empty business-node, engine-kernel, topology, or routing packages merely to match the diagram.

```text
agent/
  AGENTS.md
  README.md
  Makefile
  pyproject.toml
  uv.lock
  src/deerflow_deep_research/
    __init__.py
    __about__.py
    tool.py
    runtime/
      graph_host.py
      runtime_adapter.py
      projection.py
      identity.py
      checkpoint.py
      events.py
      cancellation.py
      node_agent_bridge.py
      diagnostics.py
      startup_snapshot.py
    domain/
      context.py
      enums.py
      node_spec.py
    engine/
      # 03+ adds gates/, work_units/, evidence/, artifacts/ with real contracts
    agents/
      factory.py
      middleware.py
      policies.py
      prompts.py
      structured_output.py
    graph/
      builder.py
      registry.py
      infra_probe.py
      # 01+ adds topology.py, implementation_map.py, routing.py,
      # components/, and nodes/ together with executable fakes
    resources/
      node_agent/runtime_policy.md
      # shared_prompts/ is created only when two real nodes share a contract
  config/
    deerflow.fragment.yaml
    extensions.fragment.json
    agent-template/{config.yaml,SOUL.md}
    public-skill/deep-research-controller/SKILL.md
  scripts/{configure.py,prepare.py,doctor.py,serve.sh}
  docker/{docker-compose.deep-research.yaml,docker-compose.postgres-test.yaml}
  tests/{unit,contract,graph,integration,e2e,fixtures}/
```

The diagram explains the approved 00 shape but is not the durable enumerated authority after archival. Change 00 adds the following permanent chain:

```text
OpenSpec config + root/module AGENTS bootstrap pointers
                         |
                         v
openspec/governance/architecture-policy.md
  authority and synchronized-change protocol only
                         |
                         v
active project-structure main spec --normatively identifies--+
                                                              |
                                                              v
                    openspec/governance/project-structure.toml
                    exact paths/layers/import and node grammar
                                      |
                                      v
                    check_project_architecture.py
                         |                         |
                         v                         v
              repository contracts     agent/AGENTS.md controlled block
```

`openspec/governance/` is a project extension rather than an OpenSpec-native automatically loaded directory, so `openspec/config.yaml` keeps only a short bootstrap pointer and archive-gate command instead of repeating the tree. The active main spec owns the normative behavior and explicitly delegates exact enumerable structural data to `project-structure.toml`; the manifest is therefore a subordinate machine-readable registry, not a second prose architecture. `architecture-policy.md` defines this authority table, the controlled-block markers, and the update protocol, but contains no independent directory enumeration. The manifest uses repository-relative normalized paths and stable requirement-owner IDs and separates paths required in the current checkout from later package grammar; it never requires empty 01+ business packages merely to represent a future plan.

The Python 3.12 standard-library checker parses the manifest with `tomllib`, validates its schema and path containment, checks the normative owning spec reference, renders and byte-compares the bounded structural block in `agent/AGENTS.md`, and enforces the current path/layer rules against the repository. Before the first archive it accepts the one active `project-structure` delta that owns the pending requirement IDs; once a main spec exists it requires that active main spec and does not treat an archived delta as authority. Group 3 extends the same contract surface with AST import and node-package checks once those pure contracts exist. Human-authored `agent/AGENTS.md` text may explain commands, ownership rationale, and explicitly labelled future additions, but it cannot override the controlled block. Archived proposal/design/tasks remain useful history and are never needed to discover the current contract.

Every later change that adds, removes, or reassigns a structural path must update its delta spec when semantics change, update the manifest's exact enumeration, regenerate the controlled guide block, update contract fixtures, and pass the checker before archive. A change contained entirely by an existing node-package grammar still adds its current required package path to the manifest; it does not rewrite the grammar unless that contract itself changes.

Later top-level node packages have the fixed surface `__init__.py`, `node.py`, `fake.py`, and `contracts.py`, with optional phase-local `subgraph.py`, planner/worker/materializer modules, gates, and prompts. The package exports only `NODE_SPEC`; the builder never imports node internals. `graph/components/` holds reusable internal subflows and is not top-level topology.

`NodeSpec` and its pure `PolicyRef` live in `domain/node_spec.py`. Its real/fake surfaces are factories that accept pure `NodeBuildDependencies`; those dependencies expose only reduced context and `NodeExecutionCapabilities`, never raw runtime. Node packages import that contract and export a value; `graph/registry.py` loads an explicitly listed package root and reads its public value, but is never imported by a node and never imports a private node module path directly. This removes the otherwise unavoidable `graph -> nodes -> graph` cycle, gives GraphHost one explicit injection point, and prevents filesystem discovery from silently changing topology.

Import rules are checked with an AST test:

```text
tool -> runtime -> graph -> nodes
                         nodes -> engine -> domain
runtime -> graph + agents + domain + deerflow.*
agents  -> domain + deerflow.* + langchain.*
graph   -> domain + nodes
domain  -> stdlib + pydantic only
```

`domain` cannot import outer layers; `engine` can import only domain; `agents` can import domain and public DeerFlow/LangChain APIs but not runtime/graph/nodes; nodes can import domain/engine but not agents, runtime, graph implementation modules, or sibling nodes. Runtime owns the concrete bridge from trusted DeerFlow objects to graph and agent execution. Production downstream source cannot import `app.*`; real Gateway integration tests may launch/import the app as a test fixture only. Neither upstream tree can import the downstream package. Generic `utils.py`, `helpers.py`, and `common.py` modules are forbidden.

Alternative considered: add the package to the backend uv workspace. Rejected because that edits the upstream mirror and reverses ownership.

Alternative considered: keep the complete structure tree in `openspec/config.yaml` or only in `architecture-policy.md`. Rejected because the former turns global prompt context into an ever-growing structural database, while the latter creates unvalidated prose that OpenSpec does not load automatically. The short bootstrap plus main-spec reference, machine-readable registry, controlled guide projection, and checker keep each fact in one owned representation.

### 3. Package independently and use environment-specific loading

`agent/pyproject.toml` is an independent, locked uv project. For repository development it declares an editable uv source for `deerflow-harness` at `../backend/packages/harness`; build metadata remains valid outside the monorepo by declaring the compatible harness version normally. Package version is single-sourced from `deerflow_deep_research/__about__.py`, so source-mounted Docker can report the same version without installed distribution metadata. Only directly imported runtime packages and test tools are declared. Comment-preserving configuration support is isolated in an operations extra so the Gateway runtime does not acquire an unused YAML dependency. Agent-owned tests and operations scripts run in the agent project environment; local Gateway loading installs the package editable into the already-synchronized backend environment with `--no-deps`.

Local dev/prod loading uses a project-owned wrapper:

1. `--stop` delegates immediately to the upstream stop action and performs no config-version check, sync, install, fingerprint, or doctor work;
2. for start/restart actions, load the same root `.env` and establish the same `DEER_FLOW_PROJECT_ROOT`/`DEER_FLOW_HOME` defaults as the upstream launcher, then run only application-state read-only preflight while an old Gateway may still be live: root prerequisites, canonical config-path agreement, the exact effective-config `config_version == config.example.yaml.config_version` gate, and `configure.py --check` from the separately locked agent operations environment; a missing/invalid/older/newer version aborts before any shared backend-environment mutation or fingerprinting and directs the operator to stop Gateway and run or reconcile the upstream upgrade;
3. delegate to the upstream stop action and require it to succeed before changing the shared backend environment, then run the same backend `uv sync --all-packages` plus detected extras and frontend install that the current upstream launcher would run;
4. install `agent/` editable into the now-synchronized backend environment with `--no-deps`, verify the harness and module origin, then compute the secret-free candidate fingerprint from the same `backend/` working directory the Gateway command uses so relative database/sandbox paths resolve identically; hash the effective `database`/`checkpointer`, `sandbox`, and supported worker-count inputs and export it as `DEER_FLOW_DEEP_RESEARCH_STARTUP_FINGERPRINT`;
5. run project doctor in explicit prelaunch-candidate mode and gate only on `runtime_ready`, then delegate the requested dev/prod/daemon start flags to the unchanged root launcher with `UV_NO_SYNC=1` and `--skip-install`. A requested restart has already been reduced to the verified stop followed by this start, so the downstream wrapper does not reproduce service orchestration.

The order is mandatory. Exact sync can remove an earlier editable install, and mutating the backend environment beneath a running Gateway is unsupported, so stop precedes sync and editable installation follows it. `agent/scripts/prepare.py` owns the no-orchestration sync/install/verification/candidate pipeline; `agent/scripts/serve.sh` owns only argument routing, read-only preflight, upstream stop/start delegation, and failure sequencing. The editable install is necessary because the upstream local launch commands overwrite `PYTHONPATH`. The current `uv run` is non-exact by default, but the wrapper still sets the documented `UV_NO_SYNC=1` control after exact sync/install so config-upgrade and Gateway `uv run` cannot unexpectedly reconcile the environment again. Config resolution is not guessed: preflight resolves the AppConfig path under the launch environment and separately predicts the current upstream `config-upgrade.sh` target (`DEER_FLOW_CONFIG_PATH`, then legacy backend, then root); those canonical paths must agree. Root/backend shadowing without an explicit common target is runtime-not-ready. Preparation and doctor use the Gateway's actual backend working directory because unified `DatabaseConfig.sqlite_dir` is resolved against process cwd. Requiring the exact current config version makes the upstream launcher's later config-upgrade invocation a proven no-op. A config edit after prelaunch doctor is still detected by RuntimeAdapter/GraphHost against the injected candidate before nested resource access. Editable source changes need no reinstall, but the upstream watcher only watches `backend/`; changing `agent/src` therefore requires a Gateway restart. The wrapper copies no service orchestration; stop/start delegation, cwd/path/default resolution, dependency-sync/config-version tokens, and the no-resync handoff are pinned by contract tests.

If preparation, installation, candidate generation, or doctor fails after quiescence, the wrapper leaves the stack stopped and reports the exact failed stage. It never restarts the old process against a possibly reconciled environment and never claims to roll an environment back; the next invocation reruns the locked exact preparation pipeline.

Docker uses `agent/docker/docker-compose.deep-research.yaml` as a downstream override. It mounts `../agent/src` read-only at `/app/agent/src` and replaces only the Gateway command so it retains the upstream command while setting `PYTHONPATH=/app/agent/src:.` from `/app/backend`, computing/exporting the canonical fingerprint from the container's effective config/environment, and running `deerflow_deep_research.runtime.diagnostics` in prelaunch-candidate mode before uvicorn. Only runtime-not-ready stops the container command; entry warnings remain visible. Group 6 establishes the source/fingerprint prelude, and group 13 adds the diagnostic gate after that module exists. A contract test compares the copied upstream command tokens with the current compose command except for the declared path/fingerprint/doctor prelude, making upstream drift explicit. A downstream baked image can replace the bind mount for production, but the upstream Dockerfile is untouched.

The documented Compose order is fixed: base `docker/docker-compose.yaml` first, downstream override second. Compose resolves the override's `../agent/src` source relative to the base compose directory; a rendered `docker compose config` contract must resolve it to `<repo>/agent/src`. Reversing file order is unsupported and doctor reports the resulting origin mismatch.

Host source is never mounted into a research sandbox. The sandbox keeps DeerFlow's existing `/mnt/user-data` and `/mnt/skills` mounts only.

Alternative considered: a local wrapper that only exports `PYTHONPATH`. Rejected because current upstream commands replace it. Alternative considered: duplicate root `scripts/serve.sh`. Rejected because it would fork service orchestration and drift quickly.

### 4. Materialize configuration structurally and preserve ownership

Committed templates live under `agent/config/`; the effective paths resolved under the loaded launch environment remain runtime truth. `agent/scripts/configure.py` resolves the same AppConfig and extensions-config targets the Gateway will use, reports their canonical paths without user-identifying prefixes, and refuses a root/backend shadow conflict or a write to an inert fallback file. Change 00 requires the effective skills root to be the canonical `<repo>/skills` mounted by its local/Docker assembly; a `skills.path`/`DEER_FLOW_SKILLS_PATH` override elsewhere is diagnosed as runtime-not-ready rather than receiving a misleading second copy. `DEER_FLOW_HOME` remains configurable and determines the effective per-user Agent root. The configurator round-trip parses YAML and structurally parses JSON before it materializes:

```yaml
tool_groups:
  - name: deep-research-control
tools:
  - name: deep_research
    group: deep-research-control
    use: deerflow_deep_research.tool:deep_research_tool
```

It also sets the effective `extensions_config.json -> skills.deep-research-controller.enabled=true`, copies the committed skill to `<repo>/skills/public/deep-research-controller/SKILL.md`, and provisions `{DEER_FLOW_HOME}/users/{user_id}/agents/deep-research/{config.yaml,SOUL.md}`. The Agent config references skill `deep-research-controller` and tool group `deep-research-control`.

Offline filesystem provisioning is deliberately narrow: `configure.py` can materialize only `default`, and only when `DEER_FLOW_AUTH_DISABLED=1` is active outside `DEER_FLOW_ENV/ENVIRONMENT=prod|production`, matching DeerFlow's documented auth-disabled gate without importing `app.*`. Otherwise it writes no user Agent and emits the committed template/request fields for the logged-in user to submit through current-user `POST /api/agents` when `agents_api.enabled=true`. Change 00 reads and diagnoses that flag but never enables it automatically because the API requires a trusted authenticated boundary. It does not expose `--user-id`; an operator string is not proof of identity.

The YAML merge uses a round-trip parser so comments, ordering, quoting, anchors, and unrelated formatting survive. JSON is structurally parsed, preserves unknown data and key order, and retains detected indentation/newline conventions when representable; arbitrary JSON whitespace is not treated as a semantic contract, but the first write converges and later runs are byte-stable. The merge algorithm is deterministic by semantic key (`tool_groups[].name`, `tools[].name`, skill name, Agent name). Matching project-owned entries are normalized; a same-name entry with a different use path or incompatible definition fails with a diagnostic. Writes are atomic, `--dry-run` emits a redacted structured diff, and `--check` performs no writes. Repeated execution produces no diff.

`configure.py --check` separates blocking runtime-configuration validity from entry materialization status. Malformed/ambiguous targets, ownership conflicts, or a missing/mismatched reflected tool/group are blocking. A missing/disabled public skill, missing dedicated Agent, or authenticated Agent that cannot be inspected offline is reported as `entry_ready = not_ready | unknown` and does not make the globally configured tool unavailable. The launcher passes these axes to doctor and gates only on final `runtime_ready`; it never treats a generic nonzero entry check as a second hidden launch gate.

Every mutating run writes a permission-restricted backup plus a manifest containing target path, before hash, after hash, and hashes of materialized skill/Agent templates. `--rollback <manifest>` restores the whole backup only when the current hash still equals the recorded after hash. If anything changed later, rollback removes only still-identical project-owned entries/files and refuses any ambiguous overwrite. It never treats a backup as authority over newer operator edits.

`--check` and `--dry-run` are safe while Gateway is live. Mutating configure and rollback have an explicit operational precondition that every Gateway sharing the files is stopped. The script acquires a project lock and refuses when an explicit/known local Gateway health endpoint is reachable or a project-owned local/Docker Gateway process is detected, because Gateway APIs are independent writers and do not share the lock. Those detectors cannot prove that no remote shared-filesystem writer exists, so the precondition remains operator-visible. A final content-signature comparison still guards an editor race before atomic replace.

The script never writes `{DEER_FLOW_HOME}/agents/deep-research/` or `skills/custom/deep-research-controller/`. A missing dedicated Agent or public entry skill does not disable the global tool, although change 00 completion still requires the committed entry artifacts to be materialized and verified.

Config/tool/skill/Agent changes take effect on the next agent build. Editable installation, package path, Docker source mount, and startup-only `database`/`checkpointer`/`sandbox` changes require Gateway restart. The project launcher fingerprints the effective startup-only values without logging their secret-bearing content. The wire value is strictly versioned and bounded as `v1:<64 lowercase hex>` over a canonical typed snapshot that includes its schema version; launch code assigns the parsed machine field directly and never evaluates shell text. Missing, malformed, or unknown-version values fail closed. GraphHost/RuntimeAdapter compare the current live AppConfig to that process-start fingerprint and return typed `restart_required` before provider or sandbox access on drift; this prevents request-time config reload from pairing the nested runtime with different startup singletons. Change 00 reads but does not change those selections. This follows `config.example.yaml` anchors plus `reload_boundary.STARTUP_ONLY_FIELDS`.

Reusable doctor logic lives in importable `runtime/diagnostics.py`; `agent/scripts/doctor.py` is a thin operations CLI. This lets Docker execute the same diagnostics inside the Gateway container through the source mount while host checks inspect rendered Compose/config state. Fingerprint semantics are explicit: prelaunch-candidate mode validates the freshly computed candidate against the same effective config that will be handed to a new process and never claims to inspect a running Gateway; in-process mode requires the environment fingerprint inherited at process start and compares live AppConfig against it. Missing mode/input is not silently replaced by a newly computed value. Machine output identifies the mode and has independent axes: boolean `runtime_ready`; `entry_ready.status = ready | not_ready | unknown`; and `durability = same_process | restart_durable | unavailable` plus effective provider kind. Runtime readiness covers package origin/version, reflected tool, trusted paths, sandbox separation, startup-fingerprint match, supported worker count, and provider compatibility. Entry readiness covers the public skill and dedicated Agent: any known missing/disabled/drifted entry yields `not_ready`; `unknown` is used only when no known entry defect exists but an authenticated Agent cannot be attributed offline; `ready` requires every entry check to pass. The shared provider classifier follows official legacy `checkpointer`-over-`database` precedence. CLI blocking exit status and launch gating depend only on `runtime_ready`; entry not-ready/unknown is emitted as a warning and never disables the global tool. Worker normalization mirrors `${GATEWAY_WORKERS:-1}`: missing/empty becomes integer `1`, and only the normalized integer `1` is supported; malformed, zero, negative, or greater values are runtime-not-ready. The normalized integer, not its textual spelling, enters the startup fingerprint.

### 5. Keep the public entry surfaces thin

The change 00 public skill establishes entry ownership: research requests must go through `deep_research` and the lead/dedicated Agent must not silently perform a parallel research workflow. It does not claim that research lifecycle actions or HITL are available yet; change 01 adds that interaction language with the fake graph. The dedicated Agent SOUL consistently routes to the tool and surfaces typed unavailability. Neither surface contains phase topology, gate rules, node prompts, source text, or claims of exclusive tool exposure.

Tool groups are not a security control because DeerFlow appends built-in/MCP/ACP tools. Actual authority remains inside the custom tool and node policy.

### 6. Adapt only trusted runtime fields into a non-checkpointed context

`deep_research_tool` is an async reflected `BaseTool` and remains a thin schema/dispatch surface. After strict schema validation it first asks the generic registry whether the action name is registered; an unavailable action returns before RuntimeAdapter, sandbox initialization, namespace derivation, or checkpoint access. For a registered action, `RuntimeAdapter` consumes DeerFlow's `ToolRuntime` and produces a runtime-owned `TrustedRuntimeEnvelope`, never serialized into graph state.

`TrustedRuntimeEnvelope` contains validated effective user id, outer thread id, outer run id, canonical host/virtual thread-data paths, the initialized parent sandbox state, `AppConfig`, and a progress emitter obtained through the supported LangGraph stream-writer API. It never reads private `__run_journal` fields and is visible only inside `runtime/` integration, GraphHost, runtime projection, and the concrete runtime-owned node-agent bridge.

Identity comes from an explicit, non-empty `runtime.context["user_id"]`, not from `resolve_runtime_user_id(runtime)`'s permissive fallback. The trust chain is pinned end to end: authenticated Gateway requests overwrite both `body.context` and `body.config.context` spoofing; explicit auth-disabled mode injects synthetic user `default`; internal callers retain an owner only through the internally authenticated path. Real Gateway contract tests cover all three paths. Thread data comes from `runtime.state` but its canonical host paths are recomputed from trusted user/thread data and compared before use. If sandbox state is absent, RuntimeAdapter calls `deerflow.sandbox.tools.ensure_sandbox_initialized_async(runtime)` once and then validates that same parent sandbox; initializer failure, a stale/mismatched sandbox, missing user/thread/AppConfig, inconsistent thread paths, or a path outside the current user's thread fails before GraphHost access. The Pydantic tool args schema uses `extra="forbid"` and permits only a bounded action name plus an optional bounded URL-safe opaque `probe_id`; authority fields are not legal arguments. Validation failures are normalized from error codes/field names and never serialize Pydantic `input`/`input_value`, rejected payloads, or secret-bearing values. `action` remains a bounded string so the dispatcher can return structured `action_unavailable` for lifecycle/unknown names, but the response reports only the code and advertised supported action without echoing the rejected action value; its tool description advertises only `infra_probe` in change 00.

`RuntimeAdapter` stops at the validated envelope. `runtime/projection.py` accepts that envelope only together with a registered research handler's validated opaque research-scope id, derives `/mnt/user-data/workspace/deep-research/<research_id>/` through validated path components, and creates pure `GraphContextView`/`NodeAgentContext` values plus a runtime-owned implementation of the domain `NodeExecutionCapabilities` protocol. A raw tool argument never selects host paths. Nodes receive the protocol through their factory dependencies and can request a bounded agent run, but cannot inspect raw user identity, AppConfig, host paths, sandbox internals, or child runtime state. Only opaque attribution, canonical virtual roots, and explicit policy can contribute model-visible data. Change 00 proves projection/bridge behavior with fixtures; `infra_probe` validates the envelope/sandbox and derives only its diagnostic checkpoint namespace, never creates a research workspace or node-agent projection. Change 01's registered research handlers become the first public callers of research projection.

The raw binding path is deliberately non-checkpointed:

```text
ToolRuntime
  -> TrustedRuntimeEnvelope                 (runtime only)
      -> registered research handler + validated scope id
          -> RuntimeProjection
              -> GraphContextView / NodeAgentContext (pure, authority-reduced)
              -> RuntimeNodeAgentBridge      (implements domain capability)
                   -> ephemeral child ThreadState    (parent sandbox + thread_data)
                   -> ephemeral child runtime context (raw user/thread/run/AppConfig)
                   -> bounded create_deerflow_agent runnable

graph node -> NodeExecutionCapabilities.run_agent(request)
           # node never receives either ephemeral raw object

infra_probe -> envelope validation + diagnostic namespace only
```

Alternative considered: place runtime handles in `ResearchState` or domain GraphContext. Rejected because they are non-serializable, secret-bearing infrastructure, violate the domain import boundary, and would make checkpoints environment-dependent.

### 7. Isolate nested checkpoints and manage SQL resources per action

`GraphHost` owns builder/topology caches, a generic typed action-handler registry, namespace derivation, a fixed-size process-local action-lock stripe set, a process-local memory saver, and the effective-provider classifier shared with doctor. It does not own a Gateway lifespan hook, `app.state`, a long-lived SQLite/Postgres pool, or named public research lifecycle methods. In change 00 only probe invoke/inspect behavior is registered; all research lifecycle actions fail with typed `action_unavailable` until change 01 installs separate fake-graph handlers.

Cached builders/topology and registered handlers are pure request-independent recipes. They never close over a TrustedRuntimeEnvelope, GraphContextView, NodeBuildDependencies, capability implementation, namespace, checkpointer, or user/thread value. Each action derives fresh reduced dependencies, binds node factories, and compiles inside that action's provider context; tests invoke different users/threads/capability sentinels through the same cached builder to prove there is no cross-action authority reuse.

For an opaque probe id, the checkpoint thread key is a domain-prefixed full SHA-256 digest of a versioned canonical tuple `(effective_user_id, outer_thread_id, probe_id)` with length-prefix encoding; `checkpoint_ns` is a fixed infrastructure-probe graph/version namespace. The digest is used as an internal key and is not accepted from the caller. This isolates users, outer threads, and the lead-agent checkpoint even when a caller reuses a probe id. Mutating actions for the same key take the same process-local lock stripe; cancellation while waiting causes no mutation. Change 00 explicitly supports one Gateway worker, matching the upstream default, and refuses stronger cross-process serialization claims.

For SQLite/Postgres each action follows:

```text
RuntimeAdapter -> namespace -> async with make_checkpointer(app_config)
                              -> compile cached builder with saver
                              -> invoke/update or inspect state
                              -> close context on success, error, or cancellation
```

Compiled graphs are not cached across SQL provider contexts. The one-node `InfraProbeState` is private infrastructure state containing only a schema version, probe id, monotonic visit count, provider kind, and last-seen marker. It is not `ResearchState`, has no interrupt, and remains a separate diagnostic topology/namespace when change 01 adds the fake research graph; old probe rows can never be interpreted as research state. Unknown probe schema versions fail closed.

Provider selection is centralized in `runtime/checkpoint.py` and mirrors the official async provider exactly: a present legacy `checkpointer` section wins, even when it selects memory; otherwise non-memory `database` selects SQLite/Postgres; otherwise memory is effective. Tests distinguish a directly constructed `AppConfig` defaulting to memory from file loading, where `_apply_database_defaults` currently turns an omitted database section into file-backed SQLite. Before selecting/constructing a saver, GraphHost requires the live startup-only fingerprint to match the launcher-captured value. It then uses official `make_checkpointer(app_config)` for SQL savers. For effective memory, GraphHost reuses one process-local saver so a second action can observe a same-process checkpoint. Legacy SQLite `:memory:` or an equivalent memory-mode URI is never classified as restart durable; missing Postgres connection data is unavailable. Doctor and tool output label those cases without stronger claims. File-backed SQLite/Postgres tests close the first provider context, open a second, and verify recovery; both require a subprocess restart profile before 00 completes.

The entire operational tool surface in change 00 is `action="infra_probe"` with an optional validated `probe_id`. With no id it creates at least 128 bits of CSPRNG entropy encoded as a bounded URL-safe opaque id containing no user/thread/path data; with the same validated id it invokes the one-node probe again and reports the previous plus current visit markers. Caller-provided ids never become checkpoint keys directly; trusted scope and domain/version separation are always re-derived. This is checkpoint recovery/revisit, not resume. Validly shaped `start`, `resume`, `status`, `cancel`, and unknown action names return typed `action_unavailable`; extra authority/unknown fields fail strict schema validation. Both paths occur before graph mutation. Change 01 registers the four lifecycle handlers; unknown actions and authority fields remain denied.

Alternative considered: reuse the outer lead-agent thread id. Rejected because it risks channel collisions and rollback coupling. Alternative considered: keep an SQL saver on GraphHost. Rejected because a reflected tool has no project-owned lifecycle hook that can close it reliably.

### 8. Propagate cancellation and progress through supported mechanisms

The current public cancellation contract is task cancellation. GraphHost and the node-agent adapter never catch and convert `asyncio.CancelledError` into success; cleanup runs in `finally`, child tasks are cancelled and awaited, and no background agent loop survives the tool call.

Progress uses `langgraph.config.get_stream_writer()` behind a project-owned emitter. Events contain stable event kind, research/probe ref, node/operation, status, and redacted detail. Absence of a writer in unit tests degrades to a no-op collector, not a private Gateway event-store call.

A required integration probe cancels an outer tool task while the nested graph/agent is active and proves child termination plus provider-context closure. If cancellation does not propagate with current public APIs, change 00 is blocked for design revision; implementation must not reach into Gateway `RunManager.abort_event` or modify backend.

### 9. Bridge nodes to phase agents without leaking runtime authority

`runtime/node_agent_bridge.py` is the only raw binding owner. It resolves the model and eligible tool objects from the trusted AppConfig plus a pure `PolicyRef`, creates an immutable execution policy, and builds the ephemeral child `ThreadState`/runtime context described above. Nodes call it only through `NodeExecutionCapabilities`; they do not import `agents` or `runtime`.

`agents/factory.py` wraps `create_deerflow_agent()` with `middleware=[...]` full takeover and `checkpointer=None`. The compiled agent is invoked as a separate runnable from the bridge, never installed as a LangGraph subgraph node that could inherit the parent saver. A bound child runnable is created per `run_agent` request and discarded after completion/cancellation; it is never cached across actions, users, threads, attempts, or capability instances. The factory imports no runtime layer and accepts already resolved model/tools plus pure model-safe context and immutable execution policy. The policy contains exact allowed tool objects/names, read roots, write roots, attempt root, maximum model calls, total/per-response/parallel tool-call limits, total token budget, per-model-call output-token cap, per-tool-result and structured-result size caps, wall time, and structured output type.

The curated chain contains only the minimum error normalization, policy enforcement, budget/cancellation, and structured-output middleware required by the phase agent. It does not auto-enable memory, title, uploads, subagents, skill evolution, todo, clarification, or an independent sandbox lifecycle. The exact ordered middleware types are pinned by a contract test.

Budget enforcement is admission control, not only after-the-fact accounting. A "model call" is one request to the chat model, independent of LangGraph supersteps. Before every text-only call, middleware serializes the actual message/tool-schema request and uses a deterministic UTF-8 byte upper bound (plus the policy's maximum output tokens) unless a provider counter is proven to be at least as conservative; it never depends on a network tokenizer download. Non-text content requires an explicit conservative modality estimator in policy and fails admission when none exists. The call is refused if the bound can exceed remaining tokens. Actual `usage_metadata` reconciles the estimate after the response; a model response without usable accounting is terminal `usage_unavailable`, has tool calls stripped, and cannot issue tools or another model call. Tool-call counts/parallelism are checked before dispatch, and every tool result is size-bounded before it can re-enter model context.

Tool authorization is enforced twice: the model receives only curated tools, and pre-dispatch middleware rejects any call whose runtime name is absent from the policy. Every allowable tool must register a typed `ToolPolicySpec` naming its path-bearing fields, read/write effect, execution-time validator, and cancellation class; a tool with unknown argument shape or no approved native async/cancellable path is not eligible for the node. Path fields are normalized and contained before execution, and only a tool/provider pair that revalidates at the final filesystem boundary is eligible. A provider/tool combination that cannot prove symlink containment is denied for writes. Default policy denies bash; a later node that needs shell access must explicitly select a sandboxed tool and add deterministic command/path validation. Writes are restricted to the active attempt root; phase, gate, ledger, sibling-attempt, package-source, and host paths are never writable by the model.

System/policy prompts are loaded from package resources. External source content is placed only in a clearly delimited untrusted data message or referenced sandbox artifact; it is never interpolated into those trusted instructions. Policy enforcement remains effective even if the source asks the agent to ignore rules, invoke a forbidden tool, alter phase/gate state, or mutate the ledger.

The adapter returns a validated typed result with finish reason, usage, artifact refs, and redacted failure. Malformed output is a failure, not partial success. `ask_clarification` is absent from both tool list and middleware; an attempted call is rejected and cannot create an interrupt.

Alternative considered: use default `RuntimeFeatures`. Rejected because its feature path always adds clarification and may add sandbox lifecycle or tools that phase agents must not own. Alternative considered: prompt-only restrictions. Rejected because source content and model errors can bypass them.

### 10. Make folder, mount, policy, and prompt boundaries executable contracts

The test suite includes:

- permanent-governance manifest schema/path checks, active-main-spec reference checks, and deterministic `agent/AGENTS.md` controlled-block rendering;
- AST import-direction and forbidden-generic-module checks;
- canonical package/node-shape and stable reflection-path tests;
- config merge/idempotency/conflict/redaction tests;
- local editable-install and Docker override command/mount tests;
- RuntimeAdapter forged-context and cross-user/thread denial tests;
- fresh-thread sandbox initialization plus parent-binding/non-leakage tests;
- effective-provider precedence, checkpoint namespace concurrency/schema/lifecycle/persistence tests;
- runtime-owned node-agent bridge, full-takeover middleware order, no-checkpointer, inherited-context tests;
- model/tool-call/token/tool-result/structured-result/wall-time budget tests;
- tool/path/cross-attempt/gate/ledger denial tests;
- adversarial source fixtures using Replay/Fake models with zero external API;
- cancellation and progress projection integration probes.

`agent/AGENTS.md` makes these contracts operational for later changes, while the active main spec and its normative manifest reference remain authoritative. `openspec/governance/check_project_architecture.py` is the archive-level deterministic gate and the agent-owned contract suite exercises the same repository rules in development. A stale guide block, misplaced node, sibling-node import, reflection drift, or second source tree fails before business behavior is considered.

## Risks / Trade-offs

- [Editable install can drift from the checked-out source or harness version] -> `doctor.py` resolves module origins and package versions; the launcher reinstalls idempotently and fails on an incompatible harness.
- [Upstream exact uv sync removes the downstream editable install or mutates an environment used by a live Gateway] -> The project launcher delegates stop first, syncs second, installs third, and delegates startup with `UV_NO_SYNC=1` plus `--skip-install`; a subprocess contract pins that order.
- [Docker override repeats the upstream Gateway command] -> Keep the override to one command delta and pin it with a token-level contract test against `docker/docker-compose.yaml`.
- [Per-action SQL setup adds latency] -> Accept the cost for deterministic cleanup; consider a process pool only after a public lifecycle hook is proven.
- [Memory appears to work but loses checkpoints on restart] -> Mark it non-durable in doctor/tool output and exclude it from restart acceptance.
- [Tool groups create a false sense of isolation] -> Keep UX language explicit and test code-level denial with built-in/MCP/ACP-like fake tools present.
- [Config writes race another operator or rollback clobbers newer edits] -> Use atomic replace, before/after manifests, restricted backups, and hash-guarded semantic rollback that refuses ambiguity.
- [A remote Gateway sharing the same files cannot be discovered reliably] -> Make stopped-Gateway status an explicit mutation precondition, reject every configured/known reachable endpoint, and retain final compare-before-replace protection without claiming the health check proves global quiescence.
- [Cancellation semantics differ across LangGraph versions] -> Pin compatible floors and require a real nested cancellation probe before declaring 00 complete.
- [A full-takeover embedded middleware chain misses a useful upstream guard] -> Pin the intentionally selected chain and add features only through explicit policy/design changes, never through implicit defaults.
- [Parallel same-probe calls fork or lose visit state] -> Serialize same-namespace mutations with a fixed-size process-local lock stripe set and fail readiness for every worker input not normalizing to integer one until a later distributed coordination design exists.
- [The large scope of 00 delays the fake graph] -> Keep all behavior business-free and tie every task to one of the four capabilities; do not pull 01 state/topology into this change.

## Migration Plan

1. Add the standalone package, tests, templates, and project-owned tooling without changing runtime config.
2. Run unit/contract tests and `configure.py --dry-run`; inspect the redacted merge.
3. Create a backup/rollback manifest and materialize the tool, public skill, and explicit no-auth `default` Agent; authenticated users create their own Agent through `POST /api/agents`.
4. For local use, load root `.env`, establish upstream-equivalent runtime-path defaults, require unambiguous effective config/extensions/canonical skills paths and the exact current config version, then delegate upstream stop. Run upstream-equivalent exact dependency sync and install the package editable with `--no-deps`; compute/export the startup candidate, pass prelaunch doctor, and delegate startup with `UV_NO_SYNC=1` plus `--skip-install`. For Docker, apply the base-first override so the container computes/exports the same canonical fingerprint before uvicorn. Keep `GATEWAY_WORKERS=1` and restart Gateway; use in-process diagnostics after startup when verifying the running configuration.
5. Run `infra_probe` twice on memory for same-process revisit behavior and on SQLite/Postgres for provider reopen/restart recovery where configured. Do not test fake research resume until change 01.
6. Roll back with the manifest. Restore a whole backup only when the current target still matches the recorded post-change hash; otherwise remove only unchanged project-owned entries/files and stop on ambiguity. The offline manifest may remove only the no-auth Agent it created; an authenticated user's API-created Agent is user-owned and must be removed, if desired, through that same current-user Agent API. Then uninstall the editable package or remove the Docker override and restart Gateway. Checkpoint rows and user workspace data are retained unless an operator explicitly removes the isolated namespace.

## Open Questions

There are no open product architecture choices in change 00. Two implementation facts are mandatory proof gates: reflected async-tool loading must preserve `ToolRuntime`, and outer task cancellation must terminate nested graph/agent work. Failure of either gate requires revising this downstream design before implementation continues; it does not authorize an upstream patch. Cross-process research-action serialization is explicitly unresolved and unsupported in change 00, so it is diagnosed as not ready rather than left as an implicit claim.
