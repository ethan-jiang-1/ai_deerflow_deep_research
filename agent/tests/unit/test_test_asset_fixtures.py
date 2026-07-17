"""Shared runtime/model/tool test adapter contracts.

@impl EVH-006
@impl EVH-007
@impl EVH-008
"""

from __future__ import annotations

import pytest

from tests.fixtures.runtime import local_runtime_envelope, redact_diagnostic, unique_run_identity
from tests.fixtures.scripted_tools import scripted_web_tools


def test_local_runtime_fixture_has_valid_unique_authority(tmp_path) -> None:
    first = unique_run_identity()
    second = unique_run_identity()
    assert first.thread_id != second.thread_id
    assert first.run_id != second.run_id
    envelope = local_runtime_envelope(tmp_path, identity=first)
    assert envelope.parent_sandbox.id.startswith("local:")
    assert envelope.workspace_host_path.is_dir()
    assert envelope.outer_thread_id == first.thread_id


def test_diagnostic_redaction_removes_secret_and_host_path() -> None:
    result = redact_diagnostic("api_key=abc /Users/alice/private/file")
    assert "abc" not in result
    assert "/Users/alice" not in result
    assert "<redacted>" in result and "<host-path>" in result


async def test_scripted_web_tools_record_success_and_failure() -> None:
    search, fetch = scripted_web_tools(search=("one", RuntimeError("offline")))
    tool = search.as_langchain_tool()
    assert await tool.ainvoke({"query": "storage"}) == "one"
    with pytest.raises(RuntimeError, match="offline"):
        await tool.ainvoke({"query": "storage retry"})
    assert [call["query"] for call in search.calls] == ["storage", "storage retry"]
    assert fetch.name == "web_fetch"
