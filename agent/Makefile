.PHONY: install lock-check format lint test test-unit test-contract test-viability test-durability test-blocking-io test-postgres demo demo-scripted demo-real demo-tui demo-tui-real

DEMO_ARGS ?=

install:
	uv sync --extra operations

# Standalone Change 01 lifecycle demo. It needs no Gateway, config.yaml,
# model credentials, network access, or TUI installation.
demo:
	uv run --extra operations python scripts/demo.py $(DEMO_ARGS)

# Non-interactive equivalent used by CI and quick smoke checks.
demo-scripted:
	uv run --extra operations python scripts/demo.py --scripted $(DEMO_ARGS)

# Real non-agent nodes (hitl2, rerun, readiness, final_delivery) + scripted HITL.
demo-real:
	uv run --extra operations python scripts/demo.py --scripted --real

# Standalone visual shell over the same zero-API lifecycle. This is not the
# production DeerFlow Terminal Workbench or generic human-input integration.
demo-tui:
	uv run --extra operations --extra demo-tui python scripts/demo_tui.py

demo-tui-real:
	uv run --extra operations --extra demo-tui python scripts/demo_tui.py --real

lock-check:
	uv lock --check

format:
	uv run ruff check . --fix
	uv run ruff format .

lint:
	uv run ruff check .
	uv run ruff format --check .

test:
	uv run --extra operations --extra demo-tui pytest

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

# Deterministic event-loop guard for lifecycle dispatch, nested graph Send
# fan-in, provider cleanup, and outer Command projection.
test-blocking-io:
	uv run --extra operations pytest tests/blocking_io

# Postgres durability profile is deferred (see openspec/config.yaml tech-stack
# decisions). This target runs the postgres-marked tests, which skip until a
# later change adds the isolated Postgres test service and Compose profile.
test-postgres:
	uv run --extra operations pytest -m postgres
