"""Pure typed-verdict routers for the stable topology.

@impl REG-002
"""

from __future__ import annotations

from enum import StrEnum


def route_typed(value: StrEnum, *, allowed: type[StrEnum]) -> str:
    if not isinstance(value, allowed):
        raise TypeError(f"route requires {allowed.__name__}")
    return value.value


__all__ = ["route_typed"]
