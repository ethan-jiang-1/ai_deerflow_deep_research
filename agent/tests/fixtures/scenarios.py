"""Composable hermetic fixtures for focused scenario cases.

@impl EVH-001
@impl EVH-007
@impl EVH-008
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from tests.fixtures.fake_models import ScriptedChatModel, ai_message
from tests.fixtures.runtime import RunIdentity, local_runtime_envelope, unique_run_identity
from tests.fixtures.scripted_tools import ScriptedTool


@dataclass(frozen=True)
class ScenarioFixtureBundle:
    identity: RunIdentity
    envelope: object
    model: ScriptedChatModel
    tool: ScriptedTool
    checkpoint_root: Path
    ledger_root: Path
    artifact_root: Path


def build_scenario_fixture_bundle(
    root: Path,
    *,
    model_responses: tuple[str, ...],
    tool_results: tuple[str | BaseException, ...],
) -> ScenarioFixtureBundle:
    identity = unique_run_identity()
    envelope = local_runtime_envelope(root, identity=identity)
    authority_root = envelope.workspace_host_path / "deep-research" / identity.research_id
    checkpoint_root = authority_root / "checkpoint"
    ledger_root = authority_root / "submissions"
    artifact_root = authority_root / "artifacts"
    for path in (checkpoint_root, ledger_root, artifact_root):
        path.mkdir(parents=True, exist_ok=True)
    return ScenarioFixtureBundle(
        identity=identity,
        envelope=envelope,
        model=ScriptedChatModel(responses=[ai_message(response) for response in model_responses]),
        tool=ScriptedTool.create("web_search", *tool_results),
        checkpoint_root=checkpoint_root,
        ledger_root=ledger_root,
        artifact_root=artifact_root,
    )


__all__ = ["ScenarioFixtureBundle", "build_scenario_fixture_bundle"]
