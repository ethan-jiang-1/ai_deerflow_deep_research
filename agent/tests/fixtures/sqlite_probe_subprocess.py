"""Run one infra_probe against a SQLite checkpoint file in a fresh process.

Invoked by the durability test as ``python sqlite_probe_subprocess.py <db> <id>``
to prove a file-backed SQLite checkpoint survives a real process restart.
Prints the opaque probe result as JSON on stdout.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from types import SimpleNamespace

from deerflow_deep_research.runtime.probe import build_probe_graph_host
from deerflow_deep_research.runtime.runtime_adapter import TrustedRuntimeEnvelope


def _envelope(app_config: object) -> TrustedRuntimeEnvelope:
    return TrustedRuntimeEnvelope(
        effective_user_id="alice",
        outer_thread_id="thread-1",
        outer_run_id="run-1",
        app_config=app_config,
        workspace_host_path=Path("/x/workspace"),
        uploads_host_path=Path("/x/uploads"),
        outputs_host_path=Path("/x/outputs"),
        workspace_virtual_root="/mnt/user-data/workspace",
        uploads_virtual_root="/mnt/user-data/uploads",
        outputs_virtual_root="/mnt/user-data/outputs",
        parent_sandbox=object(),
        progress=None,
    )


async def _main() -> None:
    db_path, probe_id = sys.argv[1], sys.argv[2]
    app_config = SimpleNamespace(
        checkpointer=SimpleNamespace(type="sqlite", connection_string=db_path),
        database=None,
    )
    host = build_probe_graph_host(fingerprint_verifier=lambda _app_config: None)
    result = await host.run_action(action="infra_probe", envelope=_envelope(app_config), action_input=probe_id)
    print(json.dumps({key: result[key] for key in ("previous_visit", "current_visit", "provider_kind", "durability")}))


if __name__ == "__main__":
    asyncio.run(_main())
