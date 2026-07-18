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
from tests.scenarios.live import (
    LiveAttempt,
    LiveAttemptReport,
    LiveOutcome,
    LivePreflightError,
    LiveScenario,
    LiveScenarioFailure,
    LiveScenarioReport,
    LiveScenarioRunner,
    ReportClassification,
    ScenarioAssertionError,
    classify_live_report,
    preflight_live_environment,
    scan_live_report_archive,
    write_live_report,
)


def _live_scenario() -> LiveScenario:
    return LiveScenario(
        scenario_id="quick-factual",
        requirement_ids=("EVH-001",),
        entrypoint="wave0-worker",
        preconditions={"max_attempts": 2},
        live_requirements=("model", "web_search"),
        expected=LiveOutcome(route="pass"),
        hard_invariants=("authority", "containment", "typed outcome"),
        metrics=("citation-binding-rate",),
    )


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
        "live-one-topic-wave1",
        "live-wave2-synthesis",
        "live-one-gap-targeted-evidence",
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
    wave1 = next(scenario for scenario in LIVE_CANARIES if scenario.scenario_id == "live-one-topic-wave1")
    assert wave1.entrypoint == "wave1.NODE_SPEC"
    assert wave1.preconditions["seed_authority"] == "validated-wave0-ledger"
    assert wave1.preconditions["capability_builder"] == "_build_wave1_capabilities"
    assert wave1.preconditions["gate_contract"] == "preview-validate-evaluate"
    assert wave1.preconditions["coverage_exclusions"] == (
        "public-entry",
        "predecessor-lifecycle",
        "production-recipe",
        "full-pipeline",
    )
    assert wave1.preconditions["max_attempts"] == 1
    assert wave1.preconditions["max_model_calls"] == 4
    assert wave1.preconditions["max_tool_calls"] == 3
    wave2 = next(scenario for scenario in LIVE_CANARIES if scenario.scenario_id == "live-wave2-synthesis")
    assert wave2.entrypoint == "wave2_synthesis.NODE_SPEC"
    assert wave2.preconditions["seed_authority"] == "validated-wave0-wave1-ledger"
    assert wave2.preconditions["capability_builder"] == "_build_hitl1_capabilities"
    assert wave2.preconditions["gate_contract"] == "node-then-evaluate"
    assert wave2.preconditions["coverage_exclusions"] == (
        "public-entry",
        "predecessor-lifecycle",
        "production-recipe",
        "full-pipeline",
    )
    assert wave2.preconditions["max_attempts"] == 1
    assert wave2.preconditions["max_model_calls"] == 2
    assert wave2.preconditions["max_tool_calls"] == 0
    targeted = next(scenario for scenario in LIVE_CANARIES if scenario.scenario_id == "live-one-gap-targeted-evidence")
    assert targeted.entrypoint == "targeted_evidence.NODE_SPEC"
    assert targeted.preconditions["seed_authority"] == "validated-synthesis-gap"
    assert targeted.preconditions["capability_builder"] == "_build_wave0_capabilities"
    assert targeted.preconditions["gate_contract"] == "none-submit-only"
    assert targeted.preconditions["coverage_exclusions"] == (
        "public-entry",
        "predecessor-lifecycle",
        "production-recipe",
        "full-pipeline",
    )
    assert targeted.preconditions["max_attempts"] == 1
    assert targeted.preconditions["max_model_calls"] == 4
    assert targeted.preconditions["max_tool_calls"] == 3


def test_six_case_live_deadline_budget_preserves_job_margin() -> None:
    from tests.scenarios.canaries import validate_live_canary_deadlines

    summary = validate_live_canary_deadlines(LIVE_CANARIES, job_timeout_seconds=1200)

    assert summary == {
        "case_count": 6,
        "declared_seconds": 900,
        "job_timeout_seconds": 1200,
        "margin_seconds": 300,
    }


@pytest.mark.parametrize(
    ("case_id", "timeout_seconds", "error"),
    [
        ("live-one-topic-wave0", 241, "live_web_deadline_invalid"),
        ("live-wave2-synthesis", 121, "live_zero_tool_deadline_invalid"),
    ],
)
def test_live_deadline_budget_rejects_per_case_violation(case_id, timeout_seconds, error) -> None:
    from dataclasses import replace

    from tests.scenarios.canaries import validate_live_canary_deadlines

    scenarios = tuple(
        replace(
            scenario,
            preconditions={**scenario.preconditions, "timeout_seconds": timeout_seconds},
        )
        if scenario.scenario_id == case_id
        else scenario
        for scenario in LIVE_CANARIES
    )
    with pytest.raises(ValueError, match=error):
        validate_live_canary_deadlines(scenarios, job_timeout_seconds=1200)


def test_live_deadline_budget_rejects_aggregate_violation() -> None:
    from dataclasses import replace

    from tests.scenarios.canaries import validate_live_canary_deadlines

    scenarios = tuple(
        replace(scenario, preconditions={**scenario.preconditions, "timeout_seconds": 240})
        if scenario.preconditions["require_web"]
        else scenario
        for scenario in LIVE_CANARIES
    )
    with pytest.raises(ValueError, match="live_aggregate_deadline_invalid"):
        validate_live_canary_deadlines(scenarios, job_timeout_seconds=1200)


@pytest.mark.parametrize("scenario", LIVE_CANARIES, ids=lambda scenario: scenario.scenario_id)
def test_live_bridge_policy_uses_each_scenario_declared_bounds(scenario, tmp_path) -> None:
    from deerflow_deep_research.runtime.projection import project_research_scope
    from deerflow_deep_research.runtime.research import (
        _build_hitl1_capabilities,
        _build_wave0_capabilities,
        _build_wave1_capabilities,
    )
    from tests.fixtures.runtime import local_runtime_envelope, unique_run_identity
    from tests.scenarios import canaries

    identity = unique_run_identity()
    envelope = local_runtime_envelope(tmp_path, identity=identity)
    graph = project_research_scope(envelope, research_scope_id=identity.research_id)
    tracker = canaries._UsageTracker(model_id="test/model")
    factory = canaries._BridgeFactory(
        focused_node=str(scenario.preconditions["focused_node"]),
        tracker=tracker,
        web=None,
        scenario=scenario,
    )
    focused_node = str(scenario.preconditions["focused_node"])
    if focused_node in {"wave0", "targeted_evidence"}:
        capabilities = _build_wave0_capabilities(envelope, graph, factory)
    elif focused_node == "wave1":
        capabilities = _build_wave1_capabilities(envelope, graph, factory)
    else:
        capabilities = _build_hitl1_capabilities(envelope, graph, factory)

    budget = capabilities._real.policy.budget
    assert budget.max_model_calls == scenario.preconditions["max_model_calls"]
    assert budget.max_total_tool_calls == max(scenario.preconditions["max_tool_calls"], 1)
    assert budget.total_token_budget == scenario.preconditions["max_total_tokens"]
    assert budget.wall_time_seconds == scenario.preconditions["timeout_seconds"]


def test_release_bridge_factory_keeps_protected_default_bounds(tmp_path) -> None:
    from deerflow_deep_research.runtime.projection import project_research_scope
    from deerflow_deep_research.runtime.research import _build_wave0_capabilities
    from tests.fixtures.runtime import local_runtime_envelope, unique_run_identity
    from tests.scenarios import canaries

    identity = unique_run_identity()
    envelope = local_runtime_envelope(tmp_path, identity=identity)
    graph = project_research_scope(envelope, research_scope_id=identity.research_id)
    factory = canaries._BridgeFactory(
        focused_node=None,
        tracker=canaries._UsageTracker(model_id="test/release"),
        web=None,
    )

    capabilities = _build_wave0_capabilities(envelope, graph, factory)

    assert capabilities._real.policy.budget.max_model_calls == 4
    assert capabilities._real.policy.budget.max_total_tool_calls == 3
    assert capabilities._real.policy.budget.total_token_budget == 32_768
    assert capabilities._real.policy.budget.wall_time_seconds == 180.0


async def test_focused_wave1_setup_uses_real_node_builder_and_gate_contract(monkeypatch, tmp_path) -> None:
    from deerflow_deep_research.domain.context import NodeExecutionResult
    from deerflow_deep_research.domain.enums import NodeFinishReason
    from tests.fixtures.runtime import local_runtime_envelope, unique_run_identity
    from tests.scenarios import canaries

    class ScriptedWave1Capabilities:
        async def run_agent(self, *, context, request):
            assert context.node_name == "wave1"
            assert request.minimum_tool_calls == 1
            return NodeExecutionResult(
                finish_reason=NodeFinishReason.SUCCESS,
                summary=json.dumps(
                    {
                        "schema_version": 1,
                        "sources": [
                            {
                                "source_id": "source:focused",
                                "canonical_url": "https://example.invalid/focused-wave1",
                                "title": "Focused synthetic source",
                            }
                        ],
                        "claims": [
                            {
                                "claim_id": "claim:focused_wave1",
                                "statement": "Focused synthetic evidence supports the claim.",
                                "support_refs": ["source:focused"],
                                "counter_refs": [],
                            }
                        ],
                        "open_questions": [],
                    }
                ),
            )

    policies = []

    def bridge_factory(*, envelope, policy):
        assert envelope.outer_run_id
        policies.append(policy)
        return ScriptedWave1Capabilities()

    events = []
    real_preview = canaries.preview_work_unit_update
    real_validate = canaries.validate_wrapper_gate_view
    real_evaluate = canaries.evaluate_gate_for_node

    def recording_preview(current, incoming):
        events.append(("preview", frozenset(incoming)))
        return real_preview(current, incoming)

    def recording_validate(view, state, *, phase):
        events.append(("validate", phase))
        return real_validate(view, state, phase=phase)

    def recording_evaluate(state, logical_name, gate_def):
        events.append(("evaluate", logical_name))
        return real_evaluate(state, logical_name, gate_def)

    monkeypatch.setattr(canaries, "preview_work_unit_update", recording_preview)
    monkeypatch.setattr(canaries, "validate_wrapper_gate_view", recording_validate)
    monkeypatch.setattr(canaries, "evaluate_gate_for_node", recording_evaluate)
    identity = unique_run_identity()
    envelope = local_runtime_envelope(tmp_path, identity=identity)

    execution = await canaries._execute_focused_wave1_core(
        envelope=envelope,
        research_id=identity.research_id,
        bridge_factory=bridge_factory,
    )

    assert len(policies) == 1
    assert policies[0].policy_name == "wave1-evidence-extraction"
    assert {"web_search", "web_fetch"} <= policies[0].allowed_tool_names
    assert events == [
        ("preview", canaries.WORK_UNIT_GATE_PREVIEW_FIELDS),
        ("validate", "wave1"),
        ("evaluate", "wave1"),
    ]
    assert execution.gate_route == "pass"
    assert execution.record_phases == ("wave0", "wave1")
    assert execution.outcome.route == "one-topic-wave1"
    assert len(execution.outcome.artifacts) == 1
    assert execution.outcome.values["identity"] == {
        "thread_id": identity.thread_id,
        "run_id": identity.run_id,
        "research_id": identity.research_id,
    }


async def test_focused_wave2_setup_binds_seeded_evidence_before_real_gate(monkeypatch, tmp_path) -> None:
    from deerflow_deep_research.domain.context import NodeExecutionResult
    from deerflow_deep_research.domain.enums import NodeFinishReason
    from tests.fixtures.runtime import local_runtime_envelope, unique_run_identity
    from tests.scenarios import canaries

    class ScriptedSynthesisCapabilities:
        async def run_agent(self, *, context, request):
            assert context.node_name == "wave2_synthesis"
            assert request.minimum_tool_calls == 0
            return NodeExecutionResult(
                finish_reason=NodeFinishReason.SUCCESS,
                summary=json.dumps(
                    {
                        "schema_version": 1,
                        "findings": [
                            {
                                "finding_id": "finding:focused_wave2",
                                "statement": "Synthetic Wave1 evidence supports the finding.",
                                "priority": 1,
                                "affected_topics": ["storage"],
                                "backing_refs": ["source:wave1"],
                                "confidence": "high",
                                "search_required": False,
                            }
                        ],
                        "relations": [],
                        "gaps": [],
                        "summary": "One supported focused finding.",
                    }
                ),
            )

    policies = []

    def bridge_factory(*, envelope, policy, tools_resolver):
        assert tools_resolver(envelope, policy) == ()
        policies.append(policy)
        return ScriptedSynthesisCapabilities()

    events = []
    real_evaluate = canaries.evaluate_gate_for_node

    def recording_evaluate(state, logical_name, gate_def):
        events.append((logical_name, tuple(state["execution_trace"])))
        return real_evaluate(state, logical_name, gate_def)

    monkeypatch.setattr(canaries, "evaluate_gate_for_node", recording_evaluate)
    identity = unique_run_identity()
    envelope = local_runtime_envelope(tmp_path, identity=identity)

    execution = await canaries._execute_focused_wave2_core(
        envelope=envelope,
        research_id=identity.research_id,
        bridge_factory=bridge_factory,
    )

    assert len(policies) == 1
    assert policies[0].policy_name == "hitl1-structured-brief"
    assert policies[0].allowed_tool_names == frozenset()
    assert events == [("wave2_synthesis", ("wave2_synthesis",))]
    assert execution.gate_route == "pass"
    assert execution.record_phases == ("wave0", "wave1")
    assert execution.backing_refs == execution.accepted_refs[-1:]
    assert execution.outcome.route == "wave2-synthesis"
    assert tuple(execution.outcome.values["synthesis_findings"][0]["backing_refs"]) == execution.accepted_refs[-1:]


async def test_focused_targeted_setup_publishes_one_gap_without_phase_gate(monkeypatch, tmp_path) -> None:
    from deerflow_deep_research.domain.context import NodeExecutionResult
    from deerflow_deep_research.domain.enums import NodeFinishReason
    from tests.fixtures.runtime import local_runtime_envelope, unique_run_identity
    from tests.scenarios import canaries

    class ScriptedTargetedCapabilities:
        async def run_agent(self, *, context, request):
            assert context.node_name == "targeted_evidence"
            assert "gap:focused-targeted" in request.objective
            return NodeExecutionResult(
                finish_reason=NodeFinishReason.SUCCESS,
                summary=json.dumps(
                    {
                        "schema_version": 1,
                        "gap_id": "gap:focused-targeted",
                        "gap_status": "resolved",
                        "sources": [
                            {
                                "source_id": "source:targeted",
                                "canonical_url": "https://example.invalid/focused-targeted",
                                "title": "Focused targeted source",
                            }
                        ],
                        "limitations": "",
                    }
                ),
            )

    policies = []

    def bridge_factory(*, envelope, policy):
        policies.append(policy)
        return ScriptedTargetedCapabilities()

    gate_calls = []
    real_evaluate = canaries.evaluate_gate_for_node

    def recording_evaluate(state, logical_name, gate_def):
        gate_calls.append(logical_name)
        return real_evaluate(state, logical_name, gate_def)

    monkeypatch.setattr(canaries, "evaluate_gate_for_node", recording_evaluate)
    identity = unique_run_identity()
    envelope = local_runtime_envelope(tmp_path, identity=identity)

    execution = await canaries._execute_focused_targeted_core(
        envelope=envelope,
        research_id=identity.research_id,
        bridge_factory=bridge_factory,
    )

    assert len(policies) == 1
    assert gate_calls == ["wave2_synthesis"]
    assert policies[0].policy_name == "wave0-source-intake"
    assert {"web_search", "web_fetch"} <= policies[0].allowed_tool_names
    assert execution.record_phases == ("wave0", "wave1", "targeted_evidence")
    assert execution.targeted_record_count == 1
    assert execution.outcome.route == "targeted-evidence"
    assert execution.outcome.values["synthesis_gaps"] == (
        {
            "gap_id": "gap:focused-targeted",
            "description": "Focused targeted evidence gap.",
            "priority": 1,
            "affected_topics": ("storage",),
            "search_required": True,
        },
    )


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
                outcome=LiveOutcome(route="pass", values={"accepted_submission_refs": ("ref:one",)}),
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

    scenario = _live_scenario()
    report = await LiveScenarioRunner(executor=execute, max_attempts=2).run(scenario)
    serialized = json.dumps(report.to_dict(), sort_keys=True)

    assert report.scenario_id == "quick-factual"
    assert report.attempt_count == 2
    assert report.retry_count == 1
    assert report.workflow_attempt_count == 3
    assert report.workflow_retry_count == 1
    assert report.hard_invariants == {"authority": True, "containment": True, "typed outcome": True}
    assert report.report_schema_version == 1
    assert report.metrics_schema == "evidence-v1"
    assert report.quality_metrics == {
        "citation-binding-rate": {
            "authoritative_denominator": None,
            "evidence_basis": ["accepted-ledger-records:missing", "final-citation-map:missing"],
            "metric_id": "citation-binding-rate",
            "status": "insufficient_authority",
            "value": None,
            "value_kind": "ratio",
        }
    }
    assert report.model_ids == ("openai/gpt-live",)
    assert report.tool_ids == ("tavily/web_search",)
    assert report.input_tokens == 220
    assert report.output_tokens == 40
    assert report.cost_usd == pytest.approx(0.004)
    assert report.tool_calls == 3
    assert report.wall_time_seconds == pytest.approx(3.75)
    assert report.diagnostics == {
        "identity": {
            "thread_id_present": False,
            "run_id_present": False,
            "research_id_present": False,
            "pairwise_distinct": False,
        },
        "invariants": {"declared": 3, "passed": 3},
        "metrics": {"selected": 1, "measured": 0, "unavailable": 1},
        "attempts": {"outer": 2, "retries": 1, "workflow": 3, "workflow_retries": 1},
        "resources": {
            "models": 1,
            "tools": 1,
            "tokens_available": True,
            "cost_available": True,
        },
    }
    assert "sk-secret" not in serialized
    assert "/Users/operator" not in serialized


async def test_live_runner_fails_hard_invariants_with_scenario_identity() -> None:
    async def execute(_scenario):
        return LiveAttempt(
            outcome=LiveOutcome(route="unauthorized"),
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

    scenario = _live_scenario()
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

    scenario = _live_scenario()
    with pytest.raises(LiveScenarioFailure, match="attempts exhausted") as caught:
        await LiveScenarioRunner(executor=execute, max_attempts=1).run(scenario)

    assert caught.value.report.hard_invariants["authority"] is False
    assert caught.value.report.workflow_retry_count == 2
    assert "sk-secret" not in json.dumps(caught.value.report.to_dict())


def test_live_report_writer_emits_stable_redacted_json(tmp_path) -> None:
    report = LiveScenarioReport(
        report_schema_version=1,
        metrics_schema="evidence-v1",
        scenario_id="live-start-to-hitl1",
        attempt_count=1,
        retry_count=0,
        workflow_attempt_count=1,
        workflow_retry_count=0,
        hard_invariants={"identity_isolated": True},
        quality_metrics={
            "citation-binding-rate": {
                "authoritative_denominator": None,
                "evidence_basis": ["final-citation-map:missing"],
                "metric_id": "citation-binding-rate",
                "status": "insufficient_authority",
                "value": None,
                "value_kind": "ratio",
            }
        },
        model_ids=("openai/gpt-live",),
        tool_ids=(),
        input_tokens=100,
        output_tokens=25,
        cost_usd=None,
        tool_calls=0,
        wall_time_seconds=1.0,
        attempts=(),
        diagnostics={
            "identity": {
                "thread_id_present": True,
                "run_id_present": True,
                "research_id_present": True,
                "pairwise_distinct": True,
            },
            "invariants": {"declared": 1, "passed": 1},
            "metrics": {"selected": 1, "measured": 0, "unavailable": 1},
            "attempts": {"outer": 1, "retries": 0, "workflow": 1, "workflow_retries": 0},
            "resources": {"models": 1, "tools": 0, "tokens_available": True, "cost_available": False},
        },
    )

    path = write_live_report(report, tmp_path)

    assert path == tmp_path / "live-start-to-hitl1.json"
    assert json.loads(path.read_text(encoding="utf-8"))["scenario_id"] == "live-start-to-hitl1"


def test_live_report_classifier_distinguishes_evidence_v1_and_legacy_reports() -> None:
    current = {
        "report_schema_version": 1,
        "metrics_schema": "evidence-v1",
        "scenario_id": "live-start-to-hitl1",
        "quality_metrics": {},
    }
    legacy = {
        "scenario_id": "live-start-to-hitl1",
        "quality_metrics": {"citation_precision": 1.0},
    }
    assert classify_live_report(current) is ReportClassification.EVIDENCE_V1
    assert classify_live_report(legacy) is ReportClassification.LEGACY


def test_live_report_rejects_untyped_metric_payload() -> None:
    values = {
        "report_schema_version": 1,
        "metrics_schema": "evidence-v1",
        "scenario_id": "live-start-to-hitl1",
        "attempt_count": 1,
        "retry_count": 0,
        "workflow_attempt_count": 1,
        "workflow_retry_count": 0,
        "hard_invariants": {"identity_isolated": True},
        "quality_metrics": {"citation-binding-rate": {"value": 1.0}},
        "model_ids": ("openai/gpt-live",),
        "tool_ids": (),
        "input_tokens": 100,
        "output_tokens": 25,
        "cost_usd": None,
        "tool_calls": 0,
        "wall_time_seconds": 1.0,
        "attempts": (),
        "diagnostics": {},
    }
    with pytest.raises(ValueError, match="live_report_metrics_invalid"):
        LiveScenarioReport(**values)


@pytest.mark.parametrize(
    "mutation",
    [
        {"diagnostics": {}},
        {"attempts": (LiveAttemptReport(1, False, "provider_error", "https://private.example/source"),)},
        {"attempts": (LiveAttemptReport(1, False, "provider_error", "x" * 4097),)},
        {
            "diagnostics": {
                "identity": {
                    "thread_id_present": False,
                    "run_id_present": False,
                    "research_id_present": False,
                    "pairwise_distinct": False,
                },
                "invariants": {"declared": 99, "passed": 0},
                "metrics": {"selected": 0, "measured": 0, "unavailable": 0},
                "attempts": {"outer": 1, "retries": 0, "workflow": 1, "workflow_retries": 0},
                "resources": {"models": 1, "tools": 0, "tokens_available": False, "cost_available": False},
            }
        },
    ],
)
def test_live_report_rejects_malformed_or_sensitive_diagnostics(mutation) -> None:
    values = {
        "report_schema_version": 1,
        "metrics_schema": "evidence-v1",
        "scenario_id": "live-start-to-hitl1",
        "attempt_count": 1,
        "retry_count": 0,
        "workflow_attempt_count": 1,
        "workflow_retry_count": 0,
        "hard_invariants": {"identity_isolated": False},
        "quality_metrics": {},
        "model_ids": ("openai/gpt-live",),
        "tool_ids": (),
        "input_tokens": None,
        "output_tokens": None,
        "cost_usd": None,
        "tool_calls": 0,
        "wall_time_seconds": 1.0,
        "attempts": (LiveAttemptReport(1, False, "provider_error", "bounded structural failure"),),
        "diagnostics": {
            "identity": {
                "thread_id_present": False,
                "run_id_present": False,
                "research_id_present": False,
                "pairwise_distinct": False,
            },
            "invariants": {"declared": 1, "passed": 0},
            "metrics": {"selected": 0, "measured": 0, "unavailable": 0},
            "attempts": {"outer": 1, "retries": 0, "workflow": 1, "workflow_retries": 0},
            "resources": {"models": 1, "tools": 0, "tokens_available": False, "cost_available": False},
        },
    }
    values.update(mutation)
    with pytest.raises(ValueError, match="live_report_diagnostics_invalid"):
        LiveScenarioReport(**values)


@pytest.mark.parametrize(
    "payload",
    [
        {"report_schema_version": 2, "metrics_schema": "evidence-v1", "scenario_id": "live-a"},
        {"report_schema_version": 1, "metrics_schema": "unknown", "scenario_id": "live-a"},
        {"report_schema_version": 1, "scenario_id": "live-a"},
    ],
)
def test_live_report_classifier_rejects_partial_or_unknown_versioned_reports(payload) -> None:
    with pytest.raises(ValueError, match="live_report_schema_invalid"):
        classify_live_report(payload)


def test_live_report_archive_scan_requires_nonempty_schema_valid_reports(tmp_path) -> None:
    report = LiveScenarioReport(
        report_schema_version=1,
        metrics_schema="evidence-v1",
        scenario_id="live-start-to-hitl1",
        attempt_count=1,
        retry_count=0,
        workflow_attempt_count=1,
        workflow_retry_count=0,
        hard_invariants={"identity_isolated": True},
        quality_metrics={},
        model_ids=("openai/gpt-live",),
        tool_ids=(),
        input_tokens=100,
        output_tokens=25,
        cost_usd=None,
        tool_calls=0,
        wall_time_seconds=1.0,
        attempts=(LiveAttemptReport(1, True, None, "bounded structural success"),),
        diagnostics={
            "identity": {
                "thread_id_present": True,
                "run_id_present": True,
                "research_id_present": True,
                "pairwise_distinct": True,
            },
            "invariants": {"declared": 1, "passed": 1},
            "metrics": {"selected": 0, "measured": 0, "unavailable": 0},
            "attempts": {"outer": 1, "retries": 0, "workflow": 1, "workflow_retries": 0},
            "resources": {"models": 1, "tools": 0, "tokens_available": True, "cost_available": False},
        },
    )
    write_live_report(report, tmp_path)

    assert scan_live_report_archive(tmp_path) == ("live-start-to-hitl1",)


def test_live_report_archive_scan_rejects_empty_and_known_sensitive_fixture(tmp_path) -> None:
    with pytest.raises(ValueError, match="live_report_archive_empty"):
        scan_live_report_archive(tmp_path)

    (tmp_path / "known-sensitive.json").write_text(
        json.dumps({"diagnostics": "source=https://private.example/finding"}),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="live_report_archive_sensitive"):
        scan_live_report_archive(tmp_path)


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
