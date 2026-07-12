"""Full-takeover embedded phase-agent factory.

@impl NOA-001

This factory wraps ``create_deerflow_agent`` in full-takeover mode: the exact
``middleware`` list is used verbatim, so DeerFlow adds none of its default
feature middleware (memory, title, uploads, subagents, skill evolution, todo,
clarification, sandbox lifecycle) and injects no tools. ``checkpointer=None`` is
always passed so the embedded agent has no independent persistence and can never
inherit the parent saver.

The factory imports no runtime layer. It accepts already resolved model/tools,
a package-owned system prompt, and a curated middleware chain; identity, host
paths, sandbox internals, and AppConfig never reach it.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

PHASE_AGENT_NAME = "deep-research-phase"


def build_phase_agent(
    *,
    model: Any,
    tools: Sequence[Any],
    middleware: Sequence[Any],
    system_prompt: str,
    name: str = PHASE_AGENT_NAME,
) -> Any:
    """Build one bounded, non-persistent phase agent as a separate runnable."""
    from deerflow.agents.factory import create_deerflow_agent

    return create_deerflow_agent(
        model=model,
        tools=list(tools),
        middleware=list(middleware),
        system_prompt=system_prompt,
        checkpointer=None,
        name=name,
    )


__all__ = ["PHASE_AGENT_NAME", "build_phase_agent"]
