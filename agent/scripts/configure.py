#!/usr/bin/env python3
"""Structurally materialize Deep Research configuration with guarded rollback.

@impl DEC-002
@impl DEC-003
@impl DEC-004
"""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import io
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import uuid
from collections.abc import Callable, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlsplit, urlunsplit

from dotenv import dotenv_values
from ruamel.yaml import YAML

OWNER_KEY = "x-deerflow-deep-research-owner"
OWNER_VERSION = "v1"
GROUP_NAME = "deep-research-control"
TOOL_NAME = "deep_research"
SKILL_NAME = "deep-research-controller"
AGENT_NAME = "deep-research"
AGENT_DESCRIPTION = "Graph-controlled Deep Research"
AGENT_NAME_PATTERN = re.compile(r"^[A-Za-z0-9-]+$")
SCRIPT_ROOT = Path(__file__).resolve().parents[1]
CONFIG_FRAGMENT = SCRIPT_ROOT / "config" / "deerflow.fragment.yaml"
EXTENSIONS_FRAGMENT = SCRIPT_ROOT / "config" / "extensions.fragment.json"
PUBLIC_SKILL_SOURCE = SCRIPT_ROOT / "config" / "public-skill" / SKILL_NAME / "SKILL.md"
AGENT_CONFIG_SOURCE = SCRIPT_ROOT / "config" / "agent-template" / "config.yaml"
AGENT_SOUL_SOURCE = SCRIPT_ROOT / "config" / "agent-template" / "SOUL.md"
Mode = Literal["apply", "check", "dry-run"]


class ConfigureError(RuntimeError):
    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"[{code}] {detail}")
        self.code = code
        self.detail = detail


@dataclass(frozen=True)
class ConfigTargets:
    project_root: Path
    config_path: Path
    extensions_path: Path
    skills_root: Path
    deer_flow_home: Path
    agents_api_enabled: bool


@dataclass(frozen=True)
class ConfigureResult:
    changed: bool
    would_change: bool
    runtime_config_ready: bool
    entry_status: str
    manifest_path: Path | None
    summary: dict[str, Any]


@dataclass(frozen=True)
class _TargetPlan:
    path: Path
    kind: str
    existed_before: bool
    before: bytes
    after: bytes
    owned_after: dict[str, Any]

    @property
    def changed(self) -> bool:
        return self.before != self.after


def _canonical(path: Path, *, require_exists: bool = False) -> Path:
    try:
        return path.resolve(strict=require_exists)
    except OSError as exc:
        raise ConfigureError("target.resolve", f"cannot resolve target {path.name}") from exc


def _explicit_file(env: Mapping[str, str], key: str) -> Path | None:
    value = env.get(key)
    if not value:
        return None
    selected = Path(value)
    if not selected.is_absolute():
        raise ConfigureError("target.relative_explicit", f"{key} must be absolute after launch-environment loading")
    path = _canonical(selected, require_exists=True)
    if not path.is_file():
        raise ConfigureError("target.not_file", f"{key} does not select a file")
    return path


def _effective_env(project_root: Path, env: Mapping[str, str] | None) -> dict[str, str]:
    dotenv_path = project_root / ".env"
    try:
        dotenv = dotenv_values(dotenv_path) if dotenv_path.is_file() else {}
    except (OSError, ValueError) as exc:
        raise ConfigureError("environment.dotenv_parse", "root .env could not be parsed") from exc
    effective = {str(key): str(value) for key, value in dotenv.items() if value is not None}
    supplied = os.environ if env is None else env
    effective.update({str(key): str(value) for key, value in supplied.items()})
    return effective


def _unambiguous_existing(candidates: tuple[Path, ...], code: str, *, default: Path | None = None) -> Path:
    existing = {_canonical(path, require_exists=True) for path in candidates if path.exists()}
    if len(existing) > 1:
        raise ConfigureError(code, "multiple implicit targets exist; set the explicit environment path")
    if existing:
        return next(iter(existing))
    if default is not None:
        return _canonical(default)
    raise ConfigureError("target.missing", "required runtime target does not exist")


def _safe_yaml_load(raw: bytes, code: str) -> tuple[Any, YAML]:
    yaml = YAML(typ="rt")
    yaml.preserve_quotes = True
    yaml.indent(mapping=2, sequence=4, offset=2)
    try:
        data = yaml.load(raw.decode("utf-8"))
    except Exception as exc:
        raise ConfigureError(code, "configuration is not valid YAML") from exc
    if data is None:
        data = {}
    if not isinstance(data, dict):
        raise ConfigureError(code, "configuration root must be a mapping")
    return data, yaml


def _yaml_dump(data: Any, yaml: YAML) -> bytes:
    stream = io.StringIO()
    yaml.dump(data, stream)
    return stream.getvalue().encode("utf-8")


def _json_convention(raw: bytes) -> tuple[str, str]:
    text = raw.decode("utf-8")
    newline = "\r\n" if "\r\n" in text else "\n"
    match = re.search(r"(?:\r?\n)([ \t]+)\"", text)
    indent = match.group(1) if match else "  "
    return newline, indent


def _json_dump(data: Any, raw_before: bytes) -> bytes:
    newline, indent = _json_convention(raw_before)
    text = json.dumps(data, ensure_ascii=False, indent=indent)
    return (text.replace("\n", newline) + newline).encode("utf-8")


def _plain(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_plain(item) for item in value]
    return value


def _load_fragments() -> tuple[dict[str, Any], dict[str, Any]]:
    yaml_data, _ = _safe_yaml_load(CONFIG_FRAGMENT.read_bytes(), "fragment.config_parse")
    try:
        extensions = json.loads(EXTENSIONS_FRAGMENT.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ConfigureError("fragment.extensions_parse", "extensions fragment is invalid") from exc
    return _plain(yaml_data), extensions


def resolve_targets(project_root: Path, env: Mapping[str, str] | None = None) -> ConfigTargets:
    root = _canonical(project_root, require_exists=True)
    effective_env = _effective_env(root, env)
    configured_root = effective_env.get("DEER_FLOW_PROJECT_ROOT")
    if configured_root:
        selected_root = Path(configured_root)
        if not selected_root.is_absolute() or _canonical(selected_root, require_exists=True) != root:
            raise ConfigureError(
                "target.project_root_mismatch",
                "DEER_FLOW_PROJECT_ROOT does not select the configured project",
            )
    config_path = _explicit_file(effective_env, "DEER_FLOW_CONFIG_PATH") or _unambiguous_existing(
        (root / "config.yaml", root / "backend" / "config.yaml"),
        "target.config_ambiguous",
    )
    extensions_path = _explicit_file(
        effective_env,
        "DEER_FLOW_EXTENSIONS_CONFIG_PATH",
    ) or _unambiguous_existing(
        (root / "extensions_config.json", root / "backend" / "extensions_config.json"),
        "target.extensions_ambiguous",
        default=root / "extensions_config.json",
    )

    config_data, _ = _safe_yaml_load(config_path.read_bytes(), "config.parse")
    skills_config = config_data.get("skills") or {}
    if not isinstance(skills_config, dict):
        raise ConfigureError("config.parse", "skills must be a mapping")
    agents_api_config = config_data.get("agents_api") or {}
    if not isinstance(agents_api_config, dict) or not isinstance(agents_api_config.get("enabled", False), bool):
        raise ConfigureError("config.parse", "agents_api.enabled must be a boolean")
    configured_skills = effective_env.get("DEER_FLOW_SKILLS_PATH") or skills_config.get("path")
    skills_root = Path(str(configured_skills)) if configured_skills else root / "skills"
    if not skills_root.is_absolute():
        skills_root = root / skills_root
    skills_root = _canonical(skills_root)
    canonical_skills = _canonical(root / "skills")
    if skills_root != canonical_skills:
        raise ConfigureError(
            "target.skills_noncanonical", "effective skills root is not the supported repository mount"
        )

    home_value = effective_env.get("DEER_FLOW_HOME")
    deer_flow_home = _canonical(Path(home_value) if home_value else root / "backend" / ".deer-flow")
    return ConfigTargets(
        root,
        config_path,
        extensions_path,
        skills_root,
        deer_flow_home,
        agents_api_config.get("enabled", False),
    )


def _find_named(entries: Any, name: str, section: str) -> dict[str, Any] | None:
    if entries is None:
        return None
    if not isinstance(entries, list):
        raise ConfigureError("config.parse", f"{section} must be a list")
    matches = [entry for entry in entries if isinstance(entry, dict) and entry.get("name") == name]
    if len(matches) > 1:
        raise ConfigureError("config.ownership_conflict", f"duplicate project-owned name in {section}")
    return matches[0] if matches else None


def _merge_owned_entry(data: dict[str, Any], section: str, expected: dict[str, Any]) -> dict[str, Any]:
    entries = data.setdefault(section, [])
    existing = _find_named(entries, expected["name"], section)
    if existing is None:
        entries.append(expected.copy())
        return expected.copy()
    if existing.get(OWNER_KEY) != OWNER_VERSION:
        raise ConfigureError("config.ownership_conflict", f"foreign entry owns {expected['name']}")
    required = {key: value for key, value in expected.items() if key != OWNER_KEY}
    if any(existing.get(key) != value for key, value in required.items()):
        raise ConfigureError("config.ownership_conflict", f"owned entry drifted: {expected['name']}")
    return _plain(existing)


def _plan_config(path: Path, fragment: dict[str, Any]) -> _TargetPlan:
    before = path.read_bytes()
    data, yaml = _safe_yaml_load(before, "config.parse")
    group = _merge_owned_entry(data, "tool_groups", fragment["tool_groups"][0])
    tool = _merge_owned_entry(data, "tools", fragment["tools"][0])
    return _TargetPlan(path, "yaml", True, before, _yaml_dump(data, yaml), {"group": group, "tool": tool})


def _plan_extensions(path: Path, fragment: dict[str, Any]) -> _TargetPlan:
    existed_before = path.exists()
    before = path.read_bytes() if existed_before else b"{}\n"
    try:
        data = json.loads(before.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ConfigureError("extensions.parse", "extensions configuration is not valid JSON") from exc
    if not isinstance(data, dict):
        raise ConfigureError("extensions.parse", "extensions root must be an object")
    skills = data.setdefault("skills", {})
    if not isinstance(skills, dict):
        raise ConfigureError("extensions.parse", "extensions skills must be an object")
    expected = fragment["skills"][SKILL_NAME]
    existing = skills.get(SKILL_NAME)
    if existing is None:
        skills[SKILL_NAME] = expected.copy()
        owned = expected.copy()
    else:
        if not isinstance(existing, dict) or existing.get(OWNER_KEY) != OWNER_VERSION:
            raise ConfigureError("extensions.ownership_conflict", f"foreign entry owns {SKILL_NAME}")
        existing["enabled"] = True
        owned = _plain(existing)
    return _TargetPlan(path, "json", existed_before, before, _json_dump(data, before), {"skill": owned})


def _plan_public_skill(targets: ConfigTargets) -> _TargetPlan:
    try:
        source = PUBLIC_SKILL_SOURCE.read_bytes()
    except OSError as exc:
        raise ConfigureError("entry.skill_source_missing", "committed public skill source is unavailable") from exc
    path = targets.skills_root / "public" / SKILL_NAME / "SKILL.md"
    parent = path.parent
    if parent.exists() and not _is_within(parent, targets.skills_root):
        raise ConfigureError("entry.skill_path_invalid", "public skill path escapes the canonical skills root")
    existed_before = path.exists()
    before = path.read_bytes() if existed_before else b""
    if existed_before and before != source:
        raise ConfigureError("entry.skill_ownership_conflict", f"same-name public skill drifted: {SKILL_NAME}")
    if not existed_before and parent.exists() and any(parent.iterdir()):
        raise ConfigureError(
            "entry.skill_ownership_conflict", f"same-name public skill directory drifted: {SKILL_NAME}"
        )
    return _TargetPlan(
        path,
        "file",
        existed_before,
        before,
        source,
        {"sha256": _sha256(source), "entry": SKILL_NAME},
    )


def validate_agent_name(name: str) -> str:
    if not isinstance(name, str) or not AGENT_NAME_PATTERN.fullmatch(name):
        raise ConfigureError("entry.agent_name_invalid", "Agent name must use only letters, digits, and hyphens")
    return name.lower()


def _agent_templates() -> tuple[dict[str, Any], bytes, bytes]:
    try:
        config_bytes = AGENT_CONFIG_SOURCE.read_bytes()
        soul_bytes = AGENT_SOUL_SOURCE.read_bytes()
    except OSError as exc:
        raise ConfigureError("entry.agent_source_missing", "committed Agent template is unavailable") from exc
    config, _yaml = _safe_yaml_load(config_bytes, "entry.agent_template_invalid")
    plain_config = _plain(config)
    expected = {
        "name": AGENT_NAME,
        "description": AGENT_DESCRIPTION,
        "tool_groups": [GROUP_NAME],
        "skills": [SKILL_NAME],
    }
    if plain_config != expected or validate_agent_name(str(plain_config.get("name", ""))) != AGENT_NAME:
        raise ConfigureError("entry.agent_template_invalid", "committed Agent config has an incompatible shape")
    if not soul_bytes.decode("utf-8").strip():
        raise ConfigureError("entry.agent_template_invalid", "committed Agent SOUL is empty")
    return expected, config_bytes, soul_bytes


def authenticated_agent_api_fixture() -> dict[str, Any]:
    config, _config_bytes, soul_bytes = _agent_templates()
    soul = soul_bytes.decode("utf-8").strip()
    request = {
        "name": config["name"],
        "description": config["description"],
        "tool_groups": config["tool_groups"],
        "skills": config["skills"],
        "soul": soul,
    }
    return {
        "method": "POST",
        "path": "/api/agents",
        "status_code": 201,
        "request": request,
        "response": {**request, "model": None},
    }


def _auth_disabled_requested(env: Mapping[str, str]) -> bool:
    return env.get("DEER_FLOW_AUTH_DISABLED") == "1"


def _production_requested(env: Mapping[str, str]) -> bool:
    return any(env.get(key, "").strip().lower() in {"prod", "production"} for key in ("DEER_FLOW_ENV", "ENVIRONMENT"))


def _agent_plans(targets: ConfigTargets, env: Mapping[str, str]) -> tuple[_TargetPlan, ...]:
    if not _auth_disabled_requested(env) or _production_requested(env):
        return ()
    _config, config_bytes, soul_bytes = _agent_templates()
    agent_dir = targets.deer_flow_home / "users" / "default" / "agents" / AGENT_NAME
    if not _is_within(agent_dir, targets.deer_flow_home):
        raise ConfigureError("entry.agent_path_invalid", "default Agent path escapes DEER_FLOW_HOME")
    sources = (("config.yaml", config_bytes), ("SOUL.md", soul_bytes))
    if agent_dir.exists():
        actual_names = {path.name for path in agent_dir.iterdir()}
        if actual_names != {name for name, _content in sources}:
            raise ConfigureError("entry.agent_ownership_conflict", f"same-name Agent directory drifted: {AGENT_NAME}")
    plans: list[_TargetPlan] = []
    for name, source in sources:
        path = agent_dir / name
        existed_before = path.exists()
        before = path.read_bytes() if existed_before else b""
        if existed_before and before != source:
            raise ConfigureError("entry.agent_ownership_conflict", f"same-name Agent file drifted: {name}")
        plans.append(
            _TargetPlan(
                path,
                "file",
                existed_before,
                before,
                source,
                {"sha256": _sha256(source), "entry": f"{AGENT_NAME}/{name}"},
            )
        )
    return tuple(plans)


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _write_restricted(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(content)
        stream.flush()
        os.fsync(stream.fileno())
    os.chmod(path, 0o600)


def _atomic_replace(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = stat.S_IMODE(path.stat().st_mode) if path.exists() else 0o600
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _health_url(value: str) -> str:
    parsed = urlsplit(value)
    path = parsed.path.rstrip("/")
    if not path.endswith("/health"):
        path = f"{path}/health"
    return urlunsplit((parsed.scheme, parsed.netloc, path, "", ""))


def _health_urls(env: Mapping[str, str]) -> tuple[str, ...]:
    candidates: list[str] = []
    explicit = env.get("DEER_FLOW_GATEWAY_HEALTH_URL")
    if explicit:
        candidates.append(_health_url(explicit))
    configured_gateway = env.get("DEER_FLOW_CHANNELS_GATEWAY_URL")
    if configured_gateway:
        candidates.append(_health_url(configured_gateway))
    candidates.append(f"http://127.0.0.1:{env.get('GATEWAY_PORT', '8001')}/health")
    candidates.append(f"http://127.0.0.1:{env.get('PORT', '2026')}/health")
    return tuple(dict.fromkeys(candidates))


def _health_endpoint_reachable(url: str) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=0.5) as response:
            payload = json.loads(response.read(4096).decode("utf-8"))
    except (OSError, UnicodeError, ValueError, urllib.error.URLError):
        return False
    return isinstance(payload, dict) and payload.get("service") == "deer-flow-gateway"


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root)
    except (OSError, ValueError):
        return False
    return True


def _process_cwd(pid: str) -> Path | None:
    proc_cwd = Path("/proc") / pid / "cwd"
    try:
        if proc_cwd.exists():
            return proc_cwd.resolve(strict=True)
    except OSError:
        pass
    try:
        result = subprocess.run(
            ["lsof", "-a", "-p", pid, "-d", "cwd", "-Fn"],
            check=False,
            capture_output=True,
            text=True,
            timeout=1,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    for line in result.stdout.splitlines():
        if line.startswith("n"):
            try:
                return Path(line[1:]).resolve()
            except OSError:
                return None
    return None


def _project_process_running(root: Path) -> bool:
    try:
        process = subprocess.run(
            ["pgrep", "-f", "uvicorn app.gateway.app:app"],
            check=False,
            capture_output=True,
            text=True,
            timeout=1,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return any(
        cwd is not None and _is_within(cwd, root) for pid in process.stdout.split() if (cwd := _process_cwd(pid))
    )


def _project_container_running(root: Path) -> bool:
    try:
        result = subprocess.run(
            ["docker", "inspect", "deer-flow-gateway"],
            check=False,
            capture_output=True,
            text=True,
            timeout=2,
        )
        inspected = json.loads(result.stdout) if result.returncode == 0 else []
    except (OSError, ValueError, subprocess.SubprocessError):
        return False
    for container in inspected if isinstance(inspected, list) else []:
        if not container.get("State", {}).get("Running"):
            continue
        labels = container.get("Config", {}).get("Labels") or {}
        working_dir = labels.get("com.docker.compose.project.working_dir")
        if working_dir and _canonical(Path(working_dir)) == root:
            return True
        for mount in container.get("Mounts") or []:
            source = mount.get("Source")
            if source and _is_within(Path(source), root):
                return True
    return False


def _default_online_detector(root: Path, env: Mapping[str, str]) -> bool:
    if any(_health_endpoint_reachable(url) for url in _health_urls(env)):
        return True
    return _project_process_running(root) or _project_container_running(root)


def _entry_assessment(
    targets: ConfigTargets,
    plans: tuple[_TargetPlan, ...],
    env: Mapping[str, str],
) -> tuple[str, str, str, list[str]]:
    issues: list[str] = []
    legacy = targets.skills_root / "custom" / SKILL_NAME
    if legacy.exists():
        issues.append("legacy_custom_skill")
    extension_plan = next(plan for plan in plans if plan.kind == "json")
    skill_plan = next(plan for plan in plans if plan.owned_after.get("entry") == SKILL_NAME)
    if extension_plan.changed:
        issues.append("public_skill_disabled")
    if skill_plan.changed:
        issues.append("public_skill_missing")
    public_skill_status = "not_ready" if issues else "ready"

    agent_issues: list[str] = []
    legacy_agent = targets.deer_flow_home / "agents" / AGENT_NAME
    if legacy_agent.exists():
        agent_issues.append("legacy_shared_agent")
        agent_status = "not_ready"
    elif _auth_disabled_requested(env) and _production_requested(env):
        agent_issues.append("auth_disabled_production")
        agent_status = "not_ready"
    elif _auth_disabled_requested(env):
        agent_plans = [plan for plan in plans if str(plan.owned_after.get("entry", "")).startswith(f"{AGENT_NAME}/")]
        if any(plan.changed for plan in agent_plans):
            agent_issues.append("default_agent_missing")
            agent_status = "not_ready"
        else:
            agent_status = "ready"
    elif not targets.agents_api_enabled:
        agent_issues.append("agents_api_disabled")
        agent_status = "not_ready"
    else:
        agent_issues.append("authenticated_agent_unverifiable")
        agent_status = "unknown"

    issues.extend(agent_issues)
    if public_skill_status == "not_ready" or agent_status == "not_ready":
        entry_status = "not_ready"
    elif agent_status == "unknown":
        entry_status = "unknown"
    else:
        entry_status = "ready"
    return entry_status, public_skill_status, agent_status, issues


def _display_path(path: Path, targets: ConfigTargets) -> str:
    for label, base in (("$DEER_FLOW_HOME", targets.deer_flow_home), ("$PROJECT_ROOT", targets.project_root)):
        try:
            relative = path.relative_to(base)
        except ValueError:
            continue
        return label if not relative.parts else f"{label}/{relative.as_posix()}"
    return f"$EXTERNAL_TARGET/{path.name}"


def _summary(
    *,
    plans: tuple[_TargetPlan, ...],
    targets: ConfigTargets,
    would_change: bool,
    runtime_ready: bool,
    entry_status: str,
    public_skill_status: str | None = None,
    agent_status: str = "unknown",
    entry_issues: list[str] | None = None,
    agent_api_fixture: dict[str, Any] | None = None,
    manifest_path: Path | None = None,
    operation: str = "merge",
) -> dict[str, Any]:
    entries = {
        "yaml": [GROUP_NAME, TOOL_NAME],
        "json": [SKILL_NAME],
    }
    result: dict[str, Any] = {
        "surfaces": [GROUP_NAME, TOOL_NAME, SKILL_NAME],
        "targets": [_display_path(plan.path, targets) for plan in plans],
        "changes": [
            {
                "target": _display_path(plan.path, targets),
                "operation": operation
                if operation == "rollback"
                else "materialize"
                if plan.kind == "file"
                else operation,
                "entries": [str(plan.owned_after["entry"])] if plan.kind == "file" else entries[plan.kind],
            }
            for plan in plans
            if plan.changed
        ],
        "would_change": would_change,
        "runtime_config_ready": runtime_ready,
        "entry_status": entry_status,
        "public_skill_status": public_skill_status or entry_status,
        "agent_status": agent_status,
        "entry_issues": list(entry_issues or []),
        "mutation_precondition": "operator_confirms_all_gateways_stopped",
    }
    if manifest_path is not None:
        result["manifest"] = _display_path(manifest_path, targets)
    if agent_api_fixture is not None:
        result["authenticated_agent_api"] = agent_api_fixture
    return result


def _lock_path(targets: ConfigTargets) -> Path:
    return targets.deer_flow_home / "deep-research" / "configure.lock"


@contextmanager
def _project_lock(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(path.parent, 0o700)
    with path.open("a+b") as lock_stream:
        os.chmod(path, 0o600)
        fcntl.flock(lock_stream.fileno(), fcntl.LOCK_EX)
        yield


def _plans(targets: ConfigTargets, env: Mapping[str, str]) -> tuple[_TargetPlan, ...]:
    config_fragment, extensions_fragment = _load_fragments()
    return (
        _plan_config(targets.config_path, config_fragment),
        _plan_extensions(targets.extensions_path, extensions_fragment),
        _plan_public_skill(targets),
        *_agent_plans(targets, env),
    )


def _current_plan_bytes(plan: _TargetPlan) -> bytes:
    if plan.path.exists():
        return plan.path.read_bytes()
    return b"{}\n" if plan.kind == "json" else b""


def execute_configuration(
    project_root: Path,
    env: Mapping[str, str] | None = None,
    *,
    mode: Mode,
    online_detector: Callable[[], bool] | None = None,
    before_replace: Callable[[Path], None] | None = None,
) -> ConfigureResult:
    if mode not in {"apply", "check", "dry-run"}:
        raise ConfigureError("mode.invalid", f"unsupported mode: {mode}")
    root = _canonical(project_root, require_exists=True)
    effective_env = _effective_env(root, env)
    targets = resolve_targets(root, effective_env)
    api_fixture = None if _auth_disabled_requested(effective_env) else authenticated_agent_api_fixture()
    if mode != "apply":
        plans = _plans(targets, effective_env)
        entry_status, public_skill_status, agent_status, entry_issues = _entry_assessment(targets, plans, effective_env)
        would_change = any(plan.changed for plan in plans)
        runtime_ready = not any(plan.kind == "yaml" and plan.changed for plan in plans)
        return ConfigureResult(
            changed=False,
            would_change=would_change,
            runtime_config_ready=runtime_ready,
            entry_status=entry_status,
            manifest_path=None,
            summary=_summary(
                plans=plans,
                targets=targets,
                would_change=would_change,
                runtime_ready=runtime_ready,
                entry_status=entry_status,
                public_skill_status=public_skill_status,
                agent_status=agent_status,
                entry_issues=entry_issues,
                agent_api_fixture=api_fixture,
            ),
        )

    with _project_lock(_lock_path(targets)):
        plans = _plans(targets, effective_env)
        entry_status, public_skill_status, agent_status, entry_issues = _entry_assessment(targets, plans, effective_env)
        if "legacy_custom_skill" in entry_issues:
            raise ConfigureError(
                "entry.legacy_custom_skill",
                "legacy custom Deep Research skill must be removed before materialization",
            )
        if "legacy_shared_agent" in entry_issues:
            raise ConfigureError(
                "entry.legacy_shared_agent",
                "legacy shared Deep Research Agent must be migrated or removed before materialization",
            )
        if "auth_disabled_production" in entry_issues:
            raise ConfigureError(
                "entry.auth_disabled_production",
                "offline auth-disabled Agent provisioning is forbidden in production",
            )
        would_change = any(plan.changed for plan in plans)
        if not would_change:
            return ConfigureResult(
                changed=False,
                would_change=False,
                runtime_config_ready=True,
                entry_status=entry_status,
                manifest_path=None,
                summary=_summary(
                    plans=plans,
                    targets=targets,
                    would_change=False,
                    runtime_ready=True,
                    entry_status=entry_status,
                    public_skill_status=public_skill_status,
                    agent_status=agent_status,
                    entry_issues=entry_issues,
                    agent_api_fixture=api_fixture,
                ),
            )
        detector = online_detector or (lambda: _default_online_detector(targets.project_root, effective_env))
        if detector():
            raise ConfigureError("runtime.online", "configuration mutation requires a stopped project Gateway")

        changed_plans = tuple(plan for plan in plans if plan.changed)
        if before_replace:
            for plan in changed_plans:
                before_replace(plan.path)
        for plan in changed_plans:
            current = _current_plan_bytes(plan)
            if current != plan.before:
                raise ConfigureError("write.concurrent_change", f"target changed during planning: {plan.path.name}")

        run_dir = targets.deer_flow_home / "deep-research" / "config-history" / (f"{time.time_ns()}-{uuid.uuid4().hex}")
        run_dir.mkdir(parents=True, mode=0o700)
        os.chmod(run_dir, 0o700)
        manifest_targets: list[dict[str, Any]] = []
        for index, plan in enumerate(changed_plans):
            backup_path = run_dir / f"{index}-{plan.path.name}.before"
            _write_restricted(backup_path, plan.before)
            manifest_targets.append(
                {
                    "path": str(plan.path),
                    "kind": plan.kind,
                    "existed_before": plan.existed_before,
                    "before_hash": _sha256(plan.before),
                    "after_hash": _sha256(plan.after),
                    "backup_path": str(backup_path),
                    "owned_after": plan.owned_after,
                }
            )
        manifest_path = run_dir / "manifest.json"
        _write_restricted(
            manifest_path,
            (
                json.dumps(
                    {
                        "version": 2,
                        "project_root": str(targets.project_root),
                        "deer_flow_home": str(targets.deer_flow_home),
                        "targets": manifest_targets,
                    },
                    indent=2,
                )
                + "\n"
            ).encode("utf-8"),
        )
        try:
            for plan in changed_plans:
                current = _current_plan_bytes(plan)
                if current != plan.before:
                    raise ConfigureError(
                        "write.concurrent_change",
                        f"target changed immediately before replace: {plan.path.name}",
                    )
                _atomic_replace(plan.path, plan.after)
        except OSError as exc:
            manifest_ref = _display_path(manifest_path, targets)
            raise ConfigureError("write.failed", f"target write failed; recovery manifest: {manifest_ref}") from exc
        post_plans = _plans(targets, effective_env)
        post_entry_status, post_public_skill_status, post_agent_status, post_entry_issues = _entry_assessment(
            targets, post_plans, effective_env
        )
    return ConfigureResult(
        changed=True,
        would_change=True,
        runtime_config_ready=True,
        entry_status=post_entry_status,
        manifest_path=manifest_path,
        summary=_summary(
            plans=plans,
            targets=targets,
            would_change=True,
            runtime_ready=True,
            entry_status=post_entry_status,
            public_skill_status=post_public_skill_status,
            agent_status=post_agent_status,
            entry_issues=post_entry_issues,
            agent_api_fixture=api_fixture,
            manifest_path=manifest_path,
        ),
    )


def _semantic_yaml_rollback(current: bytes, owned: dict[str, Any]) -> bytes:
    data, yaml = _safe_yaml_load(current, "rollback.config_parse")
    for section, key in (("tool_groups", "group"), ("tools", "tool")):
        entries = data.get(section) or []
        expected = owned[key]
        existing = _find_named(entries, expected["name"], section)
        if existing is None:
            continue
        if _plain(existing) != expected:
            raise ConfigureError("rollback.owned_drift", f"owned entry changed: {expected['name']}")
        entries.remove(existing)
    return _yaml_dump(data, yaml)


def _semantic_json_rollback(current: bytes, owned: dict[str, Any]) -> bytes:
    try:
        data = json.loads(current.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ConfigureError("rollback.extensions_parse", "extensions configuration is invalid") from exc
    skills = data.get("skills") or {}
    existing = skills.get(SKILL_NAME)
    if existing is not None:
        if existing != owned["skill"]:
            raise ConfigureError("rollback.owned_drift", f"owned entry changed: {SKILL_NAME}")
        del skills[SKILL_NAME]
    return _json_dump(data, current)


def rollback_configuration(
    manifest_path: Path | None,
    *,
    env: Mapping[str, str] | None = None,
    online_detector: Callable[[], bool] | None = None,
) -> ConfigureResult:
    if manifest_path is None or not manifest_path.is_file():
        raise ConfigureError("rollback.manifest_missing", "rollback manifest does not exist")
    try:
        manifest_bytes = manifest_path.read_bytes()
        manifest = json.loads(manifest_bytes.decode("utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ConfigureError("rollback.manifest_parse", "rollback manifest is invalid") from exc
    if manifest.get("version") != 2 or not isinstance(manifest.get("targets"), list):
        raise ConfigureError("rollback.manifest_parse", "rollback manifest version is unsupported")
    try:
        root = _canonical(Path(manifest["project_root"]), require_exists=True)
        deer_flow_home = _canonical(Path(manifest["deer_flow_home"]))
    except (KeyError, TypeError) as exc:
        raise ConfigureError("rollback.manifest_parse", "rollback manifest paths are invalid") from exc
    effective_env = _effective_env(root, env)
    targets = ConfigTargets(root, root, root, root / "skills", deer_flow_home, False)
    plans_for_summary: list[_TargetPlan] = []
    outputs: list[tuple[Path, bytes, bytes | None]] = []
    seen_paths: set[Path] = set()
    owned_agent_dirs: set[Path] = set()

    with _project_lock(deer_flow_home / "deep-research" / "configure.lock"):
        if manifest_path.read_bytes() != manifest_bytes:
            raise ConfigureError("write.concurrent_change", "rollback manifest changed during planning")
        detector = online_detector or (lambda: _default_online_detector(root, effective_env))
        if detector():
            raise ConfigureError("runtime.online", "rollback requires a stopped project Gateway")

        for target in manifest["targets"]:
            try:
                recorded_path = Path(target["path"])
                path = _canonical(recorded_path)
                recorded_backup_path = Path(target["backup_path"])
                backup_path = _canonical(recorded_backup_path, require_exists=True)
                before_hash = target["before_hash"]
                after_hash = target["after_hash"]
                kind = target["kind"]
                existed_before = target["existed_before"]
                owned_after = target["owned_after"]
            except (KeyError, TypeError) as exc:
                raise ConfigureError("rollback.manifest_parse", "rollback target is invalid") from exc
            if path != recorded_path or backup_path != recorded_backup_path:
                raise ConfigureError("rollback.target_identity", "rollback target identity changed")
            if path in seen_paths or kind not in {"yaml", "json", "file"} or not isinstance(existed_before, bool):
                raise ConfigureError("rollback.manifest_parse", "rollback target is ambiguous")
            seen_paths.add(path)
            backup = backup_path.read_bytes()
            if _sha256(backup) != before_hash:
                raise ConfigureError("rollback.backup_drift", f"backup changed: {path.name}")
            path_exists = path.exists()
            if not path_exists and existed_before:
                raise ConfigureError("rollback.target_missing", f"rollback target is missing: {path.name}")
            current = path.read_bytes() if path_exists else b""
            current_hash = _sha256(current)
            if not existed_before and not path_exists:
                desired: bytes | None = None
            elif current_hash == before_hash and existed_before:
                desired = current
            elif current_hash == after_hash:
                desired = backup if existed_before else None
            elif kind == "yaml":
                desired = _semantic_yaml_rollback(current, owned_after)
            elif kind == "json":
                desired = _semantic_json_rollback(current, owned_after)
            elif _sha256(current) == owned_after.get("sha256"):
                desired = backup if existed_before else None
            else:
                raise ConfigureError("rollback.owned_drift", f"owned entry changed: {path.name}")
            outputs.append((path, current, desired))
            plans_for_summary.append(_TargetPlan(path, kind, path.exists(), current, desired or b"", owned_after))
            expected_agent_dir = deer_flow_home / "users" / "default" / "agents" / AGENT_NAME
            if path.parent == expected_agent_dir and str(owned_after.get("entry", "")).startswith(f"{AGENT_NAME}/"):
                owned_agent_dirs.add(expected_agent_dir)

        for path, before, _desired in outputs:
            current = path.read_bytes() if path.exists() else b""
            if current != before:
                raise ConfigureError("write.concurrent_change", f"target changed during rollback: {path.name}")
        for path, before, desired in outputs:
            current = path.read_bytes() if path.exists() else b""
            if current != before:
                raise ConfigureError("write.concurrent_change", f"target changed before rollback replace: {path.name}")
            if desired is None:
                path.unlink(missing_ok=True)
            else:
                _atomic_replace(path, desired)
        for agent_dir in owned_agent_dirs:
            if agent_dir.is_dir() and not any(agent_dir.iterdir()):
                agent_dir.rmdir()
    changed = any(before != (desired or b"") for _path, before, desired in outputs)
    return ConfigureResult(
        changed=changed,
        would_change=changed,
        runtime_config_ready=False,
        entry_status="not_ready",
        manifest_path=manifest_path,
        summary=_summary(
            plans=tuple(plans_for_summary),
            targets=targets,
            would_change=changed,
            runtime_ready=False,
            entry_status="not_ready",
            manifest_path=manifest_path,
            operation="rollback",
        ),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=SCRIPT_ROOT.parent)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--check", action="store_true")
    modes.add_argument("--dry-run", action="store_true")
    modes.add_argument("--rollback", type=Path)
    args = parser.parse_args()
    try:
        if args.rollback:
            result = rollback_configuration(args.rollback)
        else:
            mode: Mode = "check" if args.check else "dry-run" if args.dry_run else "apply"
            result = execute_configuration(args.project_root, mode=mode)
    except ConfigureError as exc:
        print(json.dumps({"ok": False, "code": exc.code, "detail": exc.detail}), file=sys.stderr)
        return 1
    except Exception:
        print(
            json.dumps(
                {
                    "ok": False,
                    "code": "internal.error",
                    "detail": "configuration operation failed without a safe diagnostic",
                }
            ),
            file=sys.stderr,
        )
        return 1
    print(json.dumps({"ok": True, **result.summary}, sort_keys=True))
    if args.check and not result.runtime_config_ready:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
