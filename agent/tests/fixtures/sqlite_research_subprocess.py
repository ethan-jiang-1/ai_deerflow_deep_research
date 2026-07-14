"""Start or resume one fake research lifecycle in a fresh process.

The durability suite invokes this script twice against the same file-backed
SQLite database.  Each invocation constructs and closes a new provider context,
so the resume path proves recovery without process-local state.
"""

from __future__ import annotations

import asyncio
import json
import secrets
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

from langchain_core.messages import HumanMessage

from deerflow_deep_research.domain.lifecycle import LifecycleAction
from deerflow_deep_research.runtime.control import build_control_graph_host
from deerflow_deep_research.runtime.human_input import SelectedStartMessage
from deerflow_deep_research.runtime.research import ResearchActionInput, derive_research_id
from deerflow_deep_research.runtime.runtime_adapter import TrustedRuntimeEnvelope
from deerflow_deep_research.runtime.work_unit_store import WorkUnitStore


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


def _payload(result: object) -> tuple[dict[str, object], dict[str, object]]:
    message = result.update["messages"][0]
    return json.loads(message.content), message.artifact["human_input"]


async def _main() -> None:
    db_path, mode = sys.argv[1], sys.argv[2]
    previous_request_id = sys.argv[3] if len(sys.argv) > 3 else None
    app_config = SimpleNamespace(
        checkpointer=SimpleNamespace(type="sqlite", connection_string=db_path),
        database=None,
    )
    envelope = _envelope(app_config)
    workspace = Path(db_path).parent / "workspace"
    workspace.mkdir(exist_ok=True)

    async def create(_cls, _envelope, *, research_id, **_kwargs):
        return WorkUnitStore(
            workspace_host_path=workspace,
            research_id=research_id,
            clock=lambda: datetime(2026, 7, 14, tzinfo=UTC),
            monotonic=time.monotonic,
            lock_sleep=time.sleep,
            token_factory=lambda: secrets.token_hex(16),
            fault_hook=None,
        )

    WorkUnitStore.create = classmethod(create)
    research_id = derive_research_id(
        effective_user_id=envelope.effective_user_id,
        outer_thread_id=envelope.outer_thread_id,
    )
    host = build_control_graph_host(fingerprint_verifier=lambda _app_config: None)

    if mode == "start":
        action_input = ResearchActionInput(
            action=LifecycleAction.START,
            research_id=research_id,
            tool_call_id="call-start",
            messages=(),
            start_message=SelectedStartMessage(message_id="human-start", text="research question"),
        )
    elif mode == "resume" and previous_request_id:
        response = HumanMessage(
            content="profile answer",
            id="human-response",
            additional_kwargs={
                "human_input_response": {
                    "version": 1,
                    "kind": "human_input_response",
                    "source": "deep_research",
                    "request_id": previous_request_id,
                    "response_kind": "text",
                    "value": "profile answer",
                }
            },
        )
        action_input = ResearchActionInput(
            action=LifecycleAction.RESUME,
            research_id=research_id,
            tool_call_id="call-resume",
            messages=(HumanMessage(content="research question", id="human-start"), response),
        )
    else:
        raise SystemExit("usage: sqlite_research_subprocess.py <db> start|resume [request-id]")

    result = await host.run_action(action=mode, envelope=envelope, action_input=action_input)
    control, request = _payload(result)
    print(
        json.dumps(
            {
                "research_id": control["research_id"],
                "request_id": request["request_id"],
                "code": control["code"],
                "durability": control["durability"],
                "implementation_mode": control["implementation_mode"],
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    asyncio.run(_main())
