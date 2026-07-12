"""Reflected Deep Research control tool.

@impl RUI-001

``deep_research_tool`` is a thin async reflected tool. It validates strictly
(``extra="forbid"``, a bounded action plus an optional URL-safe opaque probe id),
asks the generic registry whether the action is registered before any adapter or
sandbox access, adapts trusted runtime through ``RuntimeAdapter``, and dispatches
to GraphHost. In change 00 the only registered action is ``infra_probe``; valid
lifecycle names (``start|resume|status|cancel``) and unknown names return a typed
``action_unavailable`` without echoing the rejected action. Validation failures
expose only field names and error codes, never Pydantic input values, rejected
payloads, host identities, or secret markers.
"""

from __future__ import annotations

import json
import secrets
from typing import Any

from langchain.tools import ToolRuntime
from langchain_core.tools import tool
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from deerflow_deep_research.runtime.identity import TrustedIdentityError
from deerflow_deep_research.runtime.probe import build_probe_graph_host
from deerflow_deep_research.runtime.runtime_adapter import RuntimeAdapter, RuntimeAdapterError

ADVERTISED_ACTION = "infra_probe"
_PROBE_ID_PATTERN = r"^[A-Za-z0-9_-]{1,64}$"


class DeepResearchArgs(BaseModel):
    """Strict tool arguments. Authority/path/sandbox fields are not legal."""

    model_config = ConfigDict(extra="forbid")

    action: str = Field(min_length=1, max_length=32)
    probe_id: str | None = Field(default=None, pattern=_PROBE_ID_PATTERN)


def generate_probe_id() -> str:
    """A bounded URL-safe opaque id with >=128 bits of CSPRNG entropy."""
    return secrets.token_urlsafe(16)


def normalize_validation_error(exc: ValidationError) -> dict[str, Any]:
    """Field names and error codes only -- never input values or messages."""
    fields = sorted({".".join(str(part) for part in error["loc"]) for error in exc.errors()})
    codes = sorted({error["type"] for error in exc.errors()})
    return {"code": "invalid_arguments", "fields": fields, "violations": codes}


async def run_deep_research(
    *,
    action: str,
    probe_id: str | None,
    runtime: Any,
    adapter: RuntimeAdapter | None = None,
    host_factory: Any = build_probe_graph_host,
) -> dict[str, Any]:
    """Core dispatch: registry presence -> adapter -> GraphHost run."""
    host = host_factory()
    if not host.is_registered(action):
        # Do not echo the rejected action; advertise only what is supported.
        return {"code": "action_unavailable", "supported": [ADVERTISED_ACTION]}

    adapter = adapter or RuntimeAdapter()
    try:
        envelope = await adapter.adapt(runtime)
    except (TrustedIdentityError, RuntimeAdapterError) as exc:
        return {"code": exc.code}

    resolved_probe_id = probe_id or generate_probe_id()
    return await host.run_action(action=action, envelope=envelope, action_input=resolved_probe_id)


@tool("deep_research", args_schema=DeepResearchArgs)
async def deep_research_tool(action: str, probe_id: str | None = None, runtime: ToolRuntime = None) -> str:
    """Route a Deep Research control action. Change 00 supports only infra_probe.

    Args:
        action: The control action. Only ``infra_probe`` is available.
        probe_id: Optional opaque URL-safe id to revisit a prior probe checkpoint.
    """
    try:
        args = DeepResearchArgs(action=action, probe_id=probe_id)
    except ValidationError as exc:
        return json.dumps(normalize_validation_error(exc), sort_keys=True)
    result = await run_deep_research(action=args.action, probe_id=args.probe_id, runtime=runtime)
    return json.dumps(result, sort_keys=True)


__all__ = ["DeepResearchArgs", "deep_research_tool", "generate_probe_id", "run_deep_research"]
