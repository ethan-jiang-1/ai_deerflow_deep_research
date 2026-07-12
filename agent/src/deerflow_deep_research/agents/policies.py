"""Immutable execution policy, budget, and tool policy for the phase agent.

@impl NOA-002
@impl NOA-003

The policy is a frozen, model-independent value: exact allowed tool names,
typed per-tool ``ToolPolicySpec`` records, read and write roots, the active
attempt root, and every hard budget. Budget enforcement is admission control,
not only after-the-fact accounting, so every limit is a positive integer (or
positive wall-time) validated at construction. Tool authorization is deny by
default: a tool is eligible only when it is both allow-listed and backed by a
spec declaring its path fields, effect, native cancellability, and (for writes)
provider-verifiable final-boundary containment.
"""

from __future__ import annotations

import posixpath
from dataclasses import dataclass, field
from typing import Literal


class PolicyError(ValueError):
    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"[{code}] {detail}")
        self.code = code
        self.detail = detail


@dataclass(frozen=True)
class ExecutionBudget:
    """Hard, admission-controlled limits for one bounded agent run."""

    max_model_calls: int
    max_total_tool_calls: int
    max_tool_calls_per_response: int
    max_parallel_tool_calls: int
    total_token_budget: int
    per_call_output_token_cap: int
    per_tool_result_bytes: int
    structured_result_bytes: int
    wall_time_seconds: float

    def __post_init__(self) -> None:
        positive_ints = {
            "max_model_calls": self.max_model_calls,
            "max_total_tool_calls": self.max_total_tool_calls,
            "max_tool_calls_per_response": self.max_tool_calls_per_response,
            "max_parallel_tool_calls": self.max_parallel_tool_calls,
            "total_token_budget": self.total_token_budget,
            "per_call_output_token_cap": self.per_call_output_token_cap,
            "per_tool_result_bytes": self.per_tool_result_bytes,
            "structured_result_bytes": self.structured_result_bytes,
        }
        for name, value in positive_ints.items():
            if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
                raise PolicyError("budget_invalid", f"{name} must be a positive integer")
        if not isinstance(self.wall_time_seconds, (int, float)) or self.wall_time_seconds <= 0:
            raise PolicyError("budget_invalid", "wall_time_seconds must be positive")
        if self.max_tool_calls_per_response > self.max_total_tool_calls:
            raise PolicyError("budget_invalid", "per-response tool calls cannot exceed total tool calls")
        if self.max_parallel_tool_calls > self.max_tool_calls_per_response:
            raise PolicyError("budget_invalid", "parallel tool calls cannot exceed per-response tool calls")
        if self.per_call_output_token_cap > self.total_token_budget:
            raise PolicyError("budget_invalid", "per-call output cap cannot exceed the total token budget")


ToolEffect = Literal["read", "write", "none"]


def path_within_roots(path: str, roots: tuple[str, ...]) -> bool:
    """True when a normalized POSIX virtual path is contained by one root.

    ``normpath`` collapses ``..`` so a traversal that escapes a root cannot be
    contained. This is the virtual-path guard; a tool's provider is separately
    required to revalidate symlink containment at the real filesystem boundary.
    """
    if not isinstance(path, str) or not path:
        return False
    normalized = posixpath.normpath(path)
    for root in roots:
        root_normalized = posixpath.normpath(root)
        if normalized == root_normalized or normalized.startswith(f"{root_normalized}/"):
            return True
    return False


@dataclass(frozen=True)
class ToolPolicySpec:
    """Typed authorization record for one eligible tool (deny by default)."""

    tool_name: str
    effect: ToolEffect
    path_fields: tuple[str, ...] = ()
    native_cancellable: bool = False
    provider_containment_verified: bool = False

    def __post_init__(self) -> None:
        if not self.tool_name:
            raise PolicyError("tool_spec_invalid", "tool_name is required")
        if self.effect not in ("read", "write", "none"):
            raise PolicyError("tool_spec_invalid", "effect must be read, write, or none")

    @property
    def is_eligible(self) -> bool:
        # A tool with no approved native async/cancellable path is not eligible;
        # writes additionally require provider-verifiable final-boundary containment.
        if not self.native_cancellable:
            return False
        if self.effect == "write" and not self.provider_containment_verified:
            return False
        return True


@dataclass(frozen=True)
class ExecutionPolicy:
    """Immutable, model-safe policy passed to the full-takeover factory."""

    policy_name: str
    allowed_tool_names: frozenset[str]
    read_roots: tuple[str, ...]
    write_roots: tuple[str, ...]
    attempt_root: str
    budget: ExecutionBudget
    tool_specs: tuple[ToolPolicySpec, ...] = field(default_factory=tuple)
    structured_output_type: type | None = None

    def __post_init__(self) -> None:
        if not self.policy_name:
            raise PolicyError("policy_invalid", "policy_name is required")
        if not self.read_roots:
            raise PolicyError("policy_invalid", "at least one read root is required")
        if not self.attempt_root:
            raise PolicyError("policy_invalid", "attempt_root is required")
        # The model may only ever write under the active attempt root; phase,
        # gate, ledger, sibling-attempt, package-source, and host paths are never
        # writable. Enforcing containment here keeps the invariant close to the
        # policy value the middleware trusts.
        for write_root in self.write_roots:
            if write_root != self.attempt_root and not write_root.startswith(f"{self.attempt_root}/"):
                raise PolicyError("policy_invalid", "write roots must be contained by the attempt root")
        specs = {spec.tool_name: spec for spec in self.tool_specs}
        if len(specs) != len(self.tool_specs):
            raise PolicyError("policy_invalid", "duplicate tool spec names")
        object.__setattr__(self, "_spec_index", specs)

    def is_tool_allowed(self, name: str) -> bool:
        return name in self.allowed_tool_names

    def spec_for(self, name: str) -> ToolPolicySpec | None:
        return self._spec_index.get(name)  # type: ignore[attr-defined]


__all__ = [
    "ExecutionBudget",
    "ExecutionPolicy",
    "PolicyError",
    "ToolPolicySpec",
    "path_within_roots",
]
