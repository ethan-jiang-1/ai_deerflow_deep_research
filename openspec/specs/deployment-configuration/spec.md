# deployment-configuration Specification

> req: DEC-001, DEC-002, DEC-003, DEC-004, DEC-005

## Purpose
How the Deep Research downstream package is loaded, configured, materialized, provisioned, and diagnosed across environments without modifying upstream source.
## Requirements
### Requirement: Gateway loads one downstream package in every supported environment
The project SHALL provide local-development, local-production, and Docker assembly that resolves `deerflow_deep_research` from the checked-out or mounted `agent/src` source while leaving upstream source unchanged. Each start SHALL inject a secret-free, canonical, strictly parsed `v1:<64 lowercase hex>` fingerprint of the effective startup-only provider/sandbox/normalized-worker inputs for runtime drift detection; missing, malformed, or unknown-version fingerprints SHALL fail closed and launch code SHALL NOT evaluate fingerprint command output as shell source. Host package source SHALL NOT be mounted into the research sandbox.

Change 00 delivers the loadable-source mechanism and proves it with contract tests: the `prepare.py` preparation core (upstream-equivalent sync plus `--no-deps` editable install into the backend environment, root/backend/explicit config-target agreement and exact config-version preflight, harness/module-origin verification, and secret-free startup-candidate computation) and the committed Docker Compose override that read-only mounts `agent/src` and exports the container-effective candidate. The project-owned live launch WRAPPER that automates the stop → prepare → prelaunch-doctor → start lifecycle, the in-container prelaunch doctor GATE before uvicorn, and live dev/production/Docker launch verification are DEFERRED to a follow-up deployment change (`_backlog/todos/deferred_deep-research-00-launcher-and-docker.md`); they require a provisioned deployment environment and are not part of change 00.

#### Scenario: Editable source is resolved by the preparation core
- **WHEN** the preparation core runs against a caller-quiesced backend environment
- **THEN** it proves the AppConfig and upstream config-upgrade targets are the same canonical file, passes exact-current-version preflight, runs upstream-equivalent dependency sync before the `--no-deps` editable install, verifies compatible DeerFlow 2.1 harness and module origin, computes a secret-free startup candidate, and Python resolves `deerflow_deep_research` from the current `agent/src` tree

#### Scenario: Mismatched upstream config is refused before fingerprinting
- **WHEN** the effective config version is missing, invalid, older, or newer than `config.example.yaml.config_version`
- **THEN** preparation performs no shared backend-environment mutation or fingerprint and directs the operator to upgrade an older config or reconcile the config/checkout pair for any other mismatch

#### Scenario: Ambiguous config targets are refused
- **WHEN** AppConfig resolution and the current upstream config-upgrade search order select different canonical files, including an unqualified root/backend shadow pair
- **THEN** preparation performs no shared backend-environment mutation or fingerprint and reports the conflicting paths without exposing their contents

#### Scenario: Docker exports the container-effective candidate
- **WHEN** the base-first Docker override renders the Gateway command
- **THEN** it read-only mounts `agent/src`, sets the Gateway-only `PYTHONPATH`, and computes and exports the candidate inside the container from the mounted source and effective config before the unchanged uvicorn tokens, without mounting host source into the research sandbox

#### Scenario: Startup-only drift requires restart
- **WHEN** live config reload changes effective database/checkpointer or sandbox values after the launcher captured the process-start fingerprint
- **THEN** doctor and runtime integration report `restart_required` before nested provider or sandbox access

### Requirement: Runtime configuration materialization is idempotent
The configurator SHALL resolve and mutate the same AppConfig and extensions-config targets the Gateway will use under the loaded launch environment, merge the `deep-research-control` tool group and `deep_research` reflected tool with comment/order/style-preserving YAML operations, and merge the public-skill enabled state with structured JSON operations that preserve unknown data and key order. Change 00 SHALL require the effective skills root to be its canonical repo `skills/` mount and SHALL fail rather than writing an inert fallback or alternate skill copy. It SHALL retain the JSON file's detected indentation/newline convention when representable and converge to a byte-stable result after the first write. It SHALL support check, dry-run, permission-restricted backup, atomic write, redacted diff, and hash-guarded rollback modes; repeated execution SHALL produce no semantic drift or further textual drift.

#### Scenario: Effective configuration targets are authoritative
- **WHEN** the launch environment selects explicit config/extensions paths or creates a root/backend shadow ambiguity
- **THEN** configure writes only the unambiguous effective targets or fails before every write, and doctor never reports a fallback file as active

#### Scenario: Noncanonical skills root is refused
- **WHEN** effective `skills.path` or `DEER_FLOW_SKILLS_PATH` resolves outside the canonical repo skills root used by the local/Docker assembly
- **THEN** configure performs no write and reports runtime not ready instead of materializing a public skill that the supported mount contract does not expose

#### Scenario: Entry drift is not a hidden runtime gate
- **WHEN** the reflected tool/group configuration is valid but the public skill or dedicated Agent is missing or cannot be inspected offline
- **THEN** check reports entry not-ready or unknown without reporting runtime configuration invalid, and the launcher defers the final decision to doctor's independent readiness axes

#### Scenario: Fresh and repeated configuration converge
- **WHEN** configure runs twice against fresh valid config fixtures
- **THEN** the first run creates the required semantic entries and the second run reports no changes

#### Scenario: Same-name foreign ownership is refused
- **WHEN** an existing tool or group uses a project-owned name with a different reflection path or incompatible definition
- **THEN** configure performs no write and reports the exact ownership conflict without exposing secret values

#### Scenario: Rollback preserves later operator edits
- **WHEN** a target changed after the configurator recorded its post-change hash
- **THEN** rollback removes only byte-identical project-owned entries/files or stops on ambiguity and never restores the whole stale backup over newer edits

#### Scenario: Detected online mutation is refused
- **WHEN** configure or rollback would mutate runtime files while an explicit/known local Gateway endpoint is reachable or a project-owned local/Docker Gateway process is detected
- **THEN** it performs no write and reports the offline operational precondition, while check and dry-run remain available

### Requirement: Public entry skill is committed and enabled

The project SHALL keep the `deep-research-controller` skill source under
`agent/config/public-skill/`, materialize it under `skills/public/`, and store its
enabled state in `extensions_config.json`. The change-01 skill MAY route research
requests to the `start | resume | status | cancel` lifecycle, but SHALL explicitly
surface `implementation_mode=full_fake`, SHALL state that terminal fixtures are not
research findings or reports, and SHALL NOT claim real research completion. It SHALL
NOT contain graph topology, phase prompts, fixture controls, answer payloads, exclusive
tool claims, or security-isolation claims.

#### Scenario: Public skill is available
- **WHEN** configuration is materialized and enabled skills are loaded
- **THEN** the public Deep Research entry skill is discoverable with content matching its committed source

#### Scenario: Full-fake lifecycle is represented honestly
- **WHEN** the entry skill handles a research request or lifecycle result in change 01
- **THEN** it preserves the `full_fake` mode, routes only through the documented control actions, and does not present a terminal fixture as findings, citations, report content, or completed research

#### Scenario: Legacy custom path is rejected
- **WHEN** validation finds the project entry skill under `skills/custom/deep-research-controller/` instead of the public path
- **THEN** the configuration check fails and identifies the legacy location

### Requirement: Dedicated Agent is provisioned in the effective user scope

The project SHALL provision `deep-research` Agent files only at
`{DEER_FLOW_HOME}/users/{effective_user}/agents/deep-research/`, reference the public
skill and control tool group, and use the dedicated Agent only as a recommended UX
route. Its change-01 SOUL/config guidance SHALL preserve and surface
`implementation_mode=full_fake` and SHALL forbid presenting fake terminal state as
research output. Offline filesystem configuration SHALL provision only explicit no-auth
user `default`; authenticated provisioning SHALL use current-user `POST /api/agents`
only when the operator has independently enabled `agents_api.enabled`. Change 01 SHALL
NOT enable that security-sensitive API automatically. The global control tool SHALL
remain usable when the Agent is absent.

#### Scenario: No-auth user is isolated
- **WHEN** configure provisions an explicit non-production `DEER_FLOW_AUTH_DISABLED=1` installation
- **THEN** it writes the Agent under `users/default/agents/deep-research/` and writes nothing under the shared legacy Agent root

#### Scenario: Production cannot use offline auth-disabled provisioning
- **WHEN** auth-disabled provisioning is requested with `DEER_FLOW_ENV` or `ENVIRONMENT` set to production
- **THEN** configure refuses the Agent write and does not weaken or bypass DeerFlow authentication

#### Scenario: Unvalidated authenticated identity is refused
- **WHEN** offline configuration receives an arbitrary `--user-id` or runs for an authenticated deployment without current-user API attribution
- **THEN** filesystem provisioning fails without creating or modifying any user's Agent directory and directs the authenticated user to the current-user API

#### Scenario: Offline rollback does not own authenticated Agent state
- **WHEN** an authenticated user created the Agent through `POST /api/agents` and an operator rolls back the offline configuration manifest
- **THEN** rollback leaves that user's Agent untouched and directs user-owned deletion through the authenticated Agent API

#### Scenario: Dedicated Agent preserves skeleton honesty
- **WHEN** the dedicated Agent invokes or explains a change-01 lifecycle action
- **THEN** it surfaces the `full_fake` mode, does not claim exclusive tool isolation, and does not describe the terminal fixture as a real research answer or report

### Requirement: Diagnostics expose readiness without secrets
Doctor SHALL separately report its fingerprint inspection mode, boolean `runtime_ready`, `entry_ready.status = ready | not_ready | unknown`, and `durability = same_process | restart_durable | unavailable` with effective provider kind. Prelaunch-candidate mode SHALL validate the launcher's freshly computed candidate against the effective launch config without claiming to inspect a running process. In-process mode SHALL compare live AppConfig with the fingerprint inherited by that process; missing mode or expected fingerprint SHALL NOT be replaced by silent recomputation. Runtime readiness SHALL cover package origin/version, reflection resolution, config ownership, source/mount paths, sandbox separation, the applicable fingerprint match, supported worker count, and provider compatibility. Entry readiness SHALL cover the public skill and dedicated Agent without disabling the global tool: a known defect SHALL produce `not_ready`; `unknown` SHALL apply only when no known defect exists and the authenticated Agent cannot be inspected offline; `ready` SHALL require all entry checks to pass. Durability SHALL follow legacy `checkpointer`-over-`database` precedence. Doctor's blocking exit status SHALL depend only on runtime readiness. Doctor SHALL report next-build/restart requirements and redact credentials, connection secrets, host user identifiers, full startup inputs/fingerprints, and full internal checkpoint keys.

#### Scenario: Ready environment is classified accurately
- **WHEN** doctor inspects a correctly assembled SQLite environment
- **THEN** it reports runtime ready, entry readiness independently, SQLite restart recovery expected, and no source mount inside the sandbox

#### Scenario: Prelaunch readiness is not confused with a running process
- **WHEN** the wrapper supplies a freshly computed SQLite candidate to prelaunch doctor before starting Gateway
- **THEN** doctor labels the result as prelaunch-candidate, verifies it against the same effective config, and does not claim that an existing process inherited that fingerprint

#### Scenario: Missing dedicated Agent is an entry warning
- **WHEN** package, reflected tool, paths, and provider are valid but the dedicated Agent is absent
- **THEN** doctor reports runtime ready and entry not ready without claiming the global control tool is unavailable

#### Scenario: Authenticated Agent cannot be guessed offline
- **WHEN** doctor runs without a current-user authenticated API context in an authenticated deployment
- **THEN** it reports the dedicated Agent check as unknown or warning rather than inspecting an arbitrary user directory

#### Scenario: Effective provider precedence is consistent
- **WHEN** legacy `checkpointer` and unified `database` select different backends
- **THEN** doctor reports the legacy checkpointer backend and the same durability class GraphHost will use

#### Scenario: Invalid persistent provider is unavailable
- **WHEN** the effective provider has a missing Postgres URL or an SQLite memory-mode connection
- **THEN** doctor reports unavailable or same-process durability as applicable and does not report restart recovery expected

#### Scenario: Unsupported worker input is not ready
- **WHEN** `GATEWAY_WORKERS` does not normalize under `${GATEWAY_WORKERS:-1}` to integer one, including malformed, zero, negative, or greater values
- **THEN** doctor reports runtime not ready and the launcher does not claim process-local action serialization is sufficient

#### Scenario: Secret-bearing failure is redacted
- **WHEN** a failing fixture contains a database URL or API key
- **THEN** doctor reports the failing field/provider without printing the secret value

