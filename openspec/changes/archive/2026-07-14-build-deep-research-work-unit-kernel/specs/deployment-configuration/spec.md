> req: DEC-005

## MODIFIED Requirements

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
