#!/usr/bin/env python3
"""Shared demo infrastructure for CLI and TUI research lifecycle demos.

@impl DPL-001
@impl DPL-003
"""

from __future__ import annotations

import json
import os
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

from deerflow_deep_research.graph.topology import LOGICAL_NODES
from deerflow_deep_research.runtime.control import build_control_graph_host
from deerflow_deep_research.runtime.node_agent_bridge import RuntimeNodeAgentBridge
from deerflow_deep_research.runtime.research import ResearchGraphRecipe
from deerflow_deep_research.runtime.runtime_adapter import TrustedRuntimeEnvelope
from deerflow_deep_research.runtime.work_unit_store import WorkUnitStore
from deerflow.sandbox.local.local_sandbox import LocalSandbox, PathMapping

# ── adapter ──────────────────────────────────────────────────────────


_KNOWN_API_KEY_VARS = (
    "ANTHROPIC_API_KEY",
    "DEEPSEEK_API_KEY",
    "OPENAI_API_KEY",
)

# Each entry: (env_var, model_name, use_path, model_id, base_url, extra_kwargs)
_MODEL_REGISTRY = (
    ("DEEPSEEK_API_KEY", "deepseek-v4-pro", "deerflow.models.patched_deepseek:PatchedChatDeepSeek", "deepseek-v4-pro", "https://api.deepseek.com/v1", {}),
    ("DEEPSEEK_API_KEY", "deepseek-v4-flash", "deerflow.models.patched_deepseek:PatchedChatDeepSeek", "deepseek-v4-flash", "https://api.deepseek.com/v1", {}),
    ("ANTHROPIC_API_KEY", "anthropic-demo", "langchain_anthropic:ChatAnthropic", "claude-sonnet-4-5-20250901", None, {}),
    ("OPENAI_API_KEY", "openai-demo", "langchain_openai:ChatOpenAI", "gpt-4o", None, {}),
)


def _resolve_demo_models():
    """Build ModelConfig entries for every available env credential."""
    from deerflow.config.model_config import ModelConfig

    models = []
    for env_var, name, use_path, model_id, base_url, extra in _MODEL_REGISTRY:
        if env_var in os.environ:
            cfg: dict[str, Any] = {"name": name, "use": use_path, "model": model_id, "api_key": os.environ[env_var], **extra}
            if base_url is not None:
                cfg["base_url"] = base_url
            models.append(ModelConfig(**cfg))
    return models


class _DemoSandboxConfig:
    use = "deerflow.sandbox.local:LocalSandboxProvider"


class DemoAppConfig:
    """Minimal config shim for the standalone demo.

    Provides a single auto-detected model plus a local-sandbox stub so the
    work-unit storage classifier and model factory both resolve without a full
    ``config.yaml``.
    """

    checkpointer = None
    database = None
    sandbox = _DemoSandboxConfig()
    tools: list[Any] = []

    def __init__(self) -> None:
        self._models = _resolve_demo_models()
        self.models = self._models

    def get_model_config(self, name: str):
        for model in self._models:
            if model.name == name:
                return model
        return None


def _prime_demo_sandbox(sandbox: Any) -> None:
    """Register *sandbox* as the generic singleton inside the global provider.

    The work-unit storage verifier calls ``provider.get(parent.id)`` and
    expects the same instance back.  For the demo we set the provider's
    internal ``_generic_sandbox`` so the lookup succeeds.
    """
    from deerflow.sandbox import get_sandbox_provider

    provider = get_sandbox_provider()
    # LocalSandboxProvider stores the legacy "local" singleton here.
    provider._generic_sandbox = sandbox


async def _demo_storage_verifier(envelope: Any, *, research_id: str, provider: Any = None) -> Any:
    """Return a ready check without running the full POSIX probe.

    The probe exercises edge cases (lock/fsync/aliased-readback/cleanup) that
    are already covered by the unit suite. For a demo run on a real temp dir
    we skip those to keep startup fast and avoid cleanup-ordering issues with
    the process-local provider.
    """
    from deerflow_deep_research.runtime.work_unit_storage import WorkUnitStorageCheck

    return WorkUnitStorageCheck("ready", "local_thread_mount")


# Patch all work-unit store classes to skip the storage probe in demo mode.
# Only overrides the *default* verifier; explicit callers (tests, real Gateway)
# that pass a custom ``storage_verifier`` are unaffected.
def _install_demo_storage_patch() -> None:
    from deerflow_deep_research.runtime import bootstrap_bundle as _bb
    from deerflow_deep_research.runtime import request_bundle as _rb
    from deerflow_deep_research.runtime import work_unit_store as _ws

    _targets = [
        (_bb, "BootstrapBundleStore"),
        (_rb, "RequestBundleStore"),
        (_ws, "WorkUnitStore"),
    ]
    for _mod, _cls_name in _targets:
        _cls = getattr(_mod, _cls_name, None)
        if _cls is None:
            continue
        _orig_create = _cls.create

        def _make_patched(orig, demo_verifier):
            @classmethod
            async def _patched(cls, envelope, *, research_id, storage_verifier=None, provider=None, **kw):
                return await orig.__func__(
                    cls,
                    envelope,
                    research_id=research_id,
                    storage_verifier=demo_verifier if storage_verifier is None else storage_verifier,
                    provider=provider,
                    **kw,
                )
            return _patched

        _cls.create = _make_patched(_orig_create, _demo_storage_verifier)


class DemoAdapter:
    def __init__(self) -> None:
        self._temporary = tempfile.TemporaryDirectory(prefix="deerflow-deep-research-demo-")
        root = Path(self._temporary.name)
        workspace = root / "workspace"
        uploads = root / "uploads"
        outputs = root / "outputs"
        for path in (workspace, uploads, outputs):
            path.mkdir()

        # Create a proper LocalSandbox so the work-unit storage verification can
        # exercise real POSIX primitives (aliased read/write, directory listing).
        sandbox = LocalSandbox(
            id="local",
            path_mappings=[
                PathMapping(container_path="/mnt/user-data/workspace", local_path=str(workspace)),
                PathMapping(container_path="/mnt/user-data/uploads", local_path=str(uploads)),
                PathMapping(container_path="/mnt/user-data/outputs", local_path=str(outputs)),
            ],
        )
        # Register with the global sandbox provider so provider.get("local")
        # returns our sandbox (required by verify_runtime_work_unit_storage).
        _prime_demo_sandbox(sandbox)

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
            parent_sandbox=sandbox,
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


# ── helpers ──────────────────────────────────────────────────────────


def _tool_call(action: str, call_id: str, research_id: str | None = None) -> AIMessage:
    args: dict[str, str] = {"action": action}
    if research_id is not None:
        args["research_id"] = research_id
    return AIMessage(
        content="",
        tool_calls=[{"name": "deep_research", "args": args, "id": call_id}],
    )


def _runtime(
    messages: list[Any],
    call_id: str,
    context: dict[str, Any] | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        state={"messages": messages},
        context=context if context is not None else {},
        tool_call_id=call_id,
    )


def _suspension(command: Command) -> tuple[dict[str, Any], dict[str, Any]]:
    message = command.update["messages"][0]
    return json.loads(message.content), message.artifact["human_input"]


def create_hitl_response(
    *,
    value: str,
    request_id: str,
    message_id: str,
    response_kind: str,
    option_id: str | None = None,
) -> HumanMessage:
    payload: dict[str, Any] = {
        "version": 1,
        "kind": "human_input_response",
        "source": "deep_research",
        "request_id": request_id,
        "response_kind": response_kind,
        "value": value,
    }
    if response_kind == "option":
        payload["option_id"] = value
    return HumanMessage(
        content=value,
        id=message_id,
        additional_kwargs={"human_input_response": payload},
    )


# ── phase metadata ───────────────────────────────────────────────────


PHASE_META: dict[str, tuple[str, str]] = {
    "bootstrap": ("初始化", "建立 research 环境"),
    "hitl1": ("研究配置", "确定研究方向与范围"),
    "topic_planning": ("主题规划", "拆解研究问题为子主题"),
    "wave0": ("源数据收集", "收集初步资料"),
    "wave1": ("深度证据", "深挖关键证据"),
    "wave2_synthesis": ("综合分析", "跨主题综合"),
    "targeted_evidence": ("补证", "针对性补充证据"),
    "hitl2": ("决策", "人工评判与方向选择"),
    "rerun": ("重搜索", "按新方向重新搜索"),
    "readiness": ("可答性评估", "检查证据是否充分"),
    "final_delivery": ("报告生成", "输出最终报告"),
}


# ── recipe / host factories ──────────────────────────────────────────


ALL_REAL_MODES: dict[str, str] = {name: "real" for name in LOGICAL_NODES}


def build_demo_recipe(
    *,
    mode: str,
    work_unit_store_factory: Any,
) -> ResearchGraphRecipe:
    """Build a ResearchGraphRecipe for the given mode.

    @impl DPL-003

    Args:
        mode: ``"fake"`` or ``"real"``.
        work_unit_store_factory: Factory for ``WorkUnitStore`` creation.

    Returns:
        A ``ResearchGraphRecipe`` configured for the requested mode.
    """
    if mode == "fake":
        return ResearchGraphRecipe.create(
            work_unit_store_factory=work_unit_store_factory,
        )
    if mode == "real":
        return ResearchGraphRecipe.create(
            implementation_modes=ALL_REAL_MODES,
            work_unit_store_factory=work_unit_store_factory,
            node_agent_bridge_factory=RuntimeNodeAgentBridge,
        )
    raise ValueError(f"Unknown demo mode: {mode!r}")


def build_demo_host(*, recipe: ResearchGraphRecipe) -> Any:
    return build_control_graph_host(
        fingerprint_verifier=lambda _app_config: None,
        research_recipe=recipe,
    )




def check_credentials_available() -> bool:
    return any(var in os.environ for var in _KNOWN_API_KEY_VARS)


# ── phase progress display ───────────────────────────────────────────


def display_phase_progress(
    phases: list[str],
    *,
    suspended_at: str | None = None,
) -> None:
    """Display pipeline phase progress with human-readable labels.

    @impl DPL-002

    Args:
        phases: Phase names in execution order.
        suspended_at: The phase at which the graph is currently suspended,
            if any. Displayed with ⏸ marker instead of →.
    """
    for name in phases:
        label, desc = PHASE_META.get(name, (name, ""))
        if name == suspended_at:
            print(f"  ⏸ {label:<18} {desc}")
        else:
            print(f"  → {label:<18} {desc}")


# ── answer helper (CLI) ──────────────────────────────────────────────


def _answer(prompt: str, *, scripted: bool, default: str) -> str:
    if scripted:
        print(f"  {prompt}{default}  [scripted]")
        return default
    value = input(f"  {prompt}[默认: {default}] ").strip()
    return value or default


# ── install demo patches at import time ──────────────────────────────

_install_demo_storage_patch()
