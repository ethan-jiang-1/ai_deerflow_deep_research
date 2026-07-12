"""Contracts for the stopped-environment preparation core."""

from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
PREPARE_PATH = REPO_ROOT / "agent/scripts/prepare.py"


def _module():
    spec = importlib.util.spec_from_file_location("deep_research_prepare", PREPARE_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def project(tmp_path: Path) -> tuple[Path, dict[str, str]]:
    root = tmp_path / "repo"
    (root / "backend/packages/harness/deerflow").mkdir(parents=True)
    (root / "frontend").mkdir()
    (root / "agent/src/deerflow_deep_research").mkdir(parents=True)
    (root / "scripts").mkdir()
    (root / "skills").mkdir()
    (root / "backend/packages/harness/deerflow/__init__.py").write_text("", encoding="utf-8")
    (root / "agent/src/deerflow_deep_research/__init__.py").write_text("", encoding="utf-8")
    (root / "scripts/detect_uv_extras.py").write_text("", encoding="utf-8")
    (root / "config.example.yaml").write_text("config_version: 19\n", encoding="utf-8")
    (root / "config.yaml").write_text(
        "config_version: 19\n"
        "sandbox:\n"
        "  use: deerflow.sandbox.local:LocalSandboxProvider\n"
        "database:\n"
        "  backend: sqlite\n"
        "  sqlite_dir: relative-db\n",
        encoding="utf-8",
    )
    (root / "extensions_config.json").write_text('{"mcpServers": {}, "skills": {}}\n', encoding="utf-8")
    env = {
        "DEER_FLOW_CONFIG_PATH": str(root / "config.yaml"),
        "DEER_FLOW_EXTENSIONS_CONFIG_PATH": str(root / "extensions_config.json"),
        "DEER_FLOW_PROJECT_ROOT": str(root),
        "DEER_FLOW_HOME": str(root / "backend/.deer-flow"),
    }
    return root, env


def _facts(module, root: Path, **overrides):
    values = {
        "harness_version": "2.1.0",
        "harness_origin": root / "backend/packages/harness/deerflow/__init__.py",
        "module_origin": root / "agent/src/deerflow_deep_research/__init__.py",
    }
    values.update(overrides)
    return module.RuntimeOriginFacts(**values)


def test_current_upstream_command_tokens_are_pinned() -> None:
    module = _module()
    contract = module.upstream_command_contract(REPO_ROOT)
    serve = (REPO_ROOT / "scripts/serve.sh").read_text(encoding="utf-8")

    assert contract.backend_sync_prefix == ("uv", "sync", "--quiet", "--all-packages")
    assert contract.frontend_install == ("pnpm", "install", "--silent")
    assert contract.detect_extras_script == (REPO_ROOT / "scripts/detect_uv_extras.py").resolve()
    assert contract.gateway_pythonpath == "."
    assert "uv sync --quiet --all-packages $UV_EXTRAS_FLAGS" in serve
    assert "pnpm install --silent" in serve
    assert "cd backend && PYTHONPATH=. uv run uvicorn app.gateway.app:app" in serve


def test_root_dotenv_and_runtime_path_defaults_match_local_gateway(project: tuple[Path, dict[str, str]]) -> None:
    root, env = project
    selected = root / "selected.yaml"
    selected.write_text((root / "config.yaml").read_text(encoding="utf-8"), encoding="utf-8")
    dotenv_home = root / "custom-home"
    (root / ".env").write_text(
        f"DEER_FLOW_CONFIG_PATH={selected}\n"
        f"DEER_FLOW_EXTENSIONS_CONFIG_PATH={root / 'extensions_config.json'}\n"
        f"DEER_FLOW_PROJECT_ROOT={root}\n"
        f"DEER_FLOW_HOME={dotenv_home}\n",
        encoding="utf-8",
    )
    module = _module()

    dotenv_context = module.resolve_preparation_context(root, {})
    explicit_context = module.resolve_preparation_context(root, env)

    assert dotenv_context.config_path == selected.resolve()
    assert dotenv_context.deer_flow_home == dotenv_home.resolve()
    assert explicit_context.config_path == (root / "config.yaml").resolve()
    assert explicit_context.project_root == root.resolve()
    assert explicit_context.backend_dir == (root / "backend").resolve()
    assert explicit_context.gateway_cwd == explicit_context.backend_dir
    assert explicit_context.deer_flow_home == (root / "backend/.deer-flow").resolve()
    assert explicit_context.environment["DEER_FLOW_PROJECT_ROOT"] == str(root.resolve())
    assert explicit_context.environment["DEER_FLOW_HOME"] == str((root / "backend/.deer-flow").resolve())


def test_implicit_runtime_path_defaults_are_established(project: tuple[Path, dict[str, str]]) -> None:
    root, _env = project
    context = _module().resolve_preparation_context(root, {})

    assert context.project_root == root.resolve()
    assert context.deer_flow_home == (root / "backend/.deer-flow").resolve()
    assert context.config_path == (root / "config.yaml").resolve()
    assert context.extensions_path == (root / "extensions_config.json").resolve()


def test_root_backend_shadow_disagreement_is_refused(project: tuple[Path, dict[str, str]]) -> None:
    root, _env = project
    (root / "backend/config.yaml").write_text((root / "config.yaml").read_text(encoding="utf-8"), encoding="utf-8")
    module = _module()

    with pytest.raises(module.PrepareError, match="config_target_disagreement"):
        module.resolve_preparation_context(root, {})


@pytest.mark.parametrize(
    ("version_line", "code"),
    [
        ("", "config_version_missing"),
        ("config_version: invalid\n", "config_version_invalid"),
        ("config_version: 18\n", "config_version_older"),
        ("config_version: 20\n", "config_version_newer"),
    ],
)
def test_config_version_mismatch_refuses_before_commands_or_fingerprint(
    project: tuple[Path, dict[str, str]],
    version_line: str,
    code: str,
) -> None:
    root, env = project
    (root / "config.yaml").write_text(
        version_line + "sandbox:\n  use: deerflow.sandbox.local:LocalSandboxProvider\n",
        encoding="utf-8",
    )
    calls: list[object] = []
    module = _module()

    with pytest.raises(module.PrepareError, match=code):
        module.prepare_environment(
            root,
            env,
            quiescence_confirmed=True,
            runner=lambda spec: calls.append(spec),
            runtime_probe=lambda context: calls.append(("probe", context)),
            candidate_builder=lambda context: calls.append(("candidate", context)),
        )

    assert calls == []


def test_preparation_refuses_without_caller_quiescence(project: tuple[Path, dict[str, str]]) -> None:
    root, env = project
    calls: list[object] = []
    module = _module()

    with pytest.raises(module.PrepareError, match="quiescence_required"):
        module.prepare_environment(
            root,
            env,
            quiescence_confirmed=False,
            runner=lambda spec: calls.append(spec),
            runtime_probe=lambda context: calls.append(("probe", context)),
            candidate_builder=lambda context: calls.append(("candidate", context)),
        )

    assert calls == []


def test_sync_frontend_editable_install_origin_check_and_candidate_order(
    project: tuple[Path, dict[str, str]],
) -> None:
    root, env = project
    module = _module()
    events: list[str] = []
    specs: list[object] = []

    def runner(spec):
        events.append(spec.stage)
        specs.append(spec)
        stdout = "--extra postgres\n" if spec.stage == "detect_extras" else ""
        return module.CommandOutcome(returncode=0, stdout=stdout, stderr="")

    def probe(context):
        events.append("runtime_probe")
        return _facts(module, root)

    def candidate(context):
        events.append("candidate")
        assert context.gateway_cwd == root / "backend"
        return f"v1:{'a' * 64}"

    result = module.prepare_environment(
        root,
        env,
        quiescence_confirmed=True,
        runner=runner,
        runtime_probe=probe,
        candidate_builder=candidate,
    )

    assert events == [
        "detect_extras",
        "backend_sync",
        "frontend_install",
        "editable_install",
        "runtime_probe",
        "candidate",
    ]
    assert specs[0].argv == (sys.executable, str(root / "scripts/detect_uv_extras.py"))
    assert specs[1].argv == ("uv", "sync", "--quiet", "--all-packages", "--extra", "postgres")
    assert specs[1].cwd == root / "backend"
    assert specs[2].argv == ("pnpm", "install", "--silent")
    assert specs[2].cwd == root / "frontend"
    assert specs[3].argv == (
        "uv",
        "pip",
        "install",
        "--python",
        str(root / "backend/.venv/bin/python"),
        "--no-deps",
        "--editable",
        str(root / "agent"),
    )
    assert specs[3].cwd == root / "backend"
    assert all(spec.environment["PYTHONPATH"] == "." for spec in specs)
    assert result.machine == {"startup_fingerprint": f"v1:{'a' * 64}"}


@pytest.mark.parametrize(
    "facts_override",
    [
        {"harness_version": "2.0.9"},
        {"harness_version": "2.2.0"},
        {"harness_origin": Path("/foreign/deerflow/__init__.py")},
        {"module_origin": Path("/foreign/deerflow_deep_research/__init__.py")},
    ],
)
def test_incompatible_harness_or_wrong_module_origin_stops_before_candidate(
    project: tuple[Path, dict[str, str]],
    facts_override: dict,
) -> None:
    root, env = project
    module = _module()
    events: list[str] = []

    def runner(spec):
        events.append(spec.stage)
        return module.CommandOutcome(0, "", "")

    with pytest.raises(module.PrepareError, match="runtime_origin_invalid"):
        module.prepare_environment(
            root,
            env,
            quiescence_confirmed=True,
            runner=runner,
            runtime_probe=lambda context: _facts(module, root, **facts_override),
            candidate_builder=lambda context: events.append("candidate"),
        )

    assert events == ["detect_extras", "backend_sync", "frontend_install", "editable_install"]


def test_candidate_uses_gateway_cwd_for_relative_sqlite_and_is_secret_free(
    project: tuple[Path, dict[str, str]], monkeypatch
) -> None:
    root, env = project
    module = _module()
    context = module.resolve_preparation_context(root, env)
    monkeypatch.setenv("DEER_FLOW_EXTENSIONS_CONFIG_PATH", str(root / "extensions_config.json"))

    candidate = module.build_startup_candidate(context)

    old_cwd = Path.cwd()
    try:
        os.chdir(root / "backend")
        from deerflow.config.app_config import AppConfig

        from deerflow_deep_research.runtime.startup_snapshot import capture_startup_fingerprint

        gateway_config = AppConfig.from_file(str(root / "config.yaml"))
        expected = capture_startup_fingerprint(gateway_config, worker_value=None)
    finally:
        os.chdir(old_cwd)
    assert candidate == expected
    assert re_full_fingerprint(candidate)
    assert "relative-db" not in json.dumps({"startup_fingerprint": candidate})


def re_full_fingerprint(value: str) -> bool:
    return value.startswith("v1:") and len(value) == 67 and all(char in "0123456789abcdef" for char in value[3:])
