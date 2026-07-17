"""Live/release evaluation control-plane contracts.

@impl EVH-002
@impl EVH-005
@impl EVH-007
@impl EVH-009
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from types import SimpleNamespace

import pytest
from langchain_core.messages import AIMessage

from tests.scenarios.canaries import _BRIEF, _PLAN, _PROFILE, LIVE_CANARIES, _app_config, _UsageTracker
from tests.scenarios.catalog import SCENARIOS
from tests.scenarios.live import (
    LiveAttempt,
    LivePreflightError,
    LiveScenarioFailure,
    LiveScenarioReport,
    LiveScenarioRunner,
    preflight_live_environment,
    write_live_report,
)
from tests.scenarios.model import ScenarioAssertionError, ScenarioOutcome


def test_explicit_live_preflight_fails_without_model_credentials() -> None:
    with pytest.raises(LivePreflightError, match="live_model_credentials_missing") as caught:
        preflight_live_environment(environ={}, require_web=False)

    assert caught.value.code == "live_model_credentials_missing"


def test_wave0_live_preflight_fails_without_web_credentials() -> None:
    with pytest.raises(LivePreflightError, match="live_web_credentials_missing") as caught:
        preflight_live_environment(environ={"ANTHROPIC_API_KEY": "model-secret"}, require_web=True)

    assert caught.value.code == "live_web_credentials_missing"


def test_live_preflight_reports_provider_identity_without_secret_values() -> None:
    environment = preflight_live_environment(
        environ={"OPENAI_API_KEY": "model-secret", "TAVILY_API_KEY": "web-secret"},
        require_web=True,
    )

    assert environment.model_provider == "openai"
    assert environment.web_provider == "tavily"
    assert "secret" not in repr(environment)


def test_live_canaries_declare_unique_identity_and_bounded_execution() -> None:
    assert [scenario.scenario_id for scenario in LIVE_CANARIES] == [
        "live-start-to-hitl1",
        "live-hitl1-to-topic-planning",
        "live-one-topic-wave0",
    ]
    for scenario in LIVE_CANARIES:
        assert scenario.preconditions["identity"] == "unique-per-invocation"
        assert 0 < scenario.preconditions["timeout_seconds"] <= 300
        assert scenario.preconditions["max_attempts"] == 1
        assert scenario.preconditions["max_total_tokens"] == 32_768
        assert scenario.preconditions["max_model_calls"] <= 4
        assert scenario.preconditions["max_tool_calls"] <= 3
    wave0 = next(scenario for scenario in LIVE_CANARIES if scenario.scenario_id == "live-one-topic-wave0")
    assert wave0.preconditions["max_model_calls"] == 4
    assert wave0.preconditions["max_tool_calls"] == 3


def test_live_model_config_constructs_with_one_retry_authority() -> None:
    from deerflow.models.factory import create_chat_model

    model = create_chat_model(
        app_config=_app_config("deepseek", "placeholder-key"),
        attach_tracing=False,
    )

    assert model.max_retries == 0


def test_live_canary_setup_payloads_satisfy_real_node_parsers() -> None:
    from deerflow_deep_research.domain.profile import parse_profile_response
    from deerflow_deep_research.graph.nodes.hitl1.prompts import parse_brief_output
    from deerflow_deep_research.graph.nodes.topic_planning.prompts import parse_plan_output

    assert parse_brief_output(_BRIEF).time_budget.value == "very_quick"
    assert parse_profile_response(_PROFILE).time_budget.value == "very_quick"
    assert len(parse_plan_output(_PLAN).topics) == 1


def test_live_usage_tracker_reports_response_shape_without_raw_content() -> None:
    tracker = _UsageTracker(model_id="deepseek/test")
    message = AIMessage(
        content='{"schema_version":1,"sources":[{"title":"private provider text"}]}',
        tool_calls=[{"name": "web_search", "args": {"query": "storage"}, "id": "call-1"}],
        usage_metadata={"input_tokens": 10, "output_tokens": 5, "total_tokens": 15},
    )
    tracker.on_llm_end(SimpleNamespace(generations=[[SimpleNamespace(message=message)]]))

    summary = tracker.diagnostic_summary()
    shape = json.loads(summary)[0]
    assert shape["content_chars"] == len(message.content)
    assert shape["content_kind"] == "json_object"
    assert shape["json_keys"] == ["schema_version", "sources"]
    assert shape["tool_names"] == ["web_search"]
    assert shape["source_count"] == 1
    assert shape["source_item_keys"] == ["title"]
    assert shape["source_field_types"] == {"title": "str"}
    assert shape["wave0_schema_valid"] is False
    assert "sources.0.canonical_url:missing" in shape["wave0_validation_errors"]
    assert shape["wave1_schema_valid"] is False
    assert "sources.0.canonical_url:missing" in shape["wave1_validation_errors"]
    assert "private provider text" not in summary


def test_live_usage_tracker_identifies_one_embedded_json_object_without_preserving_prose() -> None:
    tracker = _UsageTracker(model_id="deepseek/test")
    message = AIMessage(
        content='Analysis complete. Final answer: {"schema_version":1,"sources":[]}',
        usage_metadata={"input_tokens": 10, "output_tokens": 5, "total_tokens": 15},
    )
    tracker.on_llm_end(SimpleNamespace(generations=[[SimpleNamespace(message=message)]]))

    shape = json.loads(tracker.diagnostic_summary())[0]
    assert shape["content_kind"] == "embedded_json_object"
    assert shape["json_keys"] == ["schema_version", "sources"]
    assert "Analysis complete" not in tracker.diagnostic_summary()


def test_live_usage_tracker_reports_synthesis_schema_errors_without_values() -> None:
    tracker = _UsageTracker(model_id="deepseek/test")
    message = AIMessage(
        content=json.dumps(
            {
                "schema_version": 1,
                "findings": [{"finding_id": "private invalid id"}],
                "relations": [],
                "gaps": [],
                "summary": "private synthesis text",
            }
        )
    )
    tracker.on_llm_end(SimpleNamespace(generations=[[SimpleNamespace(message=message)]]))

    shape = json.loads(tracker.diagnostic_summary())[0]
    assert shape["synthesis_schema_valid"] is False
    assert "findings.0.finding_id:string_pattern_mismatch" in shape["synthesis_validation_errors"]
    assert "private invalid id" not in tracker.diagnostic_summary()
    assert "private synthesis text" not in tracker.diagnostic_summary()


async def test_live_runner_reports_attempts_metrics_cost_and_redacts_diagnostics() -> None:
    attempts = iter(
        (
            LiveAttempt(
                outcome=None,
                error_code="provider_timeout",
                model_id="openai/gpt-live",
                tool_ids=("tavily/web_search",),
                input_tokens=100,
                output_tokens=0,
                cost_usd=0.001,
                tool_calls=1,
                wall_time_seconds=1.25,
                diagnostics="token=sk-secret path=/Users/operator/private/run.json",
                workflow_attempts=1,
                workflow_retries=0,
            ),
            LiveAttempt(
                outcome=ScenarioOutcome(route="pass", values={"accepted_submission_refs": ("ref:one",)}),
                error_code=None,
                model_id="openai/gpt-live",
                tool_ids=("tavily/web_search",),
                input_tokens=120,
                output_tokens=40,
                cost_usd=0.003,
                tool_calls=2,
                wall_time_seconds=2.5,
                diagnostics="completed",
                workflow_attempts=2,
                workflow_retries=1,
            ),
        )
    )

    async def execute(_scenario):
        return next(attempts)

    scenario = next(item for item in SCENARIOS if item.scenario_id == "quick-factual")
    report = await LiveScenarioRunner(executor=execute, max_attempts=2).run(scenario)
    serialized = json.dumps(report.to_dict(), sort_keys=True)

    assert report.scenario_id == "quick-factual"
    assert report.attempt_count == 2
    assert report.retry_count == 1
    assert report.workflow_attempt_count == 3
    assert report.workflow_retry_count == 1
    assert report.hard_invariants == {"authority": True, "containment": True, "typed outcome": True}
    assert report.quality_metrics["citation_precision"] == 1.0
    assert report.model_ids == ("openai/gpt-live",)
    assert report.tool_ids == ("tavily/web_search",)
    assert report.input_tokens == 220
    assert report.output_tokens == 40
    assert report.cost_usd == pytest.approx(0.004)
    assert report.tool_calls == 3
    assert report.wall_time_seconds == pytest.approx(3.75)
    assert "sk-secret" not in serialized
    assert "/Users/operator" not in serialized


async def test_live_runner_fails_hard_invariants_with_scenario_identity() -> None:
    async def execute(_scenario):
        return LiveAttempt(
            outcome=ScenarioOutcome(route="unauthorized"),
            error_code=None,
            model_id="openai/gpt-live",
            tool_ids=(),
            input_tokens=None,
            output_tokens=None,
            cost_usd=None,
            tool_calls=0,
            wall_time_seconds=0.5,
            diagnostics="completed",
        )

    scenario = next(item for item in SCENARIOS if item.scenario_id == "quick-factual")
    with pytest.raises(
        ScenarioAssertionError,
        match="scenario=quick-factual lane=live authenticity=live_real_dependencies: invariant failed",
    ):
        await LiveScenarioRunner(executor=execute, max_attempts=1).run(scenario)


async def test_live_runner_exhaustion_carries_a_redacted_failure_report() -> None:
    async def execute(_scenario):
        return LiveAttempt(
            outcome=None,
            error_code="provider_timeout",
            model_id="deepseek/live",
            tool_ids=("tavily/web_search",),
            input_tokens=100,
            output_tokens=5,
            cost_usd=None,
            tool_calls=1,
            wall_time_seconds=2.0,
            diagnostics="token=sk-secret path=/Users/operator/run.json",
            workflow_attempts=3,
            workflow_retries=2,
        )

    scenario = next(item for item in SCENARIOS if item.scenario_id == "quick-factual")
    with pytest.raises(LiveScenarioFailure, match="attempts exhausted") as caught:
        await LiveScenarioRunner(executor=execute, max_attempts=1).run(scenario)

    assert caught.value.report.hard_invariants["authority"] is False
    assert caught.value.report.workflow_retry_count == 2
    assert "sk-secret" not in json.dumps(caught.value.report.to_dict())


def test_live_report_writer_emits_stable_redacted_json(tmp_path) -> None:
    report = LiveScenarioReport(
        scenario_id="live-start-to-hitl1",
        attempt_count=1,
        retry_count=0,
        workflow_attempt_count=1,
        workflow_retry_count=0,
        hard_invariants={"identity_isolated": True},
        quality_metrics={"citation_precision": 1.0},
        model_ids=("openai/gpt-live",),
        tool_ids=(),
        input_tokens=100,
        output_tokens=25,
        cost_usd=None,
        tool_calls=0,
        wall_time_seconds=1.0,
        attempts=(),
    )

    path = write_live_report(report, tmp_path)

    assert path == tmp_path / "live-start-to-hitl1.json"
    assert json.loads(path.read_text(encoding="utf-8"))["scenario_id"] == "live-start-to-hitl1"


def test_live_preflight_cli_fails_without_environment_or_dotenv() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/live_preflight.py", "--require-web"],
        capture_output=True,
        check=False,
        env={"PATH": os.environ.get("PATH", ""), "LIVE_DISABLE_DOTENV": "1"},
        text=True,
    )

    assert result.returncode == 1
    assert "live_model_credentials_missing" in result.stderr
