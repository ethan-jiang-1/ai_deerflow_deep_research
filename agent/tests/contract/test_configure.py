"""Contracts for structural, reversible Deep Research configuration.

@impl DEC-002
"""

from __future__ import annotations

import importlib.util
import json
import os
import stat
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
CONFIGURE_PATH = REPO_ROOT / "agent" / "scripts" / "configure.py"

CONFIG_TEXT = """\
config_version: 19
provider: &provider
  token: "secret-value"
provider_copy: *provider
tool_groups:
  - name: web
tools:
  - name: web_search
    group: web
    use: example:web
skills: {}
"""

EXTENSIONS_TEXT = '{\r\n    "unknown": {"token": "secret-json"},\r\n    "mcpServers": {},\r\n    "skills": {}\r\n}\r\n'

PROTECTED_CONFIG_TEXT = """\
config_version: 19
database:
  backend: postgres
  postgres:
    url: "postgresql://protected-secret"
checkpointer:
  type: sqlite
  sqlite:
    path: protected-checkpoints.sqlite
sandbox:
  use: protected.sandbox:Provider
  connection:
    token: "sandbox-secret"
agents_api:
  enabled: false
acp_agents:
  protected-acp:
    command: protected-command
subagents:
  enabled: true
  max_concurrent: 7
tool_groups:
  - name: web
    marker: keep-group
tools:
  - name: web_search
    group: web
    use: example:web
    marker: keep-tool
skills: {}
"""


def _module():
    spec = importlib.util.spec_from_file_location("deep_research_configure", CONFIGURE_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def project(tmp_path: Path) -> tuple[Path, dict[str, str]]:
    root = tmp_path / "repo"
    root.mkdir()
    (root / "backend").mkdir()
    (root / "skills/public").mkdir(parents=True)
    (root / "config.yaml").write_text(CONFIG_TEXT, encoding="utf-8")
    (root / "extensions_config.json").write_bytes(EXTENSIONS_TEXT.encode("utf-8"))
    home = root / ".runtime-home"
    env = {
        "DEER_FLOW_CONFIG_PATH": str(root / "config.yaml"),
        "DEER_FLOW_EXTENSIONS_CONFIG_PATH": str(root / "extensions_config.json"),
        "DEER_FLOW_SKILLS_PATH": str(root / "skills"),
        "DEER_FLOW_HOME": str(home),
    }
    return root, env


def test_explicit_targets_match_gateway_paths(project: tuple[Path, dict[str, str]]) -> None:
    root, env = project
    targets = _module().resolve_targets(root, env)

    assert targets.config_path == (root / "config.yaml").resolve()
    assert targets.extensions_path == (root / "extensions_config.json").resolve()
    assert targets.skills_root == (root / "skills").resolve()
    assert targets.deer_flow_home == (root / ".runtime-home").resolve()


def test_root_dotenv_is_loaded_without_overriding_explicit_environment(
    project: tuple[Path, dict[str, str]],
) -> None:
    root, env = project
    selected = root / "selected-config.yaml"
    selected.write_text(CONFIG_TEXT, encoding="utf-8")
    (root / ".env").write_text(
        f"DEER_FLOW_CONFIG_PATH={selected}\n"
        f"DEER_FLOW_EXTENSIONS_CONFIG_PATH={root / 'extensions_config.json'}\n"
        f"DEER_FLOW_SKILLS_PATH={root / 'skills'}\n"
        f"DEER_FLOW_HOME={root / '.dotenv-home'}\n",
        encoding="utf-8",
    )
    module = _module()

    dotenv_targets = module.resolve_targets(root, {})
    explicit_targets = module.resolve_targets(root, env)

    assert dotenv_targets.config_path == selected.resolve()
    assert dotenv_targets.deer_flow_home == (root / ".dotenv-home").resolve()
    assert explicit_targets.config_path == (root / "config.yaml").resolve()
    assert explicit_targets.deer_flow_home == (root / ".runtime-home").resolve()


def test_mismatched_effective_project_root_is_rejected(project: tuple[Path, dict[str, str]]) -> None:
    root, env = project
    alternate = root.parent / "other-project"
    alternate.mkdir()
    env["DEER_FLOW_PROJECT_ROOT"] = str(alternate)
    module = _module()

    with pytest.raises(module.ConfigureError, match="target.project_root_mismatch"):
        module.resolve_targets(root, env)


def test_relative_explicit_runtime_target_is_rejected(project: tuple[Path, dict[str, str]]) -> None:
    root, env = project
    env["DEER_FLOW_CONFIG_PATH"] = "config.yaml"
    module = _module()

    with pytest.raises(module.ConfigureError, match="target.relative_explicit"):
        module.resolve_targets(root, env)


def test_root_backend_shadow_is_rejected_without_explicit_target(project: tuple[Path, dict[str, str]]) -> None:
    root, env = project
    env.pop("DEER_FLOW_CONFIG_PATH")
    (root / "backend/config.yaml").write_text(CONFIG_TEXT, encoding="utf-8")
    module = _module()

    with pytest.raises(module.ConfigureError, match="target.config_ambiguous"):
        module.resolve_targets(root, env)


def test_noncanonical_skills_root_is_rejected(project: tuple[Path, dict[str, str]]) -> None:
    root, env = project
    alternate = root / "alternate-skills"
    alternate.mkdir()
    env["DEER_FLOW_SKILLS_PATH"] = str(alternate)
    module = _module()

    with pytest.raises(module.ConfigureError, match="target.skills_noncanonical"):
        module.resolve_targets(root, env)


def test_apply_is_idempotent_and_preserves_yaml_json_conventions(project: tuple[Path, dict[str, str]]) -> None:
    root, env = project
    module = _module()

    first = module.execute_configuration(root, env, mode="apply", online_detector=lambda: False)
    config_after_first = (root / "config.yaml").read_bytes()
    extensions_after_first = (root / "extensions_config.json").read_bytes()
    second = module.execute_configuration(root, env, mode="apply", online_detector=lambda: False)

    assert first.changed is True
    assert first.runtime_config_ready is True
    assert first.entry_status == "not_ready"
    assert first.summary["public_skill_status"] == "ready"
    assert first.summary["agent_status"] == "not_ready"
    assert second.changed is False
    assert (root / "config.yaml").read_bytes() == config_after_first
    assert (root / "extensions_config.json").read_bytes() == extensions_after_first
    yaml_text = config_after_first.decode("utf-8")
    assert "provider: &provider" in yaml_text
    assert 'token: "secret-value"' in yaml_text
    assert "provider_copy: *provider" in yaml_text
    assert b"\r\n" in extensions_after_first
    assert b'    "unknown"' in extensions_after_first
    parsed = json.loads(extensions_after_first)
    assert list(parsed) == ["unknown", "mcpServers", "skills"]
    assert parsed["unknown"] == {"token": "secret-json"}
    assert parsed["skills"]["deep-research-controller"]["enabled"] is True


@pytest.mark.parametrize("mode", ["check", "dry-run"])
def test_read_only_modes_do_not_write_and_keep_readiness_axes_separate(
    project: tuple[Path, dict[str, str]],
    mode: str,
) -> None:
    root, env = project
    before = ((root / "config.yaml").read_bytes(), (root / "extensions_config.json").read_bytes())

    result = _module().execute_configuration(root, env, mode=mode, online_detector=lambda: True)

    assert result.changed is False
    assert result.would_change is True
    assert result.runtime_config_ready is False
    assert result.entry_status == "not_ready"
    assert ((root / "config.yaml").read_bytes(), (root / "extensions_config.json").read_bytes()) == before


def test_apply_creates_restricted_backup_and_exact_rollback(project: tuple[Path, dict[str, str]]) -> None:
    root, env = project
    module = _module()
    before = ((root / "config.yaml").read_bytes(), (root / "extensions_config.json").read_bytes())

    result = module.execute_configuration(root, env, mode="apply", online_detector=lambda: False)
    assert result.manifest_path is not None
    manifest_mode = stat.S_IMODE(result.manifest_path.stat().st_mode)
    assert manifest_mode == 0o600
    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    for target in manifest["targets"]:
        assert stat.S_IMODE(Path(target["backup_path"]).stat().st_mode) == 0o600

    rollback = module.rollback_configuration(result.manifest_path, online_detector=lambda: False)
    assert rollback.changed is True
    assert (root / "config.yaml").read_bytes() == before[0]
    assert (root / "extensions_config.json").read_bytes() == before[1]


def test_apply_manifest_survives_interrupted_target_write(project: tuple[Path, dict[str, str]], monkeypatch) -> None:
    root, env = project
    module = _module()
    real_replace = module._atomic_replace
    calls = 0

    def fail_second_replace(path: Path, content: bytes) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("simulated write interruption")
        real_replace(path, content)

    monkeypatch.setattr(module, "_atomic_replace", fail_second_replace)
    with pytest.raises(module.ConfigureError, match="write.failed") as error:
        module.execute_configuration(root, env, mode="apply", online_detector=lambda: False)
    assert str(root) not in error.value.detail
    assert "$DEER_FLOW_HOME/" in error.value.detail

    manifests = list((root / ".runtime-home/deep-research/config-history").glob("*/manifest.json"))
    assert len(manifests) == 1
    monkeypatch.setattr(module, "_atomic_replace", real_replace)
    rolled_back = module.rollback_configuration(manifests[0], online_detector=lambda: False)

    assert rolled_back.changed is True
    assert "deep-research-control" not in (root / "config.yaml").read_text(encoding="utf-8")
    assert json.loads((root / "extensions_config.json").read_text(encoding="utf-8"))["skills"] == {}


def test_interrupted_creation_rolls_back_to_missing_extensions_target(
    project: tuple[Path, dict[str, str]], monkeypatch
) -> None:
    root, env = project
    extensions_path = root / "extensions_config.json"
    extensions_path.unlink()
    env.pop("DEER_FLOW_EXTENSIONS_CONFIG_PATH")
    module = _module()
    real_replace = module._atomic_replace
    calls = 0

    def fail_extensions_replace(path: Path, content: bytes) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("simulated extensions creation interruption")
        real_replace(path, content)

    monkeypatch.setattr(module, "_atomic_replace", fail_extensions_replace)
    with pytest.raises(module.ConfigureError, match="write.failed"):
        module.execute_configuration(root, env, mode="apply", online_detector=lambda: False)
    manifest = next((root / ".runtime-home/deep-research/config-history").glob("*/manifest.json"))
    monkeypatch.setattr(module, "_atomic_replace", real_replace)

    module.rollback_configuration(manifest, online_detector=lambda: False)

    assert not extensions_path.exists()
    assert "deep-research-control" not in (root / "config.yaml").read_text(encoding="utf-8")


def test_final_compare_before_replace_catches_edit_after_manifest_creation(
    project: tuple[Path, dict[str, str]], monkeypatch
) -> None:
    root, env = project
    module = _module()
    real_write_restricted = module._write_restricted
    config_path = root / "config.yaml"

    def edit_after_manifest(path: Path, content: bytes) -> None:
        real_write_restricted(path, content)
        if path.name == "manifest.json":
            config_path.write_text(
                config_path.read_text(encoding="utf-8") + "operator_edit: keep\n",
                encoding="utf-8",
            )

    monkeypatch.setattr(module, "_write_restricted", edit_after_manifest)
    with pytest.raises(module.ConfigureError, match="write.concurrent_change"):
        module.execute_configuration(root, env, mode="apply", online_detector=lambda: False)

    assert "operator_edit: keep" in config_path.read_text(encoding="utf-8")
    assert "deep-research-control" not in config_path.read_text(encoding="utf-8")
    assert json.loads((root / "extensions_config.json").read_text(encoding="utf-8"))["skills"] == {}


def test_summary_and_manifest_do_not_expose_secrets_or_full_target_paths(project: tuple[Path, dict[str, str]]) -> None:
    root, env = project
    result = _module().execute_configuration(root, env, mode="dry-run", online_detector=lambda: False)
    summary = json.dumps(result.summary)

    assert "secret-value" not in summary
    assert "secret-json" not in summary
    assert str(root) not in summary
    assert "deep-research-control" in summary
    assert result.summary["changes"] == [
        {
            "target": "$PROJECT_ROOT/config.yaml",
            "operation": "merge",
            "entries": ["deep-research-control", "deep_research"],
        },
        {
            "target": "$PROJECT_ROOT/extensions_config.json",
            "operation": "merge",
            "entries": ["deep-research-controller"],
        },
        {
            "target": "$PROJECT_ROOT/skills/public/deep-research-controller/SKILL.md",
            "operation": "materialize",
            "entries": ["deep-research-controller"],
        },
    ]


def test_cli_read_only_modes_emit_redacted_json_and_runtime_axis_exit_codes(
    project: tuple[Path, dict[str, str]],
) -> None:
    root, env = project
    process_env = os.environ | env

    dry_run = subprocess.run(
        [sys.executable, str(CONFIGURE_PATH), "--project-root", str(root), "--dry-run"],
        check=False,
        capture_output=True,
        text=True,
        env=process_env,
    )
    check_before = subprocess.run(
        [sys.executable, str(CONFIGURE_PATH), "--project-root", str(root), "--check"],
        check=False,
        capture_output=True,
        text=True,
        env=process_env,
    )
    _module().execute_configuration(root, env, mode="apply", online_detector=lambda: False)
    check_after = subprocess.run(
        [sys.executable, str(CONFIGURE_PATH), "--project-root", str(root), "--check"],
        check=False,
        capture_output=True,
        text=True,
        env=process_env,
    )

    assert dry_run.returncode == 0
    assert check_before.returncode == 1
    assert check_after.returncode == 0
    for result in (dry_run, check_before, check_after):
        payload = json.loads(result.stdout)
        assert payload["ok"] is True
        assert str(root) not in result.stdout
        assert "secret-value" not in result.stdout
        assert "Traceback" not in result.stderr


@pytest.mark.parametrize(
    "foreign_entry",
    [
        "tool_groups:\n  - name: deep-research-control\ntools: []\n",
        ("tool_groups: []\ntools:\n  - name: deep_research\n    group: foreign\n    use: foreign.module:tool\n"),
    ],
)
def test_foreign_same_name_ownership_is_rejected_without_writes(
    project: tuple[Path, dict[str, str]],
    foreign_entry: str,
) -> None:
    root, env = project
    config_path = root / "config.yaml"
    config_path.write_text("config_version: 19\n" + foreign_entry, encoding="utf-8")
    before = (config_path.read_bytes(), (root / "extensions_config.json").read_bytes())
    module = _module()

    with pytest.raises(module.ConfigureError, match="config.ownership_conflict"):
        module.execute_configuration(root, env, mode="apply", online_detector=lambda: False)

    assert (config_path.read_bytes(), (root / "extensions_config.json").read_bytes()) == before


@pytest.mark.parametrize(
    ("target", "invalid", "code"),
    [
        ("config.yaml", "tools: [", "config.parse"),
        ("extensions_config.json", "{not-json", "extensions.parse"),
    ],
)
def test_malformed_input_is_rejected_without_partial_write(
    project: tuple[Path, dict[str, str]],
    target: str,
    invalid: str,
    code: str,
) -> None:
    root, env = project
    (root / target).write_text(invalid, encoding="utf-8")
    before = ((root / "config.yaml").read_bytes(), (root / "extensions_config.json").read_bytes())
    module = _module()

    with pytest.raises(module.ConfigureError, match=code):
        module.execute_configuration(root, env, mode="apply", online_detector=lambda: False)

    assert ((root / "config.yaml").read_bytes(), (root / "extensions_config.json").read_bytes()) == before


def test_compare_before_replace_detects_concurrent_change(project: tuple[Path, dict[str, str]]) -> None:
    root, env = project
    extensions_before = (root / "extensions_config.json").read_bytes()
    changed = False

    def operator_edit(path: Path) -> None:
        nonlocal changed
        if not changed and path.name == "config.yaml":
            path.write_text(path.read_text(encoding="utf-8") + "operator_edit: true\n", encoding="utf-8")
            changed = True

    module = _module()
    with pytest.raises(module.ConfigureError, match="write.concurrent_change"):
        module.execute_configuration(
            root,
            env,
            mode="apply",
            online_detector=lambda: False,
            before_replace=operator_edit,
        )

    assert "operator_edit: true" in (root / "config.yaml").read_text(encoding="utf-8")
    assert (root / "extensions_config.json").read_bytes() == extensions_before


def test_online_mutation_is_refused_but_read_only_modes_are_allowed(project: tuple[Path, dict[str, str]]) -> None:
    root, env = project
    module = _module()

    with pytest.raises(module.ConfigureError, match="runtime.online"):
        module.execute_configuration(root, env, mode="apply", online_detector=lambda: True)

    assert module.execute_configuration(root, env, mode="check", online_detector=lambda: True).would_change
    assert module.execute_configuration(root, env, mode="dry-run", online_detector=lambda: True).would_change


def test_default_online_detector_checks_configured_and_known_local_endpoints(
    project: tuple[Path, dict[str, str]], monkeypatch
) -> None:
    root, env = project
    env["DEER_FLOW_GATEWAY_HEALTH_URL"] = "https://configured.example/health"
    env["DEER_FLOW_CHANNELS_GATEWAY_URL"] = "https://channels.example/base"
    env["GATEWAY_PORT"] = "18111"
    env["PORT"] = "12026"
    module = _module()
    checked: list[str] = []

    def reachable(url: str) -> bool:
        checked.append(url)
        return False

    monkeypatch.setattr(module, "_health_endpoint_reachable", reachable)
    monkeypatch.setattr(module, "_project_process_running", lambda _root: False)
    monkeypatch.setattr(module, "_project_container_running", lambda _root: False)

    assert module._default_online_detector(root, env) is False
    assert checked == [
        "https://configured.example/health",
        "https://channels.example/base/health",
        "http://127.0.0.1:18111/health",
        "http://127.0.0.1:12026/health",
    ]


def test_default_online_detector_includes_project_process_and_container_guards(
    project: tuple[Path, dict[str, str]], monkeypatch
) -> None:
    root, env = project
    module = _module()
    monkeypatch.setattr(module, "_health_endpoint_reachable", lambda _url: False)
    monkeypatch.setattr(module, "_project_process_running", lambda _root: True)
    monkeypatch.setattr(module, "_project_container_running", lambda _root: False)
    assert module._default_online_detector(root, env) is True

    monkeypatch.setattr(module, "_project_process_running", lambda _root: False)
    monkeypatch.setattr(module, "_project_container_running", lambda _root: True)
    assert module._default_online_detector(root, env) is True


def test_project_container_guard_uses_compose_working_directory(
    project: tuple[Path, dict[str, str]], monkeypatch
) -> None:
    root, _env = project
    module = _module()
    inspect = [
        {
            "State": {"Running": True},
            "Config": {"Labels": {"com.docker.compose.project.working_dir": str(root)}},
            "Mounts": [],
        }
    ]

    monkeypatch.setattr(
        module.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout=json.dumps(inspect)),
    )
    assert module._project_container_running(root) is True


def test_rollback_uses_default_online_detector_and_project_lock(
    project: tuple[Path, dict[str, str]], monkeypatch
) -> None:
    root, env = project
    module = _module()
    applied = module.execute_configuration(root, env, mode="apply", online_detector=lambda: False)
    lock_calls: list[int] = []
    monkeypatch.setattr(module, "_default_online_detector", lambda detected_root, _env: detected_root == root)
    monkeypatch.setattr(module.fcntl, "flock", lambda _fd, operation: lock_calls.append(operation))

    with pytest.raises(module.ConfigureError, match="runtime.online"):
        module.rollback_configuration(applied.manifest_path)

    assert lock_calls == [module.fcntl.LOCK_EX]


def test_semantic_rollback_preserves_later_unrelated_edit(project: tuple[Path, dict[str, str]]) -> None:
    root, env = project
    module = _module()
    applied = module.execute_configuration(root, env, mode="apply", online_detector=lambda: False)
    config_path = root / "config.yaml"
    config_path.write_text(config_path.read_text(encoding="utf-8") + "operator_edit: keep\n", encoding="utf-8")

    result = module.rollback_configuration(applied.manifest_path, online_detector=lambda: False)
    rolled_back = config_path.read_text(encoding="utf-8")

    assert result.changed is True
    assert "operator_edit: keep" in rolled_back
    assert "deep-research-control" not in rolled_back
    assert "deerflow_deep_research.tool:deep_research_tool" not in rolled_back


def test_semantic_rollback_refuses_changed_owned_entry(project: tuple[Path, dict[str, str]]) -> None:
    root, env = project
    module = _module()
    applied = module.execute_configuration(root, env, mode="apply", online_detector=lambda: False)
    config_path = root / "config.yaml"
    config_path.write_text(
        config_path.read_text(encoding="utf-8").replace(
            "deerflow_deep_research.tool:deep_research_tool",
            "operator.replacement:tool",
        ),
        encoding="utf-8",
    )
    before = config_path.read_bytes()

    with pytest.raises(module.ConfigureError, match="rollback.owned_drift"):
        module.rollback_configuration(applied.manifest_path, online_detector=lambda: False)

    assert config_path.read_bytes() == before


def test_apply_changes_only_project_owned_entries(project: tuple[Path, dict[str, str]]) -> None:
    root, env = project
    config_path = root / "config.yaml"
    extensions_path = root / "extensions_config.json"
    config_path.write_text(PROTECTED_CONFIG_TEXT, encoding="utf-8")
    extensions_path.write_text(
        json.dumps(
            {
                "unknown": {"token": "unknown-secret", "order": [3, 2, 1]},
                "mcpServers": {"protected-mcp": {"command": "mcp-command", "env": {"TOKEN": "mcp-secret"}}},
                "skills": {"unrelated-skill": {"enabled": False, "marker": "keep-skill"}},
            },
            indent=4,
        )
        + "\n",
        encoding="utf-8",
    )
    module = _module()
    before_config, _yaml = module._safe_yaml_load(config_path.read_bytes(), "test")
    before_config = module._plain(before_config)
    before_extensions = json.loads(extensions_path.read_text(encoding="utf-8"))

    result = module.execute_configuration(root, env, mode="apply", online_detector=lambda: False)

    after_config, _yaml = module._safe_yaml_load(config_path.read_bytes(), "test")
    after_config = module._plain(after_config)
    after_extensions = json.loads(extensions_path.read_text(encoding="utf-8"))
    for protected in ("database", "checkpointer", "sandbox", "agents_api", "acp_agents", "subagents"):
        assert after_config[protected] == before_config[protected]
    assert after_config["tool_groups"][0] == before_config["tool_groups"][0]
    assert after_config["tools"][0] == before_config["tools"][0]
    assert after_extensions["unknown"] == before_extensions["unknown"]
    assert after_extensions["mcpServers"] == before_extensions["mcpServers"]
    assert after_extensions["skills"]["unrelated-skill"] == before_extensions["skills"]["unrelated-skill"]
    summary = json.dumps(result.summary)
    assert "postgresql://protected-secret" not in summary
    assert "sandbox-secret" not in summary
    assert "mcp-secret" not in summary


def test_semantic_rollback_preserves_later_protected_setting_edits(
    project: tuple[Path, dict[str, str]],
) -> None:
    root, env = project
    config_path = root / "config.yaml"
    config_path.write_text(PROTECTED_CONFIG_TEXT, encoding="utf-8")
    module = _module()
    applied = module.execute_configuration(root, env, mode="apply", online_detector=lambda: False)
    config_path.write_text(
        config_path.read_text(encoding="utf-8").replace("max_concurrent: 7", "max_concurrent: 11"),
        encoding="utf-8",
    )

    module.rollback_configuration(applied.manifest_path, online_detector=lambda: False)

    rolled_back = config_path.read_text(encoding="utf-8")
    assert "max_concurrent: 11" in rolled_back
    assert "deep-research-control" not in rolled_back
    assert "deerflow_deep_research.tool:deep_research_tool" not in rolled_back
