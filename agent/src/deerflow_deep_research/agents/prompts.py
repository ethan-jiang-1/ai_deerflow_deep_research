"""Package-resource prompt loading and untrusted-source projection.

@impl NOA-004

System and policy prompts are loaded verbatim from package resources so they are
byte-stable regardless of external source content. External source material is
never interpolated into those trusted instructions: it is projected only into a
clearly delimited untrusted-data block (or referenced as a sandbox artifact), and
its instructions carry no tool, path, phase, gate, or ledger authority.
"""

from __future__ import annotations

import importlib.resources

from deerflow_deep_research.domain.untrusted import (
    UNTRUSTED_CLOSE,
    UNTRUSTED_OPEN,
    build_untrusted_data_block,
)

_RESOURCE_ANCHOR = "deerflow_deep_research"
_POLICY_PARTS = ("resources", "node_agent", "runtime_policy.md")


def load_policy_prompt() -> str:
    """Return the trusted system/policy prompt from package resources."""
    resource = importlib.resources.files(_RESOURCE_ANCHOR).joinpath(*_POLICY_PARTS)
    return resource.read_text(encoding="utf-8")


__all__ = [
    "UNTRUSTED_CLOSE",
    "UNTRUSTED_OPEN",
    "build_untrusted_data_block",
    "load_policy_prompt",
]
