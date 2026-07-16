.PHONY: install lock-check format lint test test-unit test-contract test-viability test-durability test-blocking-io test-postgres demo demo-scripted demo-tui

DEMO_ARGS ?=

install:
	uv sync --extra operations

# Standalone fake lifecycle demo. Zero API, no Gateway, config.yaml,
# model credentials, network access, or TUI installation needed.
demo:
	uv run --extra operations python scripts/demo.py $(DEMO_ARGS)

# Non-interactive equivalent used by CI and quick smoke checks.
demo-scripted:
	uv run --extra operations python scripts/demo.py --scripted $(DEMO_ARGS)

# Real-mode CLI — full 11-phase pipeline with actual LLM + web search.
# Requires ANTHROPIC_API_KEY (and optionally web search tool credentials).
demo-real:
	uv run --env-file .env --extra operations python scripts/demo_real.py $(DEMO_ARGS)

# Non-interactive real-mode for CI (requires credentials).
demo-real-scripted:
	uv run --env-file .env --extra operations python scripts/demo_real.py --scripted $(DEMO_ARGS)

# Standalone real-mode TUI. Requires model API key in .env + TUI dependencies.
# This is not the production DeerFlow Terminal Workbench or generic
# human-input integration.
demo-tui:
	uv run --env-file .env --extra operations --extra demo-tui python scripts/demo_tui.py

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
