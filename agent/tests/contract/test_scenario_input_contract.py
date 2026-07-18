"""Bounded typed deterministic scenario input contracts.

@impl EVH-001
@impl EVH-007
"""

from __future__ import annotations

from collections import deque

import pytest

from tests.fixtures.fake_models import ScriptedChatModel
from tests.fixtures.scripted_tools import ScriptedTool
from tests.scenarios.contracts import ScenarioBounds
from tests.scenarios.inputs import (
    FaultPoint,
    LifecycleAction,
    LifecycleActionKind,
    ModelTurn,
    ObservedToolCall,
    ScenarioInputs,
    ScriptExecutionObservation,
    ScriptInputError,
    ToolOutcome,
    ToolStep,
    validate_script_observation,
)


def _inputs(**overrides: object) -> ScenarioInputs:
    values: dict[str, object] = {
        "model_turns": (
            ModelTurn(
                content="Inspect one bounded source.",
                tool_names=("web_search",),
                input_tokens=10,
                output_tokens=5,
            ),
            ModelTurn(content='{"schema_version":1}', input_tokens=8, output_tokens=4),
        ),
        "tool_steps": (
            ToolStep(
                tool_name="web_search",
                arguments=(("query", "storage economics"),),
                outcome=ToolOutcome.RESULT,
                result="bounded synthetic result",
            ),
        ),
        "lifecycle_actions": (LifecycleAction(LifecycleActionKind.START),),
        "fault_points": (FaultPoint.AFTER_STAGING_FSYNC,),
    }
    values.update(overrides)
    return ScenarioInputs(**values)


def _bounds() -> ScenarioBounds:
    return ScenarioBounds(max_attempts=1, max_model_calls=3, max_tool_calls=2, max_wall_seconds=10)


def test_typed_inputs_and_exact_observation_pass() -> None:
    inputs = _inputs()
    observation = ScriptExecutionObservation(
        model_calls=2,
        tool_calls=(ObservedToolCall("web_search", (("query", "storage economics"),)),),
        bound_tool_names=("web_search",),
    )

    validate_script_observation(inputs, _bounds(), observation)


@pytest.mark.parametrize(
    "value",
    [
        "model-response",
        ("model-response", "tool-result"),
        {"model": "response"},
    ],
)
def test_string_pseudo_scripts_are_rejected(value: object) -> None:
    with pytest.raises(ValueError, match="scenario_model_turns_invalid"):
        ScenarioInputs(model_turns=value, tool_steps=(), lifecycle_actions=(), fault_points=())


@pytest.mark.parametrize(
    ("factory", "message"),
    [
        (lambda: ModelTurn(content="x" * 16_385), "model_turn_content_oversize"),
        (lambda: ModelTurn(content="ANTHROPIC_API_KEY=sk-secret-value"), "sensitive_input_forbidden"),
        (lambda: ModelTurn(content="read /Users/alice/private/report.txt"), "raw_host_path_forbidden"),
        (
            lambda: ToolStep(
                tool_name="web_fetch",
                arguments=(("url", "https://real.example.com/private"),),
                outcome=ToolOutcome.RESULT,
                result="x",
            ),
            "external_url_forbidden",
        ),
        (
            lambda: ToolStep(
                tool_name="web_search",
                arguments=(("query", "x"),),
                outcome=ToolOutcome.RESULT,
                result="x" * 32_769,
            ),
            "tool_result_oversize",
        ),
    ],
)
def test_sensitive_or_oversize_inputs_fail_closed(factory, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        factory()


def test_tool_failure_is_typed_and_cannot_carry_result() -> None:
    failure = ToolStep(
        tool_name="web_search",
        arguments=(("query", "storage"),),
        outcome=ToolOutcome.TIMEOUT,
    )
    assert failure.outcome is ToolOutcome.TIMEOUT
    with pytest.raises(ValueError, match="tool_failure_result_forbidden"):
        ToolStep(
            tool_name="web_search",
            arguments=(("query", "storage"),),
            outcome=ToolOutcome.UNAVAILABLE,
            result="pretend result",
        )


def test_closed_lifecycle_and_fault_vocabularies_reject_aliases() -> None:
    with pytest.raises(ValueError, match="lifecycle_action_invalid"):
        LifecycleAction("resume")
    with pytest.raises(ValueError, match="scenario_fault_points_invalid"):
        ScenarioInputs(model_turns=(), tool_steps=(), lifecycle_actions=(), fault_points=("after_fsync",))


@pytest.mark.parametrize(
    ("observation", "message"),
    [
        (
            ScriptExecutionObservation(model_calls=1, tool_calls=(), bound_tool_names=("web_search",)),
            "model call order/count",
        ),
        (
            ScriptExecutionObservation(
                model_calls=2,
                tool_calls=(ObservedToolCall("web_fetch", (("url", "https://example.invalid/page"),)),),
                bound_tool_names=("web_search", "web_fetch"),
            ),
            "tool call order",
        ),
        (
            ScriptExecutionObservation(
                model_calls=2,
                tool_calls=(ObservedToolCall("web_search", (("query", "storage economics"),)),),
                bound_tool_names=("web_fetch",),
            ),
            "unbound tool",
        ),
    ],
)
def test_observation_must_match_declared_order_and_bound_tools(
    observation: ScriptExecutionObservation,
    message: str,
) -> None:
    with pytest.raises(ScriptInputError, match=message):
        validate_script_observation(_inputs(), _bounds(), observation)


def test_declared_inputs_cannot_exceed_case_bounds() -> None:
    with pytest.raises(ScriptInputError, match="model call bound"):
        validate_script_observation(
            _inputs(),
            ScenarioBounds(max_attempts=1, max_model_calls=1, max_tool_calls=2, max_wall_seconds=10),
            ScriptExecutionObservation(model_calls=2, tool_calls=(), bound_tool_names=()),
        )


def test_input_collections_have_finite_cardinality() -> None:
    with pytest.raises(ValueError, match="scenario_model_turns_invalid"):
        ScenarioInputs(
            model_turns=tuple(ModelTurn(content="x") for _ in range(65)),
            tool_steps=(),
            lifecycle_actions=(),
            fault_points=(),
        )


def test_existing_scripted_adapters_still_fail_loudly_when_exhausted() -> None:
    model = ScriptedChatModel(responses=[])
    with pytest.raises(AssertionError, match="exhausted its scripted responses"):
        model._generate([])

    tool = ScriptedTool(name="web_search", responses=deque())
    with pytest.raises(AssertionError, match="scripted tool exhausted"):
        import asyncio

        asyncio.run(tool.as_langchain_tool().ainvoke({"query": "x"}))
