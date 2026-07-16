"""Unit tests for shared demo core module.

@impl DPL-001
@impl DPL-003
"""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from deerflow_deep_research.graph.topology import LOGICAL_NODES


@pytest.fixture
def _scripts_path():
    """Ensure _demo_core is importable."""
    import sys

    scripts = str(
        __import__("pathlib").Path(__file__).resolve().parents[2] / "scripts"
    )
    if scripts not in sys.path:
        sys.path.insert(0, scripts)
    return scripts


def test_phase_meta_covers_all_logical_nodes(_scripts_path):
    from _demo_core import PHASE_META

    for name in LOGICAL_NODES:
        assert name in PHASE_META, f"Missing PHASE_META entry for {name}"
        label, desc = PHASE_META[name]
        assert isinstance(label, str) and label, f"Empty label for {name}"
        assert isinstance(desc, str) and desc, f"Empty description for {name}"


def test_build_fake_recipe(_scripts_path):
    from _demo_core import build_demo_recipe

    async def _fake_store_factory(_env, *, research_id):
        pass

    recipe = build_demo_recipe(mode="fake", work_unit_store_factory=_fake_store_factory)
    assert recipe.requires_node_agent_bridge is False
    assert recipe.requires_bootstrap_bundle is False
    assert recipe.requires_work_units is True


def test_build_real_recipe(_scripts_path):
    from _demo_core import build_demo_recipe

    async def _fake_store_factory(_env, *, research_id):
        pass

    recipe = build_demo_recipe(mode="real", work_unit_store_factory=_fake_store_factory)
    assert recipe.requires_node_agent_bridge is True
    assert recipe.requires_bootstrap_bundle is True
    assert recipe.requires_work_units is True


def test_build_demo_recipe_rejects_unknown_mode(_scripts_path):
    from _demo_core import build_demo_recipe

    async def _fake_store_factory(_env, *, research_id):
        pass

    with pytest.raises(ValueError, match="Unknown demo mode"):
        build_demo_recipe(mode="unknown", work_unit_store_factory=_fake_store_factory)


def test_create_hitl_response_text(_scripts_path):
    from _demo_core import create_hitl_response

    msg = create_hitl_response(
        value="Use broad sources",
        request_id="req-1",
        message_id="msg-1",
        response_kind="text",
    )
    payload = msg.additional_kwargs["human_input_response"]
    assert payload["value"] == "Use broad sources"
    assert payload["response_kind"] == "text"
    assert payload["request_id"] == "req-1"
    assert "option_id" not in payload


def test_create_hitl_response_option(_scripts_path):
    from _demo_core import create_hitl_response

    msg = create_hitl_response(
        value="proceed",
        request_id="req-2",
        message_id="msg-2",
        response_kind="option",
        option_id="proceed",
    )
    payload = msg.additional_kwargs["human_input_response"]
    assert payload["value"] == "proceed"
    assert payload["response_kind"] == "option"
    assert payload["option_id"] == "proceed"


def test_check_credentials_available_true(_scripts_path):
    from _demo_core import check_credentials_available

    with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-test"}):
        assert check_credentials_available() is True


def test_check_credentials_available_false(_scripts_path):
    from _demo_core import check_credentials_available

    with patch.dict(os.environ, {}, clear=True):
        # Temporarily remove ANTHROPIC_API_KEY if set
        original = os.environ.pop("ANTHROPIC_API_KEY", None)
        try:
            assert check_credentials_available() is False
        finally:
            if original is not None:
                os.environ["ANTHROPIC_API_KEY"] = original


def test_runtime_with_default_context(_scripts_path):
    from _demo_core import _runtime

    rt = _runtime([], "call-1")
    assert rt.tool_call_id == "call-1"
    assert rt.context == {}
    assert rt.state["messages"] == []


def test_runtime_with_custom_context(_scripts_path):
    from _demo_core import _runtime

    ctx = {"non_interactive_policy": {"auto_profile": True, "auto_proceed": True}}
    rt = _runtime([], "call-2", context=ctx)
    assert rt.context == ctx
    assert rt.tool_call_id == "call-2"


def test_tool_call_basic(_scripts_path):
    from langchain_core.messages import AIMessage

    from _demo_core import _tool_call

    msg = _tool_call("start", "call-start")
    assert isinstance(msg, AIMessage)
    assert len(msg.tool_calls) == 1
    assert msg.tool_calls[0]["name"] == "deep_research"
    assert msg.tool_calls[0]["args"]["action"] == "start"


def test_tool_call_with_research_id(_scripts_path):
    from _demo_core import _tool_call

    msg = _tool_call("resume", "call-resume", research_id="r_" + "A" * 43)
    assert msg.tool_calls[0]["args"]["research_id"] == "r_" + "A" * 43
    assert msg.tool_calls[0]["args"]["action"] == "resume"


def test_display_phase_progress_output(_scripts_path, capsys):
    from _demo_core import display_phase_progress

    display_phase_progress(["bootstrap"], suspended_at=None)
    captured = capsys.readouterr()
    assert "→" in captured.out
    assert "初始化" in captured.out


def test_display_phase_progress_suspended(_scripts_path, capsys):
    from _demo_core import display_phase_progress

    display_phase_progress(["bootstrap", "hitl1"], suspended_at="hitl1")
    captured = capsys.readouterr()
    assert "⏸" in captured.out
    assert "研究配置" in captured.out


def test_all_real_modes_covers_logical_nodes(_scripts_path):
    from _demo_core import ALL_REAL_MODES

    for name in LOGICAL_NODES:
        assert ALL_REAL_MODES.get(name) == "real", f"ALL_REAL_MODES missing {name}"
