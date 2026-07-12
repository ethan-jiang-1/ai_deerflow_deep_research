"""Explicit fake/real implementation selection.

@impl REG-001
"""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType

from deerflow_deep_research.domain.node_spec import UNAVAILABLE_REAL_FACTORY, NodeFactory, NodeSpec


class ImplementationMapError(ValueError):
    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"[{code}] {detail}")
        self.code = code
        self.detail = detail


def resolve_implementations(specs: Mapping[str, NodeSpec], modes: Mapping[str, str]) -> Mapping[str, NodeFactory]:
    spec_names = set(specs)
    mode_names = set(modes)
    missing = spec_names - mode_names
    if missing:
        raise ImplementationMapError("implementation_map_incomplete", f"missing modes: {', '.join(sorted(missing))}")
    unknown = mode_names - spec_names
    if unknown:
        raise ImplementationMapError("implementation_map_unknown", f"unknown modes: {', '.join(sorted(unknown))}")
    resolved: dict[str, NodeFactory] = {}
    for logical_name, spec in specs.items():
        if spec.logical_name != logical_name:
            raise ImplementationMapError("implementation_spec_mismatch", logical_name)
        mode = modes[logical_name]
        if mode == "fake":
            resolved[logical_name] = spec.fake_factory
        elif mode == "real":
            if spec.real_factory is UNAVAILABLE_REAL_FACTORY:
                raise ImplementationMapError(
                    "implementation_unavailable",
                    f"real implementation unavailable for {logical_name}",
                )
            resolved[logical_name] = spec.real_factory
        else:
            raise ImplementationMapError("implementation_mode_invalid", f"invalid mode for {logical_name}")
    return MappingProxyType(resolved)


__all__ = ["ImplementationMapError", "resolve_implementations"]
