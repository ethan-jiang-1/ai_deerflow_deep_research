"""Untrusted-data block contract — usable from any layer.

External source content is placed only in this clearly delimited block;
its instructions carry no tool, path, phase, gate, or ledger authority.

@impl NOA-004
"""

from __future__ import annotations

from collections.abc import Iterable

UNTRUSTED_OPEN = "<untrusted-source-data>"
UNTRUSTED_CLOSE = "</untrusted-source-data>"


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
