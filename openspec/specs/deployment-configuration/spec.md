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

Doctor SHALL separately report its fingerprint inspection mode, boolean
`runtime_ready`, `entry_ready.status = ready | not_ready | unknown`, and
`durability = same_process | restart_durable | unavailable` with effective provider
kind. It SHALL also report
`work_unit_storage = ready | not_ready | unknown`. Prelaunch-candidate mode SHALL validate the launcher's freshly computed candidate
against the effective launch config without claiming to inspect a running process.
In-process mode SHALL compare live AppConfig with the fingerprint inherited by that
process; missing mode or expected fingerprint SHALL NOT be replaced by silent
recomputation.

Runtime readiness SHALL cover package origin/version, reflection resolution, config
ownership, source/mount paths, sandbox separation, the applicable fingerprint match,
supported worker count, provider compatibility, and the work-unit store's
shared-workspace transaction prerequisite. The latter SHALL be ready only when the
selected sandbox exposes the same physical thread workspace as the trusted host path and
the filesystem supports bounded POSIX locking, same-directory atomic replace, and
durability sync. Remote, non-mounted, custom, or otherwise unverified providers SHALL
make runtime readiness fail closed for work-unit execution; doctor SHALL NOT claim that
a host-only ledger can validate files written in a separate sandbox filesystem.

Doctor and runtime SHALL import one pure sandbox-mode classifier with these exact
outcomes: canonical `LocalSandboxProvider` paths are `ready` candidates;
`AioSandboxProvider` without `provisioner_url` is a `ready` candidate; AIO with a
non-empty `provisioner_url`, `E2BSandboxProvider`, and `BoxliteProvider` are
`not_ready`; every unrecognized/custom provider is `unknown`. Stable reason codes SHALL
distinguish `local_thread_mount`, `aio_local_thread_mount`,
`aio_provisioner_unmounted`, `e2b_unmounted`, `boxlite_unmounted`, and
`provider_unrecognized`. `runtime_ready` SHALL be false unless
`work_unit_storage == ready`, including the `unknown` case.

Runtime/store error reasons SHALL be the closed redacted set
`aio_provisioner_unmounted | e2b_unmounted | boxlite_unmounted |
provider_unrecognized | thread_mount_unavailable | workspace_alias_mismatch |
posix_primitives_unavailable | probe_cleanup_failed | ledger_corrupt |
accepted_artifact_diverged | lock_timeout`. `lock_timeout` SHALL accompany only
`work_unit_store_busy`; every other error reason SHALL accompany only
`work_unit_storage_unavailable`. The two ready-mode codes remain success checks, not
error reasons.

Lifecycle denial output SHALL expose the applicable closed value only as
`infrastructure_reason`; no doctor issue text, host path, provider URL, probe token, or
exception detail SHALL enter the wire result.

The classifier SHALL recognize both package-export and checked-in implementation class
paths for those four built-in providers. It SHALL NOT infer readiness by suffix or class
name; an otherwise similar path is custom/unrecognized and therefore `unknown`.

For a ready candidate, prelaunch doctor SHALL probe required locking, same-directory
replace, file fsync, and directory fsync primitives in the effective host thread-data
filesystem without disclosing its path. Success SHALL require real operations: two-open-
description nonblocking `fcntl.flock` acquisition/contended denial, descriptor-relative
exclusive no-follow regular-file creation, file fsync, same-directory
`os.replace(..., src_dir_fd=..., dst_dir_fd=...)`, result reopen/verification, directory
fsync, and cleanup. Capability introspection such as membership in `os.supports_dir_fd`
SHALL NOT count as a successful probe.

Runtime store construction SHALL additionally resolve the installed provider singleton,
require `uses_thread_data_mounts is True`, require
`provider.get(parent_sandbox.id) is parent_sandbox`, round-trip independently generated
bounded random base64url ASCII tokens in both host-write/sandbox-read and sandbox-write/
host-read directions, and repeat the filesystem primitive probe. Synchronous parent
sandbox `read_file`/`write_file` calls SHALL run through `asyncio.to_thread`. Host-created
probe files SHALL use exclusive mode `0600`; because the public sandbox write API has no
mode parameter, the sandbox-created alias file SHALL be opened no-follow from the trusted
host directory, verified regular, narrowed with `fchmod(0600)`, then read and removed.
Cleanup SHALL use trusted host descriptor-relative unlink/rmdir in `finally`. Because an
alias-mismatch file may exist only inside the sandbox and the public interface has no
delete method, cleanup SHALL also run a bounded, shell-quoted
`Sandbox.execute_command` for only the trusted derived virtual probe path and probe-only
empty directories through `asyncio.to_thread`, then verify absence. Caller/model text
SHALL never enter that command. Any cleanup residue or error SHALL return
`probe_cleanup_failed`. Probe files SHALL be randomized and never treated as control,
evidence, or research artifacts. Any other runtime failure SHALL return
`work_unit_storage_unavailable` before research artifact, ledger, accepted-ref, or
checkpoint mutation. Sandbox config already belongs to the startup fingerprint; this
change SHALL add no startup-only config field.

Runtime probes SHALL use hidden `.work-unit-probe-<32-lowercase-hex>` for aliasing and the
exact same-token filesystem family `.work-unit-fsprobe-<32-lowercase-hex>.lock`,
`.work-unit-fsprobe-<32-lowercase-hex>.src`, and
`.work-unit-fsprobe-<32-lowercase-hex>.dst` inside the current research `diagnostics/`
subtree. Prelaunch doctor, which has no research id or parent sandbox, SHALL use the exact
same-token host-side family
`.deep-research-work-unit-fsprobe-<32-lowercase-hex>.lock`,
`.deep-research-work-unit-fsprobe-<32-lowercase-hex>.src`, and
`.deep-research-work-unit-fsprobe-<32-lowercase-hex>.dst` directly under the existing
gateway-visible `get_paths().base_dir`, the parent filesystem for all thread data. It
SHALL NOT invent a user/thread id or use the Docker-daemon-only `host_base_dir`. No probe
SHALL be returned as a ref; files and any probe-only empty directories SHALL be removed
on success, denial, exception, and cancellation.

Entry readiness SHALL cover the public skill and dedicated Agent without disabling the
global tool: a known defect SHALL produce `not_ready`; `unknown` SHALL apply only when no
known defect exists and the authenticated Agent cannot be inspected offline; `ready`
SHALL require all entry checks to pass. Durability SHALL follow legacy
`checkpointer`-over-`database` precedence. Doctor's blocking exit status SHALL depend
only on runtime readiness. Doctor SHALL report next-build/restart requirements and
redact credentials, connection secrets, host user identifiers, full startup
inputs/fingerprints, full internal checkpoint keys, and resolved host workspace paths.

#### Scenario: Ready environment is classified accurately
- **WHEN** doctor inspects a correctly assembled SQLite environment whose local or locally mounted sandbox shares the trusted thread workspace
- **THEN** it reports runtime ready, entry readiness independently, SQLite restart recovery expected, work-unit storage ready, and no source mount inside the sandbox

#### Scenario: Prelaunch readiness is not confused with a running process
- **WHEN** the wrapper supplies a freshly computed SQLite candidate to prelaunch doctor before starting Gateway
- **THEN** doctor labels the result as prelaunch-candidate, verifies it against the same effective config, and does not claim that an existing process inherited that fingerprint

#### Scenario: Missing dedicated Agent is an entry warning
- **WHEN** package, reflected tool, paths, provider, and work-unit storage prerequisites are valid but the dedicated Agent is absent
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

#### Scenario: Sandbox workspace is not transaction-capable
- **WHEN** sandbox selection uses a remote/non-mounted provider or a filesystem whose workspace identity and POSIX transaction primitives cannot be verified
- **THEN** doctor reports runtime not ready with a redacted work-unit-storage issue and runtime returns `work_unit_storage_unavailable` before work-unit artifact, ledger, or checkpoint mutation

#### Scenario: Known provider modes classify identically offline and at runtime
- **WHEN** doctor and runtime inspect LocalSandbox, local-container AIO, provisioner-backed AIO, E2B, BoxLite, and an unrecognized custom provider
- **THEN** both use the same stable mode/reason classifier, local mounted modes are only ready after their applicable probes pass, known unmounted modes are not ready, custom mode is unknown but runtime-not-ready, and no host path is returned

#### Scenario: Runtime provider contradicts its ready config candidate
- **WHEN** offline config classifies a local mode as a ready candidate but the initialized provider does not expose thread-data mounts or the host/sandbox alias probe fails
- **THEN** runtime refuses store construction with `work_unit_storage_unavailable`, performs no research or checkpoint mutation, and does not trust the offline classification alone

#### Scenario: Capability introspection disagrees with an executable primitive
- **WHEN** a platform's feature sets omit descriptor-relative replace support but the actual `os.replace` call would work, or advertise a primitive whose real operation fails
- **THEN** readiness is determined only by the bounded executable probe and never by feature-set membership alone

#### Scenario: Secret-bearing failure is redacted
- **WHEN** a failing fixture contains a database URL, API key, or resolved host workspace path
- **THEN** doctor reports the failing field/provider/capability without printing the secret or host path

