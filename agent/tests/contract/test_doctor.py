"""Contracts for the thin Deep Research doctor CLI."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

REPO_ROOT = Path(__file__).resolve().parents[3]
DOCTOR_PATH = REPO_ROOT / "agent" / "scripts" / "doctor.py"


def _module():
    spec = importlib.util.spec_from_file_location("deep_research_doctor", DOCTOR_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_doctor_json_includes_work_unit_storage(monkeypatch, capsys) -> None:
    import deerflow_deep_research.runtime.diagnostics as diagnostics

    monkeypatch.setattr(
        diagnostics,
        "run_diagnostics",
        lambda **_kwargs: SimpleNamespace(
            runtime_ready=True,
            mode="prelaunch-candidate",
            entry=SimpleNamespace(status="ready"),
            durability="restart_durable",
            provider_kind="sqlite",
            worker_count=1,
            work_unit_storage="ready",
            issues=[],
        ),
    )
    monkeypatch.setattr(sys, "argv", [str(DOCTOR_PATH)])

    assert _module().main() == 0
    assert json.loads(capsys.readouterr().out)["work_unit_storage"] == "ready"
