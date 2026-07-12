"""Downstream Deep Research package for DeerFlow.

@impl PRS-001
"""

from importlib import import_module
from typing import Any

from deerflow_deep_research.__about__ import __version__

__all__ = ["__version__", "deep_research_tool"]

_LAZY_EXPORTS = {
    "deep_research_tool": ("deerflow_deep_research.tool", "deep_research_tool"),
}


def __getattr__(name: str) -> Any:
    """Resolve heavyweight runtime exports only when callers request them."""
    target = _LAZY_EXPORTS.get(name)
    if target is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module_name, attribute = target
    value = getattr(import_module(module_name), attribute)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(__all__))
