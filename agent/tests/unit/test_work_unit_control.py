from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from deerflow_deep_research.domain.lifecycle import (
    InfrastructureResultCode,
    WorkUnitStorageReason,
)
from deerflow_deep_research.runtime.runtime_adapter import TrustedRuntimeEnvelope
from deerflow_deep_research.runtime.work_unit_storage import WorkUnitStoreError
from deerflow_deep_research.tool import run_deep_research

RESEARCH_ID = "r_" + "A" * 43


def _envelope(parent_sandbox: object | None) -> TrustedRuntimeEnvelope:
    return TrustedRuntimeEnvelope(
        effective_user_id="alice",
        outer_thread_id="thread-1",
        outer_run_id="run-1",
        app_config=object(),
        workspace_host_path=Path("/redacted/workspace"),
        uploads_host_path=Path("/redacted/uploads"),
        outputs_host_path=Path("/redacted/outputs"),
        workspace_virtual_root="/mnt/user-data/workspace",
        uploads_virtual_root="/mnt/user-data/uploads",
        outputs_virtual_root="/mnt/user-data/outputs",
        parent_sandbox=parent_sandbox,
        progress=None,
    )


class RecordingAdapter:
    def __init__(self) -> None:
        self.initialize_values: list[bool] = []

    async def adapt(self, _runtime, *, initialize_parent_sandbox: bool):
        self.initialize_values.append(initialize_parent_sandbox)
        return _envelope(object() if initialize_parent_sandbox else None)


class RaisingHost:
    def __init__(self, error: BaseException) -> None:
        self.error = error

    def is_registered(self, _action: str) -> bool:
        return True

    async def run_action(self, **_kwargs):
        raise self.error


@pytest.mark.parametrize("reason", tuple(WorkUnitStorageReason))
def test_work_unit_store_error_has_complete_closed_code_pairing(reason: WorkUnitStorageReason) -> None:
    error = WorkUnitStoreError(reason)
    expected = (
        InfrastructureResultCode.WORK_UNIT_STORE_BUSY
        if reason is WorkUnitStorageReason.LOCK_TIMEOUT
        else InfrastructureResultCode.WORK_UNIT_STORAGE_UNAVAILABLE
    )
    assert error.code is expected
    assert error.reason is reason


def _runtime(action: str) -> SimpleNamespace:
    call_id = "call-1"
    return SimpleNamespace(
        tool_call_id=call_id,
        context={},
        state={
            "messages": [
                HumanMessage(content="Research topic", id="human-1"),
                AIMessage(
                    content="",
                    tool_calls=[{"name": "deep_research", "args": {"action": action}, "id": call_id}],
                ),
            ]
        },
    )


@pytest.mark.parametrize(
    ("action", "initialize"), [("start", True), ("resume", True), ("status", False), ("cancel", False)]
)
async def test_tool_selects_parent_sandbox_only_for_graph_start_resume(action: str, initialize: bool) -> None:
    adapter = RecordingAdapter()
    host = RaisingHost(WorkUnitStoreError(WorkUnitStorageReason.LEDGER_CORRUPT))
    result = await run_deep_research(
        action=action,
        probe_id=None,
        research_id=None if action == "start" else RESEARCH_ID,
        runtime=_runtime(action),
        adapter=adapter,
        host_factory=lambda: host,
    )
    assert adapter.initialize_values == [initialize]
    assert result["code"] == InfrastructureResultCode.WORK_UNIT_STORAGE_UNAVAILABLE
    assert result["infrastructure_reason"] == WorkUnitStorageReason.LEDGER_CORRUPT
    assert "detail" not in result and "/redacted" not in str(result)


async def test_lock_timeout_is_retryable_busy_and_unknown_exception_is_redacted() -> None:
    busy = await run_deep_research(
        action="status",
        probe_id=None,
        research_id=RESEARCH_ID,
        runtime=_runtime("status"),
        adapter=RecordingAdapter(),
        host_factory=lambda: RaisingHost(WorkUnitStoreError(WorkUnitStorageReason.LOCK_TIMEOUT)),
    )
    assert busy["code"] == InfrastructureResultCode.WORK_UNIT_STORE_BUSY
    assert busy["infrastructure_reason"] == WorkUnitStorageReason.LOCK_TIMEOUT

    redacted = await run_deep_research(
        action="status",
        probe_id=None,
        research_id=RESEARCH_ID,
        runtime=_runtime("status"),
        adapter=RecordingAdapter(),
        host_factory=lambda: RaisingHost(RuntimeError("/secret/host/path")),
    )
    assert redacted["code"] == "checkpoint_inconsistent"
    assert "/secret" not in str(redacted)


async def test_cancellation_is_never_projected_as_checkpoint_failure() -> None:
    with pytest.raises(asyncio.CancelledError):
        await run_deep_research(
            action="status",
            probe_id=None,
            research_id=RESEARCH_ID,
            runtime=_runtime("status"),
            adapter=RecordingAdapter(),
            host_factory=lambda: RaisingHost(asyncio.CancelledError()),
        )
