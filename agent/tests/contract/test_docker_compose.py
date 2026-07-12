"""Contract for the Deep Research Docker Compose override.

@impl DEC-001

Static checks (always run) pin the one-command delta against the *current*
upstream Gateway command so upstream drift is caught. Rendered checks (skipped
when ``docker compose`` is unavailable) prove base-first ordering resolves the
read-only ``agent/src`` source to ``<repo>/agent/src`` and that reversing the
file order violates that source-origin contract.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest
from ruamel.yaml import YAML

REPO_ROOT = Path(__file__).resolve().parents[3]
BASE = REPO_ROOT / "docker" / "docker-compose.yaml"
OVERRIDE = REPO_ROOT / "agent" / "docker" / "docker-compose.deep-research.yaml"
AGENT_SRC = REPO_ROOT / "agent" / "src"

FINGERPRINT_EXPORT = "export DEER_FLOW_DEEP_RESEARCH_STARTUP_FINGERPRINT=$$("
FINGERPRINT_MODULE = "deerflow_deep_research.runtime.startup_snapshot"
DOWNSTREAM_PYTHONPATH = "PYTHONPATH=/app/agent/src:."

_yaml = YAML(typ="safe")


def _load(path: Path):
    with path.open(encoding="utf-8") as handle:
        return _yaml.load(handle)


def _gateway_command(document) -> str:
    command = document["services"]["gateway"]["command"]
    return command if isinstance(command, str) else " ".join(command)


def _upstream_uvicorn_invocation() -> str:
    """The exact upstream server launch, derived from the current base compose."""
    command = _gateway_command(_load(BASE))
    marker = "uv run uvicorn"
    assert marker in command, "upstream Gateway command no longer launches uvicorn via uv"
    return command[command.index(marker) :].rstrip('"')


# ── Static one-command-delta contract ───────────────────────────────────────


def test_override_defines_only_the_gateway_service() -> None:
    # Restricting the override to `gateway` is also what keeps host source out of
    # every other service (the research sandbox is never given an agent/src mount).
    override = _load(OVERRIDE)
    assert set(override["services"]) == {"gateway"}


def test_override_mounts_agent_src_read_only() -> None:
    volumes = _load(OVERRIDE)["services"]["gateway"]["volumes"]
    assert "../agent/src:/app/agent/src:ro" in volumes


def test_override_preserves_upstream_uvicorn_invocation() -> None:
    command = _gateway_command(_load(OVERRIDE))
    assert _upstream_uvicorn_invocation() in command


def test_override_prefixes_downstream_pythonpath() -> None:
    command = _gateway_command(_load(OVERRIDE))
    assert DOWNSTREAM_PYTHONPATH in command


def test_override_exports_container_startup_fingerprint_prelude() -> None:
    command = _gateway_command(_load(OVERRIDE))
    assert FINGERPRINT_EXPORT in command
    assert FINGERPRINT_MODULE in command


def test_override_does_not_defer_to_diagnostics_before_group_13() -> None:
    # Group 6 establishes only the source/fingerprint prelude; the pre-uvicorn
    # doctor gate is added by group 13. Guard against pulling it in early.
    command = _gateway_command(_load(OVERRIDE))
    assert "runtime.diagnostics" not in command


# ── Rendered source-origin contract ─────────────────────────────────────────


def _docker_compose_available() -> bool:
    if shutil.which("docker") is None:
        return False
    try:
        result = subprocess.run(
            ["docker", "compose", "version"],
            capture_output=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 0


requires_compose = pytest.mark.skipif(
    not _docker_compose_available(),
    reason="docker compose is unavailable",
)


@pytest.fixture()
def render_env(tmp_path: Path):
    """Provide env vars and the repo env files the base compose declares.

    The base Gateway/frontend services declare ``env_file`` entries at the repo
    root and ``frontend/``; ``docker compose config`` refuses to render without
    them. Create empty placeholders only when absent and remove only what we
    created, so a developer's real env files are never touched.
    """
    created: list[Path] = []
    for relative in (".env", "frontend/.env"):
        candidate = REPO_ROOT / relative
        if not candidate.exists():
            candidate.write_text("", encoding="utf-8")
            created.append(candidate)
    env = {
        **os.environ,
        "DEER_FLOW_CONFIG_PATH": str(tmp_path / "config.yaml"),
        "DEER_FLOW_EXTENSIONS_CONFIG_PATH": str(tmp_path / "extensions_config.json"),
        "DEER_FLOW_HOME": str(tmp_path / "home"),
        "DEER_FLOW_INTERNAL_AUTH_TOKEN": "test-token",
        "DEER_FLOW_REPO_ROOT": str(tmp_path),
        "GATEWAY_WORKERS": "1",
    }
    try:
        yield env
    finally:
        for candidate in created:
            candidate.unlink(missing_ok=True)


def _render(env: dict[str, str], *files: Path) -> subprocess.CompletedProcess[str]:
    args = ["docker", "compose"]
    for file in files:
        args += ["-f", str(file)]
    args.append("config")
    return subprocess.run(
        args,
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=90,
    )


def _rendered_agent_src(config_text: str) -> tuple[str | None, bool]:
    document = _yaml.load(config_text)
    if not document:
        return None, False
    for volume in document["services"]["gateway"].get("volumes", []):
        if volume.get("target") == "/app/agent/src":
            return volume.get("source"), volume.get("read_only") is True
    return None, False


@requires_compose
def test_rendered_base_first_resolves_agent_src_to_repo(render_env) -> None:
    result = _render(render_env, BASE, OVERRIDE)
    assert result.returncode == 0, result.stderr
    source, read_only = _rendered_agent_src(result.stdout)
    assert source == str(AGENT_SRC)
    assert read_only is True


@requires_compose
def test_rendered_reversed_order_violates_source_origin(render_env) -> None:
    result = _render(render_env, OVERRIDE, BASE)
    # Reversed order is unsupported: it must not yield the canonical
    # <repo>/agent/src override (compose either fails to render, or resolves the
    # relative source against agent/docker/ and/or falls back to the upstream
    # command). Either way it must differ from the base-first result.
    if result.returncode != 0:
        return
    source, _ = _rendered_agent_src(result.stdout)
    assert source != str(AGENT_SRC)
