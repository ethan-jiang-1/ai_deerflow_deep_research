> req: DEC-005

## MODIFIED Requirements

### Requirement: Diagnostics expose readiness without secrets

Doctor SHALL separately report its fingerprint inspection mode, boolean
`runtime_ready`, `entry_ready.status = ready | not_ready | unknown`, and
`durability = same_process | restart_durable | unavailable` with effective provider
kind. Prelaunch-candidate mode SHALL validate the launcher's freshly computed candidate
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

#### Scenario: Secret-bearing failure is redacted
- **WHEN** a failing fixture contains a database URL, API key, or resolved host workspace path
- **THEN** doctor reports the failing field/provider/capability without printing the secret or host path
