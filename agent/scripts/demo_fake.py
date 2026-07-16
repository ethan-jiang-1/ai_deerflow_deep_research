#!/usr/bin/env python3
"""Full-fake pipeline demo — every phase visible, no Gateway needed.

Usage:
  make demo                    interactive
  make demo-scripted           non-interactive (CI)"""

from __future__ import annotations

import argparse, asyncio, json, secrets, tempfile, time
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

# ── adapter ──────────────────────────────────────────────────────────

class _AppCfg:
    checkpointer = None; database = None

class _Adapter:
    def __init__(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="deerflow-demo-")
        root = Path(self._tmp.name)
        for d in ("workspace","uploads","outputs"): (root/d).mkdir()
        self._env = TrustedRuntimeEnvelope(
            effective_user_id="demo-user", outer_thread_id="demo-thread",
            outer_run_id="demo-run", app_config=_AppCfg(),
            workspace_host_path=root/"workspace", uploads_host_path=root/"uploads",
            outputs_host_path=root/"outputs",
            workspace_virtual_root="/mnt/user-data/workspace",
            uploads_virtual_root="/mnt/user-data/uploads",
            outputs_virtual_root="/mnt/user-data/outputs",
            parent_sandbox=object(), progress=None)

    async def adapt(self, _rt, *, initialize_parent_sandbox=True):
        return self._env if initialize_parent_sandbox else replace(self._env, parent_sandbox=None)

    async def create_work_unit_store(self, _env, *, research_id):
        return WorkUnitStore(workspace_host_path=self._env.workspace_host_path,
            research_id=research_id, clock=lambda: datetime.now(UTC),
            monotonic=time.monotonic, lock_sleep=time.sleep,
            token_factory=lambda: secrets.token_hex(16), fault_hook=None)

    def close(self): self._tmp.cleanup()

# ── helpers ──────────────────────────────────────────────────────────

def _tc(action, cid, rid=None):
    a = {"action": action}
    if rid: a["research_id"] = rid
    return AIMessage(content="", tool_calls=[{"name":"deep_research","args":a,"id":cid}])

def _rt(msgs, cid): return SimpleNamespace(state={"messages":msgs}, context={}, tool_call_id=cid)

def _suspend(cmd):
    msg = cmd.update["messages"][0]
    return json.loads(msg.content), msg.artifact["human_input"]

def _ask(prompt, scripted, default):
    if scripted:
        print(f"  {prompt}{default}  [scripted]")
        return default
    v = input(f"  {prompt}[默认: {default}] ").strip()
    return v or default

def _progress(name, desc, suspended=False):
    print(f"  {'⏸' if suspended else '→'} {name:<22} {desc}")

# ── phases ───────────────────────────────────────────────────────────

_BEFORE_HITL1 = [("bootstrap","建立 research 环境")]
_BEFORE_HITL2 = [
    ("topic_planning","规划研究主题"), ("wave0","收集源数据"),
    ("wave1","深挖证据"), ("wave2","综合分析"),
    ("targeted_evidence","补证循环"),
]
_AFTER_HITL2 = [("readiness","可答性评估"), ("final_delivery","生成报告")]

# ── run ──────────────────────────────────────────────────────────────

async def run(*, question, scripted):
    print(f"\n{'─'*50}")
    print(f"  DeerFlow Deep Research · full-fake pipeline")
    print(f"{'─'*50}")

    ad = _Adapter()
    host = build_control_graph_host(
        fingerprint_verifier=lambda _: None,
        research_recipe=ResearchGraphRecipe.create(work_unit_store_factory=ad.create_work_unit_store))
    su = HumanMessage(content=question, id="u-start")

    # start
    started = await run_deep_research(action="start", probe_id=None,
        runtime=_rt([su, _tc("start","c0")], "c0"), adapter=ad, host_factory=lambda: host)
    if not isinstance(started, Command): raise RuntimeError(f"start failed: {started}")
    _, h1 = _suspend(started)
    for n,d in _BEFORE_HITL1: _progress(n,d,suspended=(n=="hitl1"))

    print(f"\n  📋 研究方向")
    profile = _ask("  → ", scripted, default="Use broad public sources")

    # resume 1
    rid = json.loads(started.update["messages"][0].content)["research_id"]
    r1 = HumanMessage(content=profile, id="u-h1", additional_kwargs={
        "human_input_response":{"version":1,"kind":"human_input_response",
        "source":"deep_research","request_id":h1["request_id"],
        "response_kind":"text","value":profile}})
    resumed = await run_deep_research(action="resume", probe_id=None, research_id=rid,
        runtime=_rt([su, r1, _tc("resume","c1",rid)], "c1"), adapter=ad, host_factory=lambda: host)
    if not isinstance(resumed, Command): raise RuntimeError(f"resume failed: {resumed}")
    _, h2 = _suspend(resumed)
    for n,d in _BEFORE_HITL2: _progress(n,d,suspended=(n=="hitl2"))

    print(f"\n  🎯 决策")
    opts = [o["value"] for o in h2.get("options",[])]
    for o in opts: print(f"    [{o}]")
    decision = _ask("  选择: ", scripted, default="proceed").lower()
    if decision not in opts: raise ValueError(f"无效: {decision}，可选: {opts}")

    # resume 2
    r2 = HumanMessage(content=decision, id="u-h2", additional_kwargs={
        "human_input_response":{"version":1,"kind":"human_input_response",
        "source":"deep_research","request_id":h2["request_id"],
        "response_kind":"option","option_id":decision,"value":decision}})
    done = await run_deep_research(action="resume", probe_id=None, research_id=rid,
        runtime=_rt([su, r1, r2, _tc("resume","c2",rid)], "c2"), adapter=ad, host_factory=lambda: host)
    if not isinstance(done, dict): raise RuntimeError("expected terminal")
    for n,d in _AFTER_HITL2: _progress(n,d)

    print(f"{'─'*50}")
    print(f"  ✓ 完成 · generation {done.get('generation','?')} · status: {done.get('status','?')}")
    print(f"{'─'*50}\n")
    ad.close()

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--question", default="Compare evidence for two approaches to renewable energy storage.")
    p.add_argument("--scripted", action="store_true")
    a = p.parse_args()
    asyncio.run(run(question=a.question, scripted=a.scripted))

if __name__ == "__main__":
    main()
