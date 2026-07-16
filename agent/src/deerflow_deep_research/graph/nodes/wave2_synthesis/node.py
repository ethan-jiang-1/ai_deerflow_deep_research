"""Real Wave2 synthesis node — cross-topic synthesis from accepted evidence.

@impl WSN-001
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from deerflow_deep_research.domain.context import NodeExecutionResult
from deerflow_deep_research.domain.enums import NodeFinishReason
from deerflow_deep_research.domain.node_spec import NodeBuildDependencies
from deerflow_deep_research.engine.fake_control import node_update

from .materializer import materialize_synthesis
from .prompts import build_synthesis_prompt, parse_synthesis_output


def build_real(dependencies: NodeBuildDependencies):
    async def run(state: dict[str, Any]) -> dict[str, Any]:
        topic_registry = state.get("topic_registry") or ()
        wave0_refs = state.get("accepted_submission_refs") or ()
        wave1_refs = ()  # Wave1 refs are in the same ledger; for now, all accepted refs
        request = build_synthesis_prompt(
            topic_registry=topic_registry,
            wave0_refs=wave0_refs,
            wave1_refs=wave1_refs,
        )
        result = await dependencies.capabilities.run_agent(context=dependencies.capabilities, request=request)
        if not isinstance(result, NodeExecutionResult) or result.finish_reason is not NodeFinishReason.SUCCESS:
            raise ValueError("synthesis_failed")
        output = parse_synthesis_output(result.summary)
        materialize_synthesis(output, Path(dependencies.graph_context.workspace_root))
        return {**node_update("wave2_synthesis"), "route": "pass"}

    return run
