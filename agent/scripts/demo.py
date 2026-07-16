#!/usr/bin/env python3
"""Run the Change 01 full-fake lifecycle without Gateway or model APIs."""

from __future__ import annotations

import argparse
import asyncio
import json
import secrets
import tempfile
import time
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage
from langgraph.types import Command

from deerflow_deep_research.runtime.control import build_control_graph_host
from deerflow_deep_research.runtime.research import ResearchGraphRecipe
from deerflow_deep_research.runtime.runtime_adapter import TrustedRuntimeEnvelope
from deerflow_deep_research.runtime.work_unit_store import WorkUnitStore
from deerflow_deep_research.tool import run_deep_research


class DemoAppConfig:
    checkpointer = None
    database = None


class DemoAdapter:
    def __init__(self) -> None:
        self._temporary = tempfile.TemporaryDirectory(prefix="deerflow-deep-research-demo-")
        root = Path(self._temporary.name)
        workspace = root / "workspace"
        uploads = root / "uploads"
        outputs = root / "outputs"
        for path in (workspace, uploads, outputs):
            path.mkdir()
        self._envelope = TrustedRuntimeEnvelope(
            effective_user_id="demo-user",
            outer_thread_id="demo-thread",
            outer_run_id="demo-run",
            app_config=DemoAppConfig(),
            workspace_host_path=workspace,
            uploads_host_path=uploads,
            outputs_host_path=outputs,
            workspace_virtual_root="/mnt/user-data/workspace",
            uploads_virtual_root="/mnt/user-data/uploads",
            outputs_virtual_root="/mnt/user-data/outputs",
            parent_sandbox=object(),
            progress=None,
        )

    async def adapt(
        self,
        _runtime: Any,
        *,
        initialize_parent_sandbox: bool = True,
    ) -> TrustedRuntimeEnvelope:
        if initialize_parent_sandbox:
            return self._envelope
        return replace(self._envelope, parent_sandbox=None)

    async def create_work_unit_store(self, _envelope: Any, *, research_id: str) -> WorkUnitStore:
        return WorkUnitStore(
            workspace_host_path=self._envelope.workspace_host_path,
            research_id=research_id,
            clock=lambda: datetime.now(UTC),
            monotonic=time.monotonic,
            lock_sleep=time.sleep,
            token_factory=lambda: secrets.token_hex(16),
            fault_hook=None,
        )

    def close(self) -> None:
        self._temporary.cleanup()


def _tool_call(action: str, call_id: str, research_id: str | None = None) -> AIMessage:
    args = {"action": action}
    if research_id is not None:
        args["research_id"] = research_id
    return AIMessage(
        content="",
        tool_calls=[{"name": "deep_research", "args": args, "id": call_id}],
    )


def _runtime(messages: list[Any], call_id: str) -> SimpleNamespace:
    return SimpleNamespace(state={"messages": messages}, context={}, tool_call_id=call_id)


def _suspension(command: Command) -> tuple[dict[str, Any], dict[str, Any]]:
    message = command.update["messages"][0]
    return json.loads(message.content), message.artifact["human_input"]


def _show(label: str, payload: dict[str, Any]) -> None:
    print(f"\n=== {label} ===")
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))


def _answer(prompt: str, *, scripted: bool, default: str) -> str:
    if scripted:
        print(f"{prompt}{default}  [scripted]")
        return default
    value = input(f"{prompt}[default: {default}] ").strip()
    return value or default


async def run_demo(*, question: str, scripted: bool, real: bool = False) -> None:
    if real:
        from deerflow_deep_research.graph.topology import LOGICAL_NODES

        modes: dict[str, str] = {name: "fake" for name in LOGICAL_NODES}
        modes.update({"hitl2": "real", "rerun": "real", "readiness": "real", "final_delivery": "real"})
        implementation_modes: dict[str, str] | None = modes
        print("DeerFlow Deep Research — real: hitl2, rerun, readiness, final_delivery")
    else:
        implementation_modes = None
        print("DeerFlow Deep Research — full-fake mode (add --real for real non-agent nodes)")

    adapter = DemoAdapter()
    from deerflow_deep_research.graph.builder import build_research_graph

    recipe = ResearchGraphRecipe(
        builder=build_research_graph(implementation_modes=implementation_modes),
        requires_work_units=True,
        work_unit_store_factory=adapter.create_work_unit_store,
    )
    host = build_control_graph_host(
        fingerprint_verifier=lambda _app_config: None,
        research_recipe=recipe,
    )
    start_user = HumanMessage(content=question, id="demo-human-start")
    start_call = _tool_call("start", "demo-call-start")

    started = await run_deep_research(
        action="start",
        probe_id=None,
        runtime=_runtime([start_user, start_call], "demo-call-start"),
        adapter=adapter,
        host_factory=lambda: host,
    )
    if not isinstance(started, Command):
        raise RuntimeError(f"demo start failed: {started}")
    start_result, hitl1 = _suspension(started)
    _show("START RESULT", start_result)
    _show("HITL1 REQUEST", hitl1)
    profile = _answer("HITL1 response: ", scripted=scripted, default="Use broad public sources")

    response1 = HumanMessage(
        content=profile,
        id="demo-human-hitl1",
        additional_kwargs={
            "human_input_response": {
                "version": 1,
                "kind": "human_input_response",
                "source": "deep_research",
                "request_id": hitl1["request_id"],
                "response_kind": "text",
                "value": profile,
            }
        },
    )
    research_id = start_result["research_id"]
    resume1_call = _tool_call("resume", "demo-call-resume-1", research_id)
    resumed = await run_deep_research(
        action="resume",
        probe_id=None,
        research_id=research_id,
        runtime=_runtime([start_user, response1, resume1_call], "demo-call-resume-1"),
        adapter=adapter,
        host_factory=lambda: host,
    )
    if not isinstance(resumed, Command):
        raise RuntimeError(f"demo first resume failed: {resumed}")
    resume_result, hitl2 = _suspension(resumed)
    _show("RESUME RESULT", resume_result)
    _show("HITL2 REQUEST", hitl2)
    advertised = [option["value"] for option in hitl2["options"]]
    print(f"Available decisions: {', '.join(advertised)}")
    decision = _answer("HITL2 decision: ", scripted=scripted, default="proceed").lower()
    if decision not in advertised:
        raise ValueError(f"decision must be one of: {', '.join(advertised)}")

    response2 = HumanMessage(
        content=decision,
        id="demo-human-hitl2",
        additional_kwargs={
            "human_input_response": {
                "version": 1,
                "kind": "human_input_response",
                "source": "deep_research",
                "request_id": hitl2["request_id"],
                "response_kind": "option",
                "option_id": decision,
                "value": decision,
            }
        },
    )
    resume2_call = _tool_call("resume", "demo-call-resume-2", research_id)
    completed = await run_deep_research(
        action="resume",
        probe_id=None,
        research_id=research_id,
        runtime=_runtime(
            [start_user, response1, response2, resume2_call],
            "demo-call-resume-2",
        ),
        adapter=adapter,
        host_factory=lambda: host,
    )
    if not isinstance(completed, dict):
        raise RuntimeError("demo terminal result was unexpectedly suspended")
    _show("TERMINAL RESULT", completed)
    print("\nDemo complete. This terminal state is a fixture, not completed research.")
    adapter.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--question",
        default="Compare the evidence for two approaches to renewable energy storage.",
        help="Visible HumanMessage used as the demo research request.",
    )
    parser.add_argument(
        "--scripted",
        action="store_true",
        help="Use deterministic HITL answers instead of prompting on stdin.",
    )
    parser.add_argument(
        "--real",
        action="store_true",
        help="Run non-agent nodes (hitl2, rerun, readiness, final_delivery) in real mode.",
    )
    args = parser.parse_args()
    asyncio.run(run_demo(question=args.question, scripted=args.scripted, real=args.real))


if __name__ == "__main__":
    main()
