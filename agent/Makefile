.PHONY: install lock-check format lint test test-unit test-contract test-viability test-durability test-postgres

install:
	uv sync --extra operations

lock-check:
	uv lock --check

format:
	uv run ruff check . --fix
	uv run ruff format .

lint:
	uv run ruff check .
	uv run ruff format --check .

test:
	uv run --extra operations pytest

test-unit:
	uv run --extra operations pytest tests/unit

test-contract:
	uv run --extra operations pytest tests/contract

test-viability:
	uv run --extra operations pytest \
		tests/integration/test_reflected_runtime_viability.py \
		tests/integration/test_cancellation_viability.py

# File-backed SQLite provider-reopen + real subprocess-restart durability.
# Requires no database server and no Docker.
test-durability:
	uv run --extra operations pytest tests/integration/test_provider_durability.py

# Postgres durability profile is deferred (see openspec/config.yaml tech-stack
# decisions). This target runs the postgres-marked tests, which skip until a
# later change adds the isolated Postgres test service and Compose profile.
test-postgres:
	uv run --extra operations pytest -m postgres

