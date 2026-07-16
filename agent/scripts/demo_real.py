#!/usr/bin/env python3
"""Real-mode CLI demo — full 11-phase pipeline with actual LLM + web search.

@impl DPL-004

Requires ANTHROPIC_API_KEY in environment. Optionally TAVILY_API_KEY or
equivalent for web search tools.

Usage:
  make demo-real               interactive
  make demo-real-scripted      non-interactive (CI)"""

from __future__ import annotations

import argparse
import asyncio
import sys

from _demo_core import (
    DemoAdapter,
    _answer,
    _runtime,
    _suspension,
    _tool_call,
    build_demo_host,
    build_demo_recipe,
    check_credentials_available,
    create_hitl_response,
    display_phase_progress,
)
from langchain_core.messages import HumanMessage
from langgraph.types import Command

from deerflow_deep_research.tool import run_deep_research

SCRIPTED_CONTEXT = {"non_interactive_policy": {"auto_profile": True, "auto_proceed": True}}


def _ask(prompt: str, *, scripted: bool, default: str) -> str:
    return _answer(prompt, scripted=scripted, default=default)


async def run_demo(*, question: str, scripted: bool) -> None:
    print(f"\n{'─' * 50}")
    print("  DeerFlow Deep Research · all-real pipeline")
    print("  Requires API key — real LLM + web search")
    print(f"{'─' * 50}")

    adapter = DemoAdapter()
    recipe = build_demo_recipe(mode="real", work_unit_store_factory=adapter.create_work_unit_store)
    host = build_demo_host(recipe=recipe)

    start_user = HumanMessage(content=question, id="demo-real-human-start")
    start_call = _tool_call("start", "demo-real-call-start")
    ctx = SCRIPTED_CONTEXT if scripted else None

    started = await run_deep_research(
        action="start",
        probe_id=None,
        runtime=_runtime([start_user, start_call], "demo-real-call-start", context=ctx),
        adapter=adapter,
        host_factory=lambda: host,
    )
    if not isinstance(started, Command):
        raise RuntimeError(f"start failed: {started}")
    control1, hitl1 = _suspension(started)

    previous_trace: tuple[str, ...] = ()
    current_trace = tuple(control1.get("execution_trace", ()))
    new_phases = [p for p in current_trace if p not in previous_trace]
    display_phase_progress(new_phases, suspended_at=control1.get("phase"))
    previous_trace = current_trace

    if scripted:
        profile = "Use broad public sources"
        print(f"  📋 研究方向 → {profile}  [scripted]")
    else:
        print("\n  📋 研究方向")
        profile = _ask("  → ", scripted=False, default="Use broad public sources")

    response1 = create_hitl_response(
        value=profile,
        request_id=hitl1["request_id"],
        message_id="demo-real-human-hitl1",
        response_kind="text",
    )
    research_id = control1["research_id"]
    resume1_call = _tool_call("resume", "demo-real-call-resume-1", research_id)
    resumed = await run_deep_research(
        action="resume",
        probe_id=None,
        research_id=research_id,
        runtime=_runtime(
            [start_user, response1, resume1_call],
            "demo-real-call-resume-1",
            context=ctx,
        ),
        adapter=adapter,
        host_factory=lambda: host,
    )
    if not isinstance(resumed, Command):
        raise RuntimeError(f"first resume failed: {resumed}")
    control2, hitl2 = _suspension(resumed)

    current_trace = tuple(control2.get("execution_trace", ()))
    new_phases = [p for p in current_trace if p not in previous_trace]
    display_phase_progress(new_phases, suspended_at=control2.get("phase"))
    previous_trace = current_trace

    advertised = [option["value"] for option in hitl2.get("options", [])]
    if scripted:
        decision = "proceed"
        print(f"\n  🎯 决策 → {decision}  [scripted]")
    else:
        print("\n  🎯 决策")
        for opt in advertised:
            print(f"    [{opt}]")
        decision = _ask("  选择: ", scripted=False, default="proceed").lower()
    if decision not in advertised:
        raise ValueError(f"无效决策: {decision}，可选: {advertised}")

    response2 = create_hitl_response(
        value=decision,
        request_id=hitl2["request_id"],
        message_id="demo-real-human-hitl2",
        response_kind="option",
    )
    resume2_call = _tool_call("resume", "demo-real-call-resume-2", research_id)
    completed = await run_deep_research(
        action="resume",
        probe_id=None,
        research_id=research_id,
        runtime=_runtime(
            [start_user, response1, response2, resume2_call],
            "demo-real-call-resume-2",
            context=ctx,
        ),
        adapter=adapter,
        host_factory=lambda: host,
    )
    if not isinstance(completed, dict):
        raise RuntimeError("terminal result was unexpectedly suspended")

    current_trace = tuple(completed.get("execution_trace", ()))
    new_phases = [p for p in current_trace if p not in previous_trace]
    display_phase_progress(new_phases, suspended_at=None)

    print(f"{'─' * 50}")
    print(f"  ✓ 完成 · generation {completed.get('generation', '?')} · status: {completed.get('status', '?')}")
    print(f"{'─' * 50}\n")
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
    args = parser.parse_args()

    if not check_credentials_available():
        print(
            "❌ No API key found in environment.\n"
            "   Real-mode demo requires model credentials.\n"
            "   Export one of: ANTHROPIC_API_KEY, DEEPSEEK_API_KEY, OPENAI_API_KEY and retry.",
            file=sys.stderr,
        )
        sys.exit(1)

    asyncio.run(run_demo(question=args.question, scripted=args.scripted))


if __name__ == "__main__":
    main()
