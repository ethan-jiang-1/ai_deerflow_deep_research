> req: RUI-001, RUI-002, RUI-003, RUI-004, RUI-005

## ADDED Requirements

### Requirement: One reflected control tool exposes an infrastructure probe
DeerFlow SHALL resolve `deerflow_deep_research.tool:deep_research_tool` as the `deep_research` tool. Change 00 SHALL expose only the business-free `infra_probe` action with an optional bounded URL-safe opaque probe id and SHALL return structured, redacted results. When omitted, the id SHALL contain at least 128 bits of server CSPRNG entropy and no scope-derived identity/path text; caller-supplied ids SHALL never become internal checkpoint keys without trusted scope/domain derivation. Public research `start`, `resume`, `status`, and `cancel` remain unavailable until change 01.

#### Scenario: Probe starts through the reflected tool
- **WHEN** a fake DeerFlow runtime invokes `infra_probe` with valid trusted context
- **THEN** the tool writes and reads one probe checkpoint and returns an opaque probe reference, backend durability class, and status

#### Scenario: Unsupported control action is refused
- **WHEN** the tool receives a research lifecycle action or unknown action in an otherwise valid request
- **THEN** it returns typed `action_unavailable` without echoing the rejected action before RuntimeAdapter, sandbox initialization, namespace derivation, or graph/checkpoint mutation

#### Scenario: Extra authority field is schema-rejected
- **WHEN** the tool receives an identity, path, sandbox, checkpoint, or unknown extra field
- **THEN** strict input validation rejects the call before dispatch, emits only normalized field/code diagnostics without rejected input values, and no graph/checkpoint mutation occurs

### Requirement: Runtime authority comes only from trusted context
RuntimeAdapter SHALL require the explicit server-injected user, outer thread/run, and AppConfig from DeerFlow runtime context, validate thread-data roots from runtime state against that user/thread, and obtain the same parent sandbox through DeerFlow's public async lazy initializer when it is not yet present. It SHALL place raw values in a runtime-owned TrustedRuntimeEnvelope and SHALL NOT invent a research scope. A separate runtime-owned projection SHALL require a registered research handler's validated opaque scope id before deriving a research root and pure domain GraphContextView/capability/NodeAgentContext values. Graph nodes SHALL consume only those pure contracts, and model-facing NodeAgentContext SHALL contain only opaque attribution, canonical virtual roots, and policy. The tool args schema SHALL forbid caller-supplied identity, path, sandbox, and checkpoint fields; the permissive `resolve_runtime_user_id()` fallback to `default` SHALL NOT satisfy a missing trusted runtime identity. The change 00 infrastructure probe SHALL not create a research projection or workspace.

#### Scenario: Trusted runtime is adapted without inventing research scope
- **WHEN** runtime context and state contain one consistent effective user, thread, sandbox, and thread-data mapping
- **THEN** RuntimeAdapter emits only a runtime-owned envelope and no research root or node-agent projection

#### Scenario: Registered handler scope is authority-reduced
- **WHEN** a registered research handler supplies a validated opaque scope id with a trusted envelope
- **THEN** runtime projection emits frozen pure graph and node-agent contracts with canonical virtual roots and no model-controlled authority fields, AppConfig, or host paths

#### Scenario: Fresh thread initializes its parent sandbox
- **WHEN** trusted thread data exists but lazy parent sandbox state has not yet been created
- **THEN** RuntimeAdapter uses the public async sandbox initializer once, validates the resulting parent sandbox, and does not create a second sandbox/thread lifecycle

#### Scenario: Forged cross-user fields are denied
- **WHEN** tool arguments include user, thread, host path, sandbox, checkpoint, or any unknown field
- **THEN** schema validation rejects the invocation before RuntimeAdapter, namespace derivation, or filesystem access

#### Scenario: Gateway identity overrides client context spoofing
- **WHEN** an authenticated or explicit auth-disabled Gateway request supplies a conflicting user id through body context or body config context
- **THEN** the runtime user is the server-injected authenticated id or synthetic `default`, never the client value

#### Scenario: Missing explicit runtime identity fails closed
- **WHEN** a hand-built runtime has no non-empty `runtime.context["user_id"]` even though DeerFlow's generic helper could fall back to `default`
- **THEN** RuntimeAdapter rejects it before sandbox initialization, namespace derivation, or checkpoint access

#### Scenario: Startup sandbox drift fails before initialization
- **WHEN** live AppConfig sandbox values do not match the launcher-captured startup fingerprint
- **THEN** RuntimeAdapter returns typed `restart_required` before calling the sandbox initializer

### Requirement: Nested checkpoint namespaces are isolated
The runtime SHALL derive the nested checkpoint key from a versioned, domain-separated, collision-resistant encoding of effective user, outer thread, and opaque probe/research id. The caller SHALL not provide the derived key, and the nested graph SHALL not share the outer lead-agent checkpoint identity. Same-namespace mutating actions SHALL be serialized in the supported single-worker runtime; unsupported multi-worker execution SHALL fail readiness rather than claim cross-process exclusion.

#### Scenario: Stable identity revisits the same probe
- **WHEN** the same effective user, outer thread, and probe id are used in a later action
- **THEN** namespace derivation returns the same internal key and the new probe invocation observes the prior visit marker without claiming research resume

#### Scenario: Cross-scope collision is prevented
- **WHEN** two users or two outer threads reuse the same probe id
- **THEN** their internal keys and checkpoint histories differ and neither can inspect the other

### Requirement: GraphHost owns topology but not live SQL resources
GraphHost SHALL cache only request-independent builder/topology recipes and a generic typed action-handler registry, with only the infrastructure-probe handler registered by change 00. Cached objects SHALL NOT retain runtime envelopes, reduced dependencies/capabilities, namespace values, checkpointers, or user/thread data; each action SHALL bind fresh dependencies and compile inside the lifetime of the effective selected checkpointer. SQLite/Postgres SHALL use `make_checkpointer(app_config)` per action and close it on success, failure, or cancellation; the project-owned provider classifier SHALL follow the official legacy `checkpointer`-over-`database` precedence; embedded phase agents SHALL not receive that checkpointer. The infrastructure probe SHALL retain its own versioned topology/namespace when change 01 adds the separate fake research graph.

#### Scenario: SQL provider is reopened and closed
- **WHEN** two probe actions run against a fake async SQL provider
- **THEN** each action enters and exits its own provider context and no compiled graph or connection escapes that context

#### Scenario: Invocation failure still closes resources
- **WHEN** the probe node raises or its outer task is cancelled
- **THEN** provider cleanup and child-task cleanup complete and the error is not reported as success

#### Scenario: Startup provider drift does not split checkpoints
- **WHEN** live AppConfig database/checkpointer values differ from the launcher-captured startup fingerprint
- **THEN** GraphHost returns typed `restart_required` before opening a saver or reading/writing a nested checkpoint

### Requirement: Persistence guarantees match the selected backend
The probe SHALL describe memory and SQLite memory-mode connections as same-process only, file-backed SQLite/Postgres as durable across provider reopen and Gateway restart when correctly configured, and invalid or missing connection data as unavailable. Probe and doctor output SHALL NOT claim stronger durability than the active resolved backend provides.

#### Scenario: Memory revisits only in one process
- **WHEN** two probe actions use the same process-local memory GraphHost
- **THEN** the second action observes prior state and the response labels restart recovery unsupported

#### Scenario: Persistent provider survives reopen
- **WHEN** a file-backed SQLite or valid Postgres probe is written, its provider context is closed, and a fresh context reads the same namespace
- **THEN** the prior checkpoint is recovered without using outer lead-agent checkpoint state

#### Scenario: SQLite memory mode is not restart durable
- **WHEN** the effective legacy SQLite connection is `:memory:` or an equivalent memory-mode URI
- **THEN** GraphHost and doctor report same-process-only durability and never claim provider-reopen or Gateway-restart recovery

#### Scenario: Legacy provider overrides unified database
- **WHEN** legacy `checkpointer` selects memory and `database` selects SQLite, or vice versa
- **THEN** GraphHost and doctor both use and report the legacy selection, matching `make_checkpointer(app_config)`
