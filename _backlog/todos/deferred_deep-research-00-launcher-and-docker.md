# DEFERRED: Deep Research change 00 — launcher & Docker deployment tooling

Status: change 00's **runtime substrate is code-complete and verified** —
RuntimeAdapter, GraphHost, isolated checkpoint namespaces, the node-agent bridge,
budgets/policy, the reflected `infra_probe`, and file-backed SQLite durability
(incl. real subprocess-restart recovery), all proven with zero-API tests. What
is deferred here is the **local launcher + Docker/prod deployment tooling**
(tasks 13.4 / 13.5, and the live smoke in 14.3 / 14.4).

## Why deferred (not a gap)

The production / deployment environment for this project is **not set up yet**.
Building and half-verifying a launcher for an environment that does not exist
would overload change 00 with premature deployment burden. This tooling belongs
with the deployment-environment setup (a later change / when prod is
provisioned), not with the runtime substrate. The runtime already runs and is
reviewable without any launcher.

Related deferral: Postgres durability profile —
`deferred_deep-research-00-postgres-profile.md`.

## Deferred work

### 1. Local launcher wrapper + real-service smoke (tasks 13.4, 13.5, 14.3)

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
      checkpoint marker is recovered (already proven at the provider level via
      `make -C agent test-durability`).

### 2. Docker Compose runtime smoke (tasks 13.5 Docker gate, 14.4)

The override file and its rendered-config contract tests are DONE and green
(`agent/tests/contract/test_docker_compose.py`, using `docker compose config`,
which needs no daemon). Outstanding is actually running the container:

- [ ] Finalize the group-6 Compose Gateway prelude by adding the in-container
      prelaunch doctor gate before uvicorn (task 13.5); only `runtime_ready=false`
      stops the container command, entry warnings stay visible.
- [ ] Start Docker Desktop; `docker compose -f docker/docker-compose.yaml -f
      agent/docker/docker-compose.deep-research.yaml up -d`.
- [ ] Verify `/app/agent/src` is mounted read-only and `deerflow_deep_research`
      imports inside the Gateway container.
- [ ] Invoke `infra_probe` through the reflected tool against the containerized
      Gateway; confirm the isolated checkpoint namespace and opaque result.
- [ ] Confirm one-worker readiness and source/sandbox mount separation.
