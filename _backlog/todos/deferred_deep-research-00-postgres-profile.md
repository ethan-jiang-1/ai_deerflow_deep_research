# DEFERRED: Deep Research change 00 — Postgres durability profile

Status: change 00's durable checkpoint store is **file-backed SQLite**, and its
provider-reopen + real subprocess-restart durability are GREEN
(`agent/tests/integration/test_provider_durability.py`, `make -C agent
test-durability`) with no database server and no Docker. **Postgres is deferred**
(task 8.6 Postgres part).

## Why deferred (not a gap)

Postgres is a multi-worker / production checkpoint backend. Change 00 explicitly
chose file-backed SQLite as the durable store (see `openspec/config.yaml`
tech-stack decisions) because Deep Research is a long, intermittent task that
must survive Gateway restarts, and SQLite delivers that as a single on-disk file
with zero external services. Postgres provider verification requires a running
database service (and a container), which belongs with the deployment-environment
setup — the same reason the launcher/Docker work is deferred
(`deferred_deep-research-00-launcher-and-docker.md`).

The provider classifier already covers Postgres precedence and durability, and
`agent/Makefile test-postgres` exists and runs the postgres-marked tests, which
currently skip via `@pytest.mark.postgres`.

## Deferred work (task 8.6 Postgres part)

- [ ] Add an isolated, committed Postgres test Compose profile
      (`agent/docker/docker-compose.postgres-test.yaml`) that stands up a
      throwaway Postgres for tests only.
- [ ] Make the postgres-marked provider-reopen + subprocess-restart tests real
      against that service (mirror the SQLite durability tests), replacing the
      current `pytest.mark.postgres` skip.
- [ ] Wire `make -C agent test-postgres` to bring the profile up, run the
      postgres-marked tests, and tear it down.
- [ ] Confirm the effective-provider classifier's `restart_durable` claim and the
      legacy-`checkpointer`-over-`database` precedence hold against a real
      Postgres saver.
