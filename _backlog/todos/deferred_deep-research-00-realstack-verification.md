# TODO: Deep Research change 00 — deferred deployment/launcher work

Status: change 00's **runtime substrate is code-complete and fully verified** —
RuntimeAdapter, GraphHost, isolated checkpoint namespaces, the node-agent bridge,
budgets/policy, the reflected `infra_probe`, and **file-backed SQLite durability
(incl. real subprocess-restart recovery)**. What remains is the local launcher +
Docker/prod deployment tooling.

## Why this is deferred (not a gap)

The deployment/launcher tasks (project-owned `serve.sh`, `agent/Makefile`
dev/prod/daemon targets, in-container doctor gate, live dev/prod/container smoke)
are being deferred **on purpose**: the production / deployment environment for
this project is not set up yet. Building and half-verifying a launcher for an
environment that does not exist would overload change 00 with premature
deployment burden. This tooling belongs with the deployment-environment setup
(a later change / when prod is provisioned), not with the runtime substrate.

The runtime already runs and is proven with zero-API tests, real SQLite
durability, and the reflected probe — no launcher is required to exercise or
review it.

## Decided tech-stack context (see openspec/config.yaml)

- Durable checkpoint store = **file-backed SQLite** (long, intermittent task must
  survive Gateway restarts). Real SQLite provider-reopen AND subprocess-restart
  durability are GREEN via `agent/tests/integration/test_provider_durability.py`
  (`make -C agent test-durability`), needing no DB server and no Docker.
- **Postgres is deferred** to a later change (multi-worker/production). `make -C
  agent test-postgres` runs the postgres-marked tests, which currently skip.

## Deferred until the deployment environment is set up

### 1. Docker Compose runtime smoke (tasks 6.x runtime, 14.4)

The override file and its rendered-config contract tests are DONE and green
(`agent/tests/contract/test_docker_compose.py`, using `docker compose config`,
which needs no daemon). Outstanding is actually running the container:

- [ ] Start Docker Desktop; `docker compose -f docker/docker-compose.yaml -f
      agent/docker/docker-compose.deep-research.yaml up -d`.
- [ ] Verify `/app/agent/src` is mounted read-only and `deerflow_deep_research`
      imports inside the Gateway container.
- [ ] Invoke `infra_probe` through the reflected tool against the containerized
      Gateway; confirm the isolated checkpoint namespace and opaque result.
- [ ] Confirm one-worker readiness and source/sandbox mount separation.
- [ ] After the in-container prelaunch doctor gate is added (task 13.5), confirm
      only `runtime_ready=false` stops the container command and entry warnings
      remain visible.

### 2. Local launcher wrapper + real-service smoke (tasks 13.4, 13.5, 14.3)

- [ ] Implement `agent/scripts/serve.sh` (read-only preflight → upstream stop →
      `prepare.py` → export startup candidate → prelaunch doctor → delegate
      upstream start with `UV_NO_SYNC=1 --skip-install`) and the `agent/Makefile`
      configure/doctor/dev/prod/daemon/restart/stop targets.
- [ ] Add the wrapper/Compose-command contract tests (13.4): direct stop
      delegation with no prework; version/target-disagreement refusal before
      shared mutation; `UV_NO_SYNC=1` + `--skip-install` forwarding; Docker
      candidate → in-container doctor → uvicorn ordering.
- [ ] Run local dev + local prod smoke against isolated config; invoke
      `infra_probe`; restart the Gateway on file-SQLite and confirm the previous
      checkpoint marker is recovered (already proven at the provider level).

### 3. Postgres durability profile (tasks 8.6 Postgres part)

- [ ] Add the isolated committed Postgres test Compose profile and make the
      postgres-marked provider-reopen + subprocess-restart tests real (currently
      skipped via `@pytest.mark.postgres`).
