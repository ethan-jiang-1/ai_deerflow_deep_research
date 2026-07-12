"""Contracts for the committed Deep Research public entry skill."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
CONFIGURE_PATH = REPO_ROOT / "agent" / "scripts" / "configure.py"
SKILL_SOURCE = REPO_ROOT / "agent/config/public-skill/deep-research-controller/SKILL.md"
SKILL_RELATIVE = Path("public/deep-research-controller/SKILL.md")

CONFIG_TEXT = """\
config_version: 19
tool_groups: []
tools: []
skills: {}
"""


def _module():
    spec = importlib.util.spec_from_file_location("deep_research_skill_configure", CONFIGURE_PATH)
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
    (root / "skills/custom").mkdir(parents=True)
    (root / "config.yaml").write_text(CONFIG_TEXT, encoding="utf-8")
    (root / "extensions_config.json").write_text('{"mcpServers": {}, "skills": {}}\n', encoding="utf-8")
    env = {
        "DEER_FLOW_CONFIG_PATH": str(root / "config.yaml"),
        "DEER_FLOW_EXTENSIONS_CONFIG_PATH": str(root / "extensions_config.json"),
        "DEER_FLOW_SKILLS_PATH": str(root / "skills"),
        "DEER_FLOW_HOME": str(root / ".runtime-home"),
    }
    return root, env


def test_committed_skill_is_thin_control_tool_entry() -> None:
    content = SKILL_SOURCE.read_text(encoding="utf-8")

    assert len(content.encode("utf-8")) <= 1400
    assert "name: deep-research-controller" in content
    assert "deep_research" in content
    assert "action_unavailable" in content
    for forbidden in (
        "StateGraph",
        "ResearchState",
        "checkpoint",
        "HITL",
        "phase",
        "gate",
        "start",
        "resume",
        "cancel",
        "exclusive",
        "security isolation",
    ):
        assert forbidden.casefold() not in content.casefold()


def test_apply_materializes_exact_committed_skill_and_is_idempotent(
    project: tuple[Path, dict[str, str]],
) -> None:
    root, env = project
    module = _module()
    target = root / "skills" / SKILL_RELATIVE

    first = module.execute_configuration(root, env, mode="apply", online_detector=lambda: False)
    first_bytes = target.read_bytes()
    second = module.execute_configuration(root, env, mode="apply", online_detector=lambda: False)

    assert first_bytes == SKILL_SOURCE.read_bytes()
    assert first.summary["public_skill_status"] == "ready"
    assert second.changed is False
    assert second.summary["public_skill_status"] == "ready"
    assert target.read_bytes() == first_bytes


def test_disabled_owned_skill_is_entry_not_ready_without_invalidating_runtime_config(
    project: tuple[Path, dict[str, str]],
) -> None:
    root, env = project
    module = _module()
    module.execute_configuration(root, env, mode="apply", online_detector=lambda: False)
    extensions_path = root / "extensions_config.json"
    extensions = json.loads(extensions_path.read_text(encoding="utf-8"))
    extensions["skills"]["deep-research-controller"]["enabled"] = False
    extensions_path.write_text(json.dumps(extensions, indent=2) + "\n", encoding="utf-8")

    checked = module.execute_configuration(root, env, mode="check", online_detector=lambda: True)

    assert checked.runtime_config_ready is True
    assert checked.summary["public_skill_status"] == "not_ready"
    assert checked.summary["entry_issues"] == ["public_skill_disabled", "agents_api_disabled"]


def test_same_name_public_skill_drift_is_refused_before_any_write(
    project: tuple[Path, dict[str, str]],
) -> None:
    root, env = project
    target = root / "skills" / SKILL_RELATIVE
    target.parent.mkdir(parents=True)
    target.write_text("foreign same-name content\n", encoding="utf-8")
    config_path = root / "config.yaml"
    extensions_path = root / "extensions_config.json"
    before = (config_path.read_bytes(), extensions_path.read_bytes(), target.read_bytes())
    module = _module()

    with pytest.raises(module.ConfigureError, match="entry.skill_ownership_conflict"):
        module.execute_configuration(root, env, mode="apply", online_detector=lambda: False)

    assert (config_path.read_bytes(), extensions_path.read_bytes(), target.read_bytes()) == before


def test_legacy_custom_skill_is_reported_and_mutation_is_refused(
    project: tuple[Path, dict[str, str]],
) -> None:
    root, env = project
    module = _module()
    module.execute_configuration(root, env, mode="apply", online_detector=lambda: False)
    legacy = root / "skills/custom/deep-research-controller/SKILL.md"
    legacy.parent.mkdir(parents=True)
    legacy.write_bytes(SKILL_SOURCE.read_bytes())
    config_before = (root / "config.yaml").read_bytes()

    checked = module.execute_configuration(root, env, mode="check", online_detector=lambda: True)

    assert checked.runtime_config_ready is True
    assert checked.summary["public_skill_status"] == "not_ready"
    assert checked.summary["entry_issues"] == ["legacy_custom_skill", "agents_api_disabled"]
    with pytest.raises(module.ConfigureError, match="entry.legacy_custom_skill"):
        module.execute_configuration(root, env, mode="apply", online_detector=lambda: False)
    assert (root / "config.yaml").read_bytes() == config_before
    assert legacy.is_file()
