"""Credentialed shortest-prefix canaries through the real public entry.

@impl EVH-005
@impl EVH-009
"""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from deerflow.config.app_config import AppConfig
from deerflow.config.model_config import ModelConfig
from deerflow.config.sandbox_config import SandboxConfig
from deerflow.sandbox.sandbox_provider import set_sandbox_provider
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.tools import StructuredTool
from langgraph.types import Command

from deerflow_deep_research.domain.context import NodeExecutionResult
from deerflow_deep_research.domain.enums import NodeFinishReason
from deerflow_deep_research.graph.topology import LOGICAL_NODES
from deerflow_deep_research.runtime.control import build_control_graph_host
from deerflow_deep_research.runtime.node_agent_bridge import RuntimeNodeAgentBridge
from deerflow_deep_research.runtime.research import ResearchGraphRecipe
from deerflow_deep_research.runtime.work_unit_store import WorkUnitStore
from deerflow_deep_research.tool import run_deep_research
from tests.fixtures.runtime import local_runtime_envelope, unique_run_identity
from tests.scenarios.live import LiveAttempt, LiveScenarioReport, LiveScenarioRunner, preflight_live_environment
from tests.scenarios.model import AuthenticityLevel, Scenario, ScenarioOutcome

_FAKE_MODES = {name: "fake" for name in LOGICAL_NODES}
_MODEL_CONFIGS = {
    "deepseek": (
        "deerflow.models.patched_deepseek:PatchedChatDeepSeek",
        "deepseek-v4-pro",
        "https://api.deepseek.com/v1",
    ),
    "anthropic": ("langchain_anthropic:ChatAnthropic", "claude-sonnet-4-5-20250901", None),
    "openai": ("langchain_openai:ChatOpenAI", "gpt-4o", None),
}
_PROFILE = json.dumps(
    {
        "depth": "quick_overview",
        "audience": "domain_expert",
        "format": "annotated_bibliography",
        "cost_tolerance": "minimal",
        "time_budget": "very_quick",
        "must_answer": ["What evidence supports the answer?"],
    }
)
_BRIEF = json.dumps(
    {
        "schema_version": 1,
        "brief_summary": "A bounded live canary research brief.",
        "depth": "quick_overview",
        "audience": "domain_expert",
        "format": "annotated_bibliography",
        "cost_tolerance": "minimal",
        "time_budget": "very_quick",
        "must_answer": ["What evidence supports the answer?"],
        "scope_boundaries": "One narrow public-source topic.",
        "custom_notes": "Live canary only.",
    }
)
_PLAN = json.dumps(
    {
        "schema_version": 1,
        "topics": [
            {
                "title": "Primary evidence",
                "scope": "One authoritative source answering the canary question",
                "must_answer_bindings": ["What evidence supports the answer?"],
                "search_dimensions": ["official source"],
                "exclusions": [],
            }
        ],
    }
)


def _canary(scenario_id: str, focused_node: str, *, require_web: bool) -> Scenario:
    return Scenario(
        scenario_id=scenario_id,
        risk_family="live-prefix",
        requirement_ids=("EVH-005", "EVH-009"),
        regression_ids=(),
        entrypoint="deep_research.start/resume",
        authenticity=AuthenticityLevel.LIVE_REAL_DEPENDENCIES,
        preconditions={
            "identity": "unique-per-invocation",
            "focused_node": focused_node,
            "require_web": require_web,
            "timeout_seconds": 300,
            "max_attempts": 1,
            "max_total_tokens": 32_768,
            "max_model_calls": 4 if require_web else 1,
            "max_tool_calls": 3 if require_web else 0,
        },
        scripted_inputs=(),
        live_requirements=("model", "web_search") if require_web else ("model",),
        expected=ScenarioOutcome(route=scenario_id.removeprefix("live-")),
        hard_invariants=("identity_isolated", "bounded_attempts", "expected_prefix", "authority"),
        metrics=("citation_precision", "must_answer_coverage"),
    )


LIVE_CANARIES = (
    _canary("live-start-to-hitl1", "hitl1", require_web=False),
    _canary("live-hitl1-to-topic-planning", "topic_planning", require_web=False),
    _canary("live-one-topic-wave0", "wave0", require_web=True),
)


class _UsageTracker(BaseCallbackHandler):
    def __init__(self, *, model_id: str) -> None:
        self.model_id = model_id
        self.input_tokens = 0
        self.output_tokens = 0
        self.response_shapes: list[dict[str, Any]] = []

    def on_llm_end(self, response: Any, **_kwargs: Any) -> None:
        for generation_group in getattr(response, "generations", ()) or ():
            for generation in generation_group:
                message = getattr(generation, "message", None)
                usage = getattr(message, "usage_metadata", None) or {}
                self.input_tokens += int(usage.get("input_tokens") or 0)
                self.output_tokens += int(usage.get("output_tokens") or 0)
                self.response_shapes.append(self._response_shape(message))

    @staticmethod
    def _response_shape(message: Any) -> dict[str, Any]:
        content = getattr(message, "content", "")
        text = content if isinstance(content, str) else ""
        stripped = text.strip()
        keys: list[str] = []
        payload: Any = None
        if not stripped:
            kind = "empty"
        else:
            try:
                payload = json.loads(stripped)
            except json.JSONDecodeError:
                start = stripped.find("{")
                end = stripped.rfind("}")
                payload = None
                if 0 <= start < end:
                    try:
                        payload = json.loads(stripped[start : end + 1])
                    except json.JSONDecodeError:
                        pass
                if isinstance(payload, dict):
                    kind = "fenced_json_object" if "```" in stripped else "embedded_json_object"
                    keys = sorted(str(key) for key in payload)[:16]
                else:
                    kind = "fenced" if "```" in stripped else "prose"
            else:
                if isinstance(payload, dict):
                    kind = "json_object"
                    keys = sorted(str(key) for key in payload)[:16]
                elif isinstance(payload, list):
                    kind = "json_array"
                else:
                    kind = "json_scalar"
        tool_names = [
            str(call.get("name"))
            for call in (getattr(message, "tool_calls", None) or ())
            if isinstance(call, dict) and call.get("name")
        ]
        shape: dict[str, Any] = {
            "content_chars": len(text),
            "content_kind": kind,
            "json_keys": keys,
            "tool_names": tool_names,
        }
        if isinstance(payload, dict) and "sources" in payload:
            from pydantic import ValidationError

            from deerflow_deep_research.domain.wave1 import Wave1WorkerOutput
            from deerflow_deep_research.domain.work_units import Wave0WorkerOutput, WorkerSource

            raw_sources = payload.get("sources")
            sources = raw_sources if isinstance(raw_sources, list) else []
            source_keys = sorted({str(key) for source in sources if isinstance(source, dict) for key in source})[:16]
            first_source = next((source for source in sources if isinstance(source, dict)), {})
            shape.update(
                {
                    "source_count": len(sources),
                    "source_item_keys": source_keys,
                    "source_field_types": {
                        str(key): type(value).__name__ for key, value in sorted(first_source.items())
                    },
                }
            )
            raw_wave0_errors: list[str] = []
            for index, source in enumerate(sources):
                try:
                    WorkerSource.model_validate(source)
                except ValidationError as exc:
                    raw_wave0_errors.extend(
                        f"sources.{index}.{'.'.join(str(part) for part in error['loc'])}:{error['type']}"
                        for error in exc.errors(include_input=False, include_url=False)
                    )
            try:
                Wave0WorkerOutput.model_validate(payload)
            except ValidationError as exc:
                shape["wave0_schema_valid"] = False
                normalized_errors = [
                    f"{'.'.join(str(part) for part in error['loc'])}:{error['type']}"
                    for error in exc.errors(include_input=False, include_url=False)
                ]
                shape["wave0_validation_errors"] = list(dict.fromkeys([*raw_wave0_errors, *normalized_errors]))[:16]
            else:
                shape["wave0_schema_valid"] = True
                shape["wave0_validation_errors"] = list(dict.fromkeys(raw_wave0_errors))[:16]
            try:
                Wave1WorkerOutput.model_validate(payload)
            except ValidationError as exc:
                shape["wave1_schema_valid"] = False
                shape["wave1_validation_errors"] = [
                    f"{'.'.join(str(part) for part in error['loc'])}:{error['type']}"
                    for error in exc.errors(include_input=False, include_url=False)[:16]
                ]
            else:
                shape["wave1_schema_valid"] = True
                shape["wave1_validation_errors"] = []
        if isinstance(payload, dict) and "findings" in payload:
            from pydantic import ValidationError

            from deerflow_deep_research.domain.synthesis import SynthesisFinding, SynthesisResult

            raw_synthesis_errors: list[str] = []
            raw_findings = payload.get("findings")
            raw_relations = payload.get("relations")
            raw_gaps = payload.get("gaps")
            shape["finding_count"] = len(raw_findings) if isinstance(raw_findings, list) else 0
            shape["relation_count"] = len(raw_relations) if isinstance(raw_relations, list) else 0
            shape["gap_count"] = len(raw_gaps) if isinstance(raw_gaps, list) else 0
            shape["finding_item_keys"] = sorted(
                {str(key) for finding in raw_findings or () if isinstance(finding, dict) for key in finding}
            )[:16]
            shape["relation_item_keys"] = sorted(
                {str(key) for relation in raw_relations or () if isinstance(relation, dict) for key in relation}
            )[:16]
            shape["gap_item_keys"] = sorted(
                {str(key) for gap in raw_gaps or () if isinstance(gap, dict) for key in gap}
            )[:16]
            shape["gap_item_types"] = sorted({type(gap).__name__ for gap in raw_gaps or ()})[:8]
            if isinstance(raw_findings, list):
                for index, finding in enumerate(raw_findings):
                    try:
                        SynthesisFinding.model_validate(finding)
                    except ValidationError as exc:
                        raw_synthesis_errors.extend(
                            f"findings.{index}.{'.'.join(str(part) for part in error['loc'])}:{error['type']}"
                            for error in exc.errors(include_input=False, include_url=False)
                        )
            try:
                SynthesisResult.model_validate(payload)
            except ValidationError as exc:
                shape["synthesis_schema_valid"] = False
                normalized_errors = [
                    f"{'.'.join(str(part) for part in error['loc'])}:{error['type']}"
                    for error in exc.errors(include_input=False, include_url=False)
                ]
                shape["synthesis_validation_errors"] = list(dict.fromkeys([*raw_synthesis_errors, *normalized_errors]))[
                    :16
                ]
                shape["synthesis_raw_error_count"] = len(raw_synthesis_errors)
                shape["synthesis_normalized_error_count"] = len(normalized_errors)
            else:
                shape["synthesis_schema_valid"] = True
                shape["synthesis_validation_errors"] = list(dict.fromkeys(raw_synthesis_errors))[:16]
                shape["synthesis_raw_error_count"] = len(raw_synthesis_errors)
                shape["synthesis_normalized_error_count"] = 0
        return shape

    def diagnostic_summary(self) -> str:
        return json.dumps(self.response_shapes, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


class _LiveWebSearch:
    def __init__(self, api_key: str) -> None:
        self._api_key = api_key
        self.calls = 0

    async def search(self, query: str) -> str:
        from tavily import TavilyClient

        self.calls += 1
        response = await asyncio.to_thread(TavilyClient(api_key=self._api_key).search, query, max_results=3)
        normalized = [
            {"title": item.get("title", "Untitled"), "url": item.get("url", ""), "snippet": item.get("content", "")}
            for item in response.get("results", ())
        ]
        return json.dumps(normalized, ensure_ascii=True)

    def as_tool(self) -> StructuredTool:
        return StructuredTool.from_function(
            coroutine=self.search,
            name="web_search",
            description="Search public web sources for a narrow research question.",
        )


class _FocusedCapabilities:
    def __init__(self, *, focused_node: str | None, real: RuntimeNodeAgentBridge) -> None:
        self._focused_node = focused_node
        self._real = real

    async def run_agent(self, *, context, request) -> NodeExecutionResult:
        if self._focused_node is None or context.node_name == self._focused_node:
            return await self._real.run_agent(context=context, request=request)
        summary = _BRIEF if context.node_name == "hitl1" else _PLAN
        return NodeExecutionResult(finish_reason=NodeFinishReason.SUCCESS, summary=summary)


class _BridgeFactory:
    def __init__(self, *, focused_node: str | None, tracker: _UsageTracker, web: _LiveWebSearch | None) -> None:
        self._focused_node = focused_node
        self._tracker = tracker
        self._web = web

    def __call__(self, *, envelope, policy, tools_resolver=None):
        from deerflow.models.factory import create_chat_model

        bounded_budget = replace(
            policy.budget,
            max_model_calls=4 if policy.allowed_tool_names else 1,
            max_total_tool_calls=3 if policy.allowed_tool_names else 1,
            max_tool_calls_per_response=3 if policy.allowed_tool_names else 1,
            max_parallel_tool_calls=3 if policy.allowed_tool_names else 1,
            total_token_budget=32_768,
            per_call_output_token_cap=4_096,
            per_tool_result_bytes=16_384 if policy.allowed_tool_names else 1,
            structured_result_bytes=8_192,
            wall_time_seconds=180.0,
        )
        bounded_policy = replace(policy, budget=bounded_budget)

        def model_resolver(bound_envelope):
            return create_chat_model(
                app_config=bound_envelope.app_config,
                attach_tracing=False,
                callbacks=[self._tracker],
            )

        if self._web is not None and bounded_policy.allowed_tool_names:

            def resolved_tools(_envelope, _policy):
                return (self._web.as_tool(),)

        else:

            def no_tools(_envelope, _policy):
                return ()

            resolved_tools = tools_resolver or no_tools
        bridge = RuntimeNodeAgentBridge(
            envelope=envelope,
            policy=bounded_policy,
            model_resolver=model_resolver,
            tools_resolver=resolved_tools,
        )
        return _FocusedCapabilities(focused_node=self._focused_node, real=bridge)


class _LiveAdapter:
    def __init__(self, workspace: Path, app_config: AppConfig, *, identity=None) -> None:
        self.root = workspace
        self.identity = identity or unique_run_identity()
        self.envelope = local_runtime_envelope(workspace, identity=self.identity, app_config=app_config)
        self.stores: dict[str, WorkUnitStore] = {}
        set_sandbox_provider(_RegisteredLocalProvider(self.envelope.parent_sandbox))

    async def adapt(self, _runtime: Any, *, initialize_parent_sandbox: bool = True):
        if initialize_parent_sandbox:
            return self.envelope
        return replace(self.envelope, parent_sandbox=None)

    async def create_work_unit_store(self, _envelope: Any, *, research_id: str) -> WorkUnitStore:
        store = await WorkUnitStore.create(self.envelope, research_id=research_id)
        self.stores[research_id] = store
        return store


class _RegisteredLocalProvider:
    uses_thread_data_mounts = True
    needs_upload_permission_adjustment = False

    def __init__(self, sandbox: Any) -> None:
        self._sandbox = sandbox

    def acquire(self, thread_id: str | None = None, *, user_id: str | None = None) -> str:
        del thread_id, user_id
        return self._sandbox.id

    def get(self, sandbox_id: str) -> Any | None:
        return self._sandbox if sandbox_id == self._sandbox.id else None

    def release(self, sandbox_id: str) -> None:
        del sandbox_id

    def reset(self) -> None:
        return None


def _tool_call(action: str, call_id: str, research_id: str | None = None) -> AIMessage:
    args = {"action": action}
    if research_id is not None:
        args["research_id"] = research_id
    return AIMessage(content="", tool_calls=[{"name": "deep_research", "args": args, "id": call_id}])


def _runtime(messages: list[Any], call_id: str) -> SimpleNamespace:
    return SimpleNamespace(state={"messages": messages}, context={}, tool_call_id=call_id)


def _command_payload(command: Command) -> tuple[dict[str, Any], dict[str, Any]]:
    message = command.update["messages"][0]
    return json.loads(message.content), message.artifact["human_input"]


def _profile_response(request_id: str, message_id: str) -> HumanMessage:
    payload = {
        "version": 1,
        "kind": "human_input_response",
        "source": "deep_research",
        "request_id": request_id,
        "response_kind": "text",
        "value": _PROFILE,
    }
    return HumanMessage(content=_PROFILE, id=message_id, additional_kwargs={"human_input_response": payload})


def _modes(focused_node: str) -> dict[str, str]:
    real_prefixes = {
        "hitl1": ("bootstrap", "hitl1"),
        "topic_planning": ("bootstrap", "hitl1", "topic_planning"),
        "wave0": ("bootstrap", "hitl1", "topic_planning", "wave0"),
    }
    return _FAKE_MODES | {name: "real" for name in real_prefixes[focused_node]}


def _app_config(provider: str, api_key: str) -> AppConfig:
    use, model, base_url = _MODEL_CONFIGS[provider]
    values: dict[str, Any] = {
        "name": f"{provider}-live-canary",
        "use": use,
        "model": model,
        "api_key": api_key,
        "max_retries": 0,
    }
    if base_url is not None:
        values["base_url"] = base_url
    return AppConfig(
        models=[ModelConfig(**values)],
        sandbox=SandboxConfig(use="deerflow.sandbox.local:LocalSandboxProvider"),
    )


async def _execute_canary(
    scenario: Scenario,
    *,
    environ: dict[str, str] | Any,
    workspace: Path,
) -> LiveAttempt:
    started_at = time.monotonic()
    require_web = bool(scenario.preconditions["require_web"])
    environment = preflight_live_environment(environ=environ, require_web=require_web)
    credential_name = next(
        name
        for name, provider in {
            "ANTHROPIC_API_KEY": "anthropic",
            "DEEPSEEK_API_KEY": "deepseek",
            "OPENAI_API_KEY": "openai",
        }.items()
        if provider == environment.model_provider
    )
    app_config = _app_config(environment.model_provider, environ[credential_name])
    model = app_config.models[0]
    tracker = _UsageTracker(model_id=f"{environment.model_provider}/{model.model}")
    web = _LiveWebSearch(environ["TAVILY_API_KEY"]) if require_web else None
    focused_node = str(scenario.preconditions["focused_node"])
    bridge_factory = _BridgeFactory(focused_node=focused_node, tracker=tracker, web=web)
    adapter = _LiveAdapter(workspace / scenario.scenario_id, app_config)
    recipe = ResearchGraphRecipe.create(
        implementation_modes=_modes(focused_node),
        work_unit_store_factory=adapter.create_work_unit_store,
        node_agent_bridge_factory=bridge_factory,
    )
    host = build_control_graph_host(fingerprint_verifier=lambda _config: None, research_recipe=recipe)
    question = HumanMessage(content="What is one authoritative fact about grid energy storage?", id="live-start")
    start_call = _tool_call("start", "live-start-call")
    started = await run_deep_research(
        action="start",
        probe_id=None,
        runtime=_runtime([question, start_call], "live-start-call"),
        adapter=adapter,
        host_factory=lambda: host,
    )
    if not isinstance(started, Command):
        code = started.get("code") if isinstance(started, dict) else type(started).__name__
        return _failed_attempt(
            code=f"live_start_not_suspended:{code}",
            tracker=tracker,
            web=web,
            started_at=started_at,
            workflow_attempts=0,
        )
    control, hitl1 = _command_payload(started)
    research_id = str(control["research_id"])
    route = "start-to-hitl1"
    artifacts: tuple[str, ...] = ()
    accepted_refs: tuple[str, ...] = ()

    if focused_node != "hitl1":
        response = _profile_response(str(hitl1["request_id"]), "live-profile")
        resume_call = _tool_call("resume", "live-resume-call", research_id)
        resumed = await run_deep_research(
            action="resume",
            probe_id=None,
            research_id=research_id,
            runtime=_runtime([question, response, resume_call], "live-resume-call"),
            adapter=adapter,
            host_factory=lambda: host,
        )
        if not isinstance(resumed, Command):
            code = resumed.get("code") if isinstance(resumed, dict) else type(resumed).__name__
            attempt_count = len(
                tuple(
                    adapter.envelope.workspace_host_path.glob(
                        f"deep-research/{research_id}/work/g0_{focused_node}_w*/g0_{focused_node}_w*_a*/work-spec.json"
                    )
                )
            )
            return _failed_attempt(
                code=f"live_resume_not_suspended:{code}",
                tracker=tracker,
                web=web,
                started_at=started_at,
                workflow_attempts=max(attempt_count, 1),
            )
        control, _hitl2 = _command_payload(resumed)
        trace = tuple(control.get("execution_trace", ()))
        if focused_node not in trace:
            raise AssertionError(f"live_prefix_missing:{focused_node}")
        route = "hitl1-to-topic-planning" if focused_node == "topic_planning" else "one-topic-wave0"
        if focused_node == "wave0":
            records = await adapter.stores[research_id].load_records()
            wave0_records = tuple(record for record in records if record.phase.value == "wave0")
            if len(wave0_records) != 1 or web is None or web.calls < 1:
                raise AssertionError("live_wave0_authority_missing")
            accepted_refs = tuple(f"ref:{record.record_hash}" for record in wave0_records)
            artifacts = tuple(record.result_ref for record in wave0_records)

    outcome = ScenarioOutcome(
        route=route,
        artifacts=artifacts,
        values={
            "accepted_submission_refs": accepted_refs,
            "must_answer_questions": ("What evidence supports the answer?",),
            "identity": {
                "thread_id": adapter.identity.thread_id,
                "run_id": adapter.identity.run_id,
                "research_id": research_id,
            },
        },
    )
    return LiveAttempt(
        outcome=outcome,
        error_code=None,
        model_id=tracker.model_id,
        tool_ids=("tavily/web_search",) if web is not None else (),
        input_tokens=tracker.input_tokens or None,
        output_tokens=tracker.output_tokens or None,
        cost_usd=None,
        tool_calls=web.calls if web is not None else 0,
        wall_time_seconds=time.monotonic() - started_at,
        diagnostics="live prefix completed",
        workflow_attempts=1,
        workflow_retries=0,
    )


def _failed_attempt(
    *,
    code: str,
    tracker: _UsageTracker,
    web: _LiveWebSearch | None,
    started_at: float,
    workflow_attempts: int,
) -> LiveAttempt:
    return LiveAttempt(
        outcome=None,
        error_code=code,
        model_id=tracker.model_id,
        tool_ids=("tavily/web_search",) if web is not None else (),
        input_tokens=tracker.input_tokens or None,
        output_tokens=tracker.output_tokens or None,
        cost_usd=None,
        tool_calls=web.calls if web is not None else 0,
        wall_time_seconds=time.monotonic() - started_at,
        diagnostics=f"{code}; response_shapes={tracker.diagnostic_summary()}",
        workflow_attempts=workflow_attempts,
        workflow_retries=max(workflow_attempts - 1, 0),
    )


async def run_live_canary(
    scenario: Scenario,
    *,
    environ: dict[str, str] | Any,
    workspace: Path,
) -> LiveScenarioReport:
    async def execute(selected: Scenario) -> LiveAttempt:
        return await _execute_canary(selected, environ=environ, workspace=workspace)

    runner = LiveScenarioRunner(executor=execute, max_attempts=int(scenario.preconditions["max_attempts"]))
    return await asyncio.wait_for(runner.run(scenario), timeout=float(scenario.preconditions["timeout_seconds"]))


__all__ = ["LIVE_CANARIES", "run_live_canary"]
