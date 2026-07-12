#!/usr/bin/env python3
"""Prepare the stopped DeerFlow environment for Deep Research startup.

@impl DEC-001
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import subprocess
import sys
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

from dotenv import dotenv_values

from deerflow_deep_research.runtime.startup_snapshot import (
    capture_startup_fingerprint,
    parse_startup_fingerprint,
)

SCRIPT_ROOT = Path(__file__).resolve().parents[1]
_VERSION_PATTERN = re.compile(r"(?m)^config_version:[ \t]*([^#\r\n]+)")
_EXTRA_NAME_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_-]*$")


class PrepareError(RuntimeError):
    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"[{code}] {detail}")
        self.code = code
        self.detail = detail


@dataclass(frozen=True)
class UpstreamCommandContract:
    backend_sync_prefix: tuple[str, ...]
    frontend_install: tuple[str, ...]
    detect_extras_script: Path
    gateway_pythonpath: str


@dataclass(frozen=True)
class PreparationContext:
    project_root: Path
    backend_dir: Path
    frontend_dir: Path
    agent_dir: Path
    gateway_cwd: Path
    config_path: Path
    extensions_path: Path
    deer_flow_home: Path
    expected_config_version: int
    environment: dict[str, str]


@dataclass(frozen=True)
class CommandSpec:
    stage: str
    argv: tuple[str, ...]
    cwd: Path
    environment: dict[str, str]


@dataclass(frozen=True)
class CommandOutcome:
    returncode: int
    stdout: str
    stderr: str


@dataclass(frozen=True)
class RuntimeOriginFacts:
    harness_version: str
    harness_origin: Path
    module_origin: Path


@dataclass(frozen=True)
class PrepareResult:
    machine: dict[str, str]


Runner = Callable[[CommandSpec], CommandOutcome]
RuntimeProbe = Callable[[PreparationContext], RuntimeOriginFacts]
CandidateBuilder = Callable[[PreparationContext], str]


def upstream_command_contract(project_root: Path) -> UpstreamCommandContract:
    root = project_root.resolve(strict=True)
    return UpstreamCommandContract(
        backend_sync_prefix=("uv", "sync", "--quiet", "--all-packages"),
        frontend_install=("pnpm", "install", "--silent"),
        detect_extras_script=(root / "scripts/detect_uv_extras.py").resolve(),
        gateway_pythonpath=".",
    )


def _effective_env(root: Path, env: Mapping[str, str] | None) -> dict[str, str]:
    try:
        dotenv = dotenv_values(root / ".env") if (root / ".env").is_file() else {}
    except (OSError, ValueError) as exc:
        raise PrepareError("dotenv_invalid", "root .env could not be parsed") from exc
    effective = {str(key): str(value) for key, value in dotenv.items() if value is not None}
    supplied = os.environ if env is None else env
    effective.update({str(key): str(value) for key, value in supplied.items()})
    return effective


def _absolute_env_path(env: Mapping[str, str], key: str) -> Path | None:
    value = env.get(key)
    if not value:
        return None
    path = Path(value)
    if not path.is_absolute():
        raise PrepareError("runtime_path_relative", f"{key} must be absolute after root .env loading")
    return path.resolve()


def _app_config_target(root: Path, env: Mapping[str, str]) -> Path:
    explicit = _absolute_env_path(env, "DEER_FLOW_CONFIG_PATH")
    if explicit is not None:
        if not explicit.is_file():
            raise PrepareError("config_target_missing", "explicit AppConfig target does not exist")
        return explicit
    for candidate in (root / "config.yaml", root / "backend/config.yaml"):
        if candidate.is_file():
            return candidate.resolve()
    raise PrepareError("config_target_missing", "AppConfig target does not exist")


def _upgrade_config_target(root: Path, env: Mapping[str, str]) -> Path:
    explicit = _absolute_env_path(env, "DEER_FLOW_CONFIG_PATH")
    if explicit is not None and explicit.is_file():
        return explicit
    for candidate in (root / "backend/config.yaml", root / "config.yaml"):
        if candidate.is_file():
            return candidate.resolve()
    raise PrepareError("config_target_missing", "config-upgrade target does not exist")


def _extensions_target(root: Path, env: Mapping[str, str]) -> Path:
    explicit = _absolute_env_path(env, "DEER_FLOW_EXTENSIONS_CONFIG_PATH")
    if explicit is not None:
        if not explicit.is_file():
            raise PrepareError("extensions_target_missing", "explicit extensions target does not exist")
        return explicit
    for candidate in (root / "extensions_config.json", root / "backend/extensions_config.json"):
        if candidate.is_file():
            return candidate.resolve()
    raise PrepareError("extensions_target_missing", "extensions target does not exist")


def _read_config_version(path: Path, *, expected: bool = False) -> int:
    try:
        content = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise PrepareError("config_version_missing", "config version source is unavailable") from exc
    match = _VERSION_PATTERN.search(content)
    if match is None:
        code = "config_example_invalid" if expected else "config_version_missing"
        raise PrepareError(code, "config_version is missing")
    raw = match.group(1).strip()
    if not raw.isdecimal():
        code = "config_example_invalid" if expected else "config_version_invalid"
        raise PrepareError(code, "config_version must be a decimal integer")
    return int(raw)


def resolve_preparation_context(
    project_root: Path,
    env: Mapping[str, str] | None = None,
) -> PreparationContext:
    root = project_root.resolve(strict=True)
    effective = _effective_env(root, env)
    configured_root = _absolute_env_path(effective, "DEER_FLOW_PROJECT_ROOT")
    if configured_root is not None and configured_root != root:
        raise PrepareError("project_root_mismatch", "DEER_FLOW_PROJECT_ROOT selects another project")
    effective["DEER_FLOW_PROJECT_ROOT"] = str(root)

    backend_dir = (root / "backend").resolve(strict=True)
    frontend_dir = (root / "frontend").resolve(strict=True)
    agent_dir = (root / "agent").resolve(strict=True)
    home = _absolute_env_path(effective, "DEER_FLOW_HOME") or (backend_dir / ".deer-flow").resolve()
    effective["DEER_FLOW_HOME"] = str(home)

    app_target = _app_config_target(root, effective)
    upgrade_target = _upgrade_config_target(root, effective)
    if app_target != upgrade_target:
        raise PrepareError(
            "config_target_disagreement",
            "AppConfig and config-upgrade select different config files",
        )
    extensions_path = _extensions_target(root, effective)
    effective["DEER_FLOW_CONFIG_PATH"] = str(app_target)
    effective["DEER_FLOW_EXTENSIONS_CONFIG_PATH"] = str(extensions_path)

    expected_version = _read_config_version(root / "config.example.yaml", expected=True)
    actual_version = _read_config_version(app_target)
    if actual_version < expected_version:
        raise PrepareError("config_version_older", "config is older than this checkout")
    if actual_version > expected_version:
        raise PrepareError("config_version_newer", "config is newer than this checkout")

    return PreparationContext(
        project_root=root,
        backend_dir=backend_dir,
        frontend_dir=frontend_dir,
        agent_dir=agent_dir,
        gateway_cwd=backend_dir,
        config_path=app_target,
        extensions_path=extensions_path,
        deer_flow_home=home,
        expected_config_version=expected_version,
        environment=effective,
    )


def _default_runner(spec: CommandSpec) -> CommandOutcome:
    try:
        result = subprocess.run(
            spec.argv,
            cwd=spec.cwd,
            env=spec.environment,
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError as exc:
        raise PrepareError("command_failed", f"{spec.stage} could not start") from exc
    return CommandOutcome(result.returncode, result.stdout, result.stderr)


def _run_checked(runner: Runner, spec: CommandSpec) -> CommandOutcome:
    result = runner(spec)
    if result.returncode != 0:
        raise PrepareError("command_failed", f"{spec.stage} failed")
    return result


def _parse_extra_flags(stdout: str) -> tuple[str, ...]:
    try:
        tokens = shlex.split(stdout)
    except ValueError as exc:
        raise PrepareError("extras_invalid", "detected uv extras are malformed") from exc
    if len(tokens) % 2:
        raise PrepareError("extras_invalid", "detected uv extras are malformed")
    for index in range(0, len(tokens), 2):
        if tokens[index] != "--extra" or not _EXTRA_NAME_PATTERN.fullmatch(tokens[index + 1]):
            raise PrepareError("extras_invalid", "detected uv extras are outside the supported grammar")
    return tuple(tokens)


def _command_environment(context: PreparationContext, pythonpath: str) -> dict[str, str]:
    environment = dict(context.environment)
    environment["PYTHONPATH"] = pythonpath
    return environment


def _version_tuple(value: str) -> tuple[int, int, int] | None:
    match = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)(?:[.+-].*)?", value)
    if match is None:
        return None
    return tuple(int(part) for part in match.groups())


def validate_runtime_origins(context: PreparationContext, facts: RuntimeOriginFacts) -> None:
    version = _version_tuple(facts.harness_version)
    harness_root = context.project_root / "backend/packages/harness/deerflow"
    module_root = context.project_root / "agent/src/deerflow_deep_research"
    try:
        harness_ok = facts.harness_origin.resolve().is_relative_to(harness_root.resolve())
        module_ok = facts.module_origin.resolve().is_relative_to(module_root.resolve())
    except OSError:
        harness_ok = module_ok = False
    if version is None or not ((2, 1, 0) <= version < (2, 2, 0)) or not harness_ok or not module_ok:
        raise PrepareError("runtime_origin_invalid", "installed harness version or module origin is incompatible")


def _default_runtime_probe(context: PreparationContext) -> RuntimeOriginFacts:
    code = (
        "import importlib.metadata,json,pathlib,deerflow,deerflow_deep_research;"
        "print(json.dumps({'harness_version':importlib.metadata.version('deerflow-harness'),"
        "'harness_origin':str(pathlib.Path(deerflow.__file__).resolve()),"
        "'module_origin':str(pathlib.Path(deerflow_deep_research.__file__).resolve())}))"
    )
    interpreter = context.backend_dir / ".venv/bin/python"
    spec = CommandSpec(
        "runtime_probe",
        (str(interpreter), "-c", code),
        context.backend_dir,
        _command_environment(context, "."),
    )
    result = _run_checked(_default_runner, spec)
    try:
        payload = json.loads(result.stdout)
        return RuntimeOriginFacts(
            harness_version=payload["harness_version"],
            harness_origin=Path(payload["harness_origin"]),
            module_origin=Path(payload["module_origin"]),
        )
    except (KeyError, TypeError, json.JSONDecodeError) as exc:
        raise PrepareError("runtime_origin_invalid", "runtime origin probe returned invalid data") from exc


def build_startup_candidate(context: PreparationContext) -> str:
    previous_cwd = Path.cwd()
    previous_environment = dict(os.environ)
    try:
        os.environ.update(context.environment)
        os.chdir(context.gateway_cwd)
        from deerflow.config.app_config import AppConfig

        app_config = AppConfig.from_file(str(context.config_path))
        return capture_startup_fingerprint(
            app_config,
            worker_value=context.environment.get("GATEWAY_WORKERS"),
        )
    finally:
        os.chdir(previous_cwd)
        os.environ.clear()
        os.environ.update(previous_environment)


def prepare_environment(
    project_root: Path,
    env: Mapping[str, str] | None = None,
    *,
    quiescence_confirmed: bool,
    runner: Runner = _default_runner,
    runtime_probe: RuntimeProbe = _default_runtime_probe,
    candidate_builder: CandidateBuilder = build_startup_candidate,
) -> PrepareResult:
    if not quiescence_confirmed:
        raise PrepareError("quiescence_required", "the caller must stop the project Gateway before preparation")
    context = resolve_preparation_context(project_root, env)
    contract = upstream_command_contract(context.project_root)
    command_env = _command_environment(context, contract.gateway_pythonpath)

    detected = _run_checked(
        runner,
        CommandSpec(
            "detect_extras",
            (sys.executable, str(contract.detect_extras_script)),
            context.project_root,
            command_env,
        ),
    )
    extras = _parse_extra_flags(detected.stdout.strip())
    _run_checked(
        runner,
        CommandSpec(
            "backend_sync",
            (*contract.backend_sync_prefix, *extras),
            context.backend_dir,
            command_env,
        ),
    )
    _run_checked(
        runner,
        CommandSpec("frontend_install", contract.frontend_install, context.frontend_dir, command_env),
    )
    _run_checked(
        runner,
        CommandSpec(
            "editable_install",
            (
                "uv",
                "pip",
                "install",
                "--python",
                str(context.backend_dir / ".venv/bin/python"),
                "--no-deps",
                "--editable",
                str(context.agent_dir),
            ),
            context.backend_dir,
            command_env,
        ),
    )

    validate_runtime_origins(context, runtime_probe(context))
    fingerprint = candidate_builder(context)
    parse_startup_fingerprint(fingerprint)
    return PrepareResult(machine={"startup_fingerprint": fingerprint})


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=SCRIPT_ROOT.parent)
    parser.add_argument("--stopped", action="store_true", help="Confirm the project Gateway was stopped by the caller")
    args = parser.parse_args()
    try:
        result = prepare_environment(args.project_root, quiescence_confirmed=args.stopped)
    except PrepareError as exc:
        print(json.dumps({"ok": False, "code": exc.code, "detail": exc.detail}), file=sys.stderr)
        return 1
    except Exception:
        print(
            json.dumps(
                {
                    "ok": False,
                    "code": "internal.error",
                    "detail": "preparation failed without a safe diagnostic",
                }
            ),
            file=sys.stderr,
        )
        return 1
    print(json.dumps({"ok": True, **result.machine}, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
