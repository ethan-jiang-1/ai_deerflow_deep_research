"""Hermetic reusable scenario fixtures and owned global cleanup.

@impl EVH-001
@impl EVH-008
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from tests.fixtures.scenarios import build_scenario_fixture_bundle
from tests.scenarios import canaries


def test_fixture_bundle_is_contained_and_composes_existing_adapters(tmp_path: Path) -> None:
    bundle = build_scenario_fixture_bundle(
        tmp_path,
        model_responses=("first", "second"),
        tool_results=("result",),
    )

    assert bundle.envelope.workspace_host_path.is_relative_to(tmp_path)
    assert bundle.checkpoint_root.is_relative_to(bundle.envelope.workspace_host_path)
    assert bundle.ledger_root.is_relative_to(bundle.envelope.workspace_host_path)
    assert bundle.artifact_root.is_relative_to(bundle.envelope.workspace_host_path)
    assert len(bundle.model.responses) == 2
    assert bundle.tool.name == "web_search"
    assert len(bundle.tool.responses) == 1


def test_live_adapter_resets_owned_provider_on_success_and_failure(monkeypatch, tmp_path: Path) -> None:
    resets: list[str] = []
    monkeypatch.setattr(canaries, "set_sandbox_provider", lambda _provider: None)
    monkeypatch.setattr(canaries, "reset_sandbox_provider", lambda: resets.append("reset"))
    config = canaries._app_config("deepseek", "placeholder-key")

    with canaries._LiveAdapter(tmp_path / "success", config):
        pass
    assert resets == ["reset"]

    with pytest.raises(RuntimeError, match="boom"):
        with canaries._LiveAdapter(tmp_path / "failure", config):
            raise RuntimeError("boom")
    assert resets == ["reset", "reset"]


def test_live_adapter_cleanup_is_order_independent(monkeypatch, tmp_path: Path) -> None:
    events: list[str] = []
    monkeypatch.setattr(canaries, "set_sandbox_provider", lambda _provider: events.append("set"))
    monkeypatch.setattr(canaries, "reset_sandbox_provider", lambda: events.append("reset"))
    config = canaries._app_config("deepseek", "placeholder-key")

    for name in ("second", "first"):
        with canaries._LiveAdapter(tmp_path / name, config):
            events.append(name)

    assert events == ["set", "second", "reset", "set", "first", "reset"]


async def test_live_preflight_failure_does_not_reset_unowned_provider(monkeypatch, tmp_path: Path) -> None:
    resets: list[str] = []
    monkeypatch.setattr(canaries, "reset_sandbox_provider", lambda: resets.append("reset"))

    with pytest.raises(Exception, match="live_model_credentials_missing"):
        await canaries.run_live_canary(
            canaries.LIVE_CANARIES[0],
            environ={},
            workspace=tmp_path,
        )

    assert resets == []


async def test_live_execution_failure_after_adapter_install_resets_provider(monkeypatch, tmp_path: Path) -> None:
    resets: list[str] = []
    monkeypatch.setattr(canaries, "set_sandbox_provider", lambda _provider: None)
    monkeypatch.setattr(canaries, "reset_sandbox_provider", lambda: resets.append("reset"))
    monkeypatch.setattr(
        canaries,
        "preflight_live_environment",
        lambda **_kwargs: SimpleNamespace(model_provider="deepseek", web_provider=None),
    )
    monkeypatch.setattr(canaries, "ResearchGraphRecipe", None)

    with pytest.raises(AttributeError):
        await canaries.run_live_canary(
            canaries.LIVE_CANARIES[0],
            environ={"DEEPSEEK_API_KEY": "placeholder-key"},
            workspace=tmp_path,
        )

    assert resets == ["reset"]
