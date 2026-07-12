"""Progress projection over the supported LangGraph stream-writer API.

@impl RUI-002

The emitter degrades to an in-memory collector when no stream writer is bound
(unit tests, non-streaming callers). It never reaches into a private Gateway
event store. Group 11 finalizes the redacted event schema; this module provides
only the supported acquisition path and a bounded emit surface.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ProgressEmitter:
    """Emit bounded progress events through an injected sink."""

    _sink: Callable[[dict[str, Any]], None]
    collected: list[dict[str, Any]] = field(default_factory=list)

    def emit(self, event: dict[str, Any]) -> None:
        self.collected.append(event)
        self._sink(event)


_MAX_DETAIL_CHARS = 256


def build_progress_event(
    *,
    kind: str,
    ref: str,
    operation: str,
    status: str,
    detail: str = "",
) -> dict[str, Any]:
    """Build a stable, redacted progress event with bounded detail."""
    from deerflow_deep_research.agents.structured_output import redact

    return {
        "kind": kind,
        "ref": ref,
        "operation": operation,
        "status": status,
        "detail": redact(detail)[:_MAX_DETAIL_CHARS] if detail else "",
    }


def _resolve_stream_writer() -> Callable[[dict[str, Any]], None]:
    try:
        from langgraph.config import get_stream_writer

        writer = get_stream_writer()
    except (RuntimeError, ImportError):
        writer = None
    if writer is None:
        return lambda _event: None
    return writer


def make_progress_emitter(sink: Callable[[dict[str, Any]], None] | None = None) -> ProgressEmitter:
    return ProgressEmitter(_sink=sink if sink is not None else _resolve_stream_writer())


__all__ = ["ProgressEmitter", "build_progress_event", "make_progress_emitter"]
