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
from collections.abc import Iterable

_RESOURCE_ANCHOR = "deerflow_deep_research"
_POLICY_PARTS = ("resources", "node_agent", "runtime_policy.md")

UNTRUSTED_OPEN = "<untrusted-source-data>"
UNTRUSTED_CLOSE = "</untrusted-source-data>"


def load_policy_prompt() -> str:
    """Return the trusted system/policy prompt from package resources."""
    resource = importlib.resources.files(_RESOURCE_ANCHOR).joinpath(*_POLICY_PARTS)
    return resource.read_text(encoding="utf-8")


def build_untrusted_data_block(entries: Iterable[str]) -> str:
    """Wrap external source references/content in the delimited untrusted block.

    Any delimiter-like markers in the entries are neutralized so external content
    cannot forge the closing tag and smuggle itself back into trusted context.
    """
    safe_entries = []
    for entry in entries:
        text = entry if isinstance(entry, str) else str(entry)
        text = text.replace(UNTRUSTED_OPEN, "").replace(UNTRUSTED_CLOSE, "")
        safe_entries.append(text)
    body = "\n".join(safe_entries)
    return f"{UNTRUSTED_OPEN}\n{body}\n{UNTRUSTED_CLOSE}"


__all__ = [
    "UNTRUSTED_CLOSE",
    "UNTRUSTED_OPEN",
    "build_untrusted_data_block",
    "load_policy_prompt",
]
