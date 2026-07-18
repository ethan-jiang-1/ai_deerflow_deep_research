"""Manual full-real release acceptance control plane.

@impl EVH-004
@impl EVH-005
@impl EVH-009
"""

from __future__ import annotations

import hashlib
import json
import re
import secrets
import shutil
import time
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import asdict, dataclass, fields

from langchain_core.messages import AIMessage, HumanMessage
from langgraph.types import Command

from deerflow_deep_research.domain.lifecycle import LifecycleStatus, PendingResearchInterrupt
from deerflow_deep_research.domain.state import ResearchCheckpoint, project_lifecycle_status
from deerflow_deep_research.graph.topology import LOGICAL_NODES
from deerflow_deep_research.runtime.checkpoint import derive_research_thread_key
from deerflow_deep_research.runtime.control import build_control_graph_host
from deerflow_deep_research.runtime.research import ResearchGraphRecipe, derive_research_id
from deerflow_deep_research.tool import run_deep_research
from tests.assets.evidence import AuthenticityLevel
from tests.fixtures.runtime import RunIdentity
from tests.scenarios.canaries import (
    _app_config,
    _BridgeFactory,
    _LiveAdapter,
    _LiveWebSearch,
    _UsageTracker,
)
from tests.scenarios.live import LiveEnvironment, LivePreflightError, preflight_live_environment


class ReleasePreflightError(RuntimeError):
    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code


def preflight_release_environment(*, environ: Mapping[str, str]) -> LiveEnvironment:
    if environ.get("RELEASE_E2E_CONFIRM") != "1":
        raise ReleasePreflightError(
            "release_confirmation_missing",
            "set RELEASE_E2E_CONFIRM=1 before selecting full-real acceptance",
        )
    try:
        return preflight_live_environment(environ=environ, require_web=True)
    except LivePreflightError as exc:
        raise ReleasePreflightError(exc.code, str(exc).split(": ", 1)[-1]) from exc


@dataclass(frozen=True)
class ReleaseInvocation:
    user_id: str
    thread_id: str
    run_id: str
    research_id: str
    checkpoint_key: str


def new_release_invocation() -> ReleaseInvocation:
    token = secrets.token_urlsafe(18).replace("-", "_")
    user_id = "release-e2e"
    thread_id = f"release-thread-{token}"
    run_id = f"release-run-{token}"
    research_id = derive_research_id(effective_user_id=user_id, outer_thread_id=thread_id)
    checkpoint_key = hashlib.sha256(f"release-checkpoint:{thread_id}:{run_id}".encode()).hexdigest()
    return ReleaseInvocation(user_id, thread_id, run_id, research_id, checkpoint_key)


@dataclass(frozen=True)
class ReleaseScenario:
    scenario_id: str
    authenticity: AuthenticityLevel
    expected_trace: tuple[str, ...]
    required_artifacts: tuple[str, ...]


RELEASE_SCENARIO = ReleaseScenario(
    scenario_id="release-full-real-acceptance",
    authenticity=AuthenticityLevel.FULL_REAL_PIPELINE,
    expected_trace=(
        "bootstrap",
        "hitl1",
        "topic_planning",
        "wave0",
        "wave1",
        "wave2_synthesis",
        "hitl2",
        "readiness",
        "final_delivery",
    ),
    required_artifacts=("final/report.md", "final/claim-citation-map.json"),
)


@dataclass(frozen=True)
class ReleaseOutcome:
    invocation: ReleaseInvocation
    terminal_status: str
    lifecycle_trace: tuple[str, ...]
    accepted_submission_refs: tuple[str, ...]
    artifacts: tuple[str, ...]
    citation_bindings: dict[str, tuple[str, ...]]
    contained: bool
    cleaned_up: bool


@dataclass(frozen=True)
class ReleaseAttempt:
    outcome: ReleaseOutcome | None
    error_code: str | None
    wall_time_seconds: float
    input_tokens: int | None = None
    output_tokens: int | None = None
    tool_calls: int = 0
    checkpoint_validation_error: str | None = None
    checkpoint_summary: dict[str, object] | None = None
    response_shapes: tuple[dict[str, object], ...] = ()


@dataclass(frozen=True)
class ReleaseAttemptReport:
    attempt: int
    error_code: str | None
    wall_time_seconds: float
    input_tokens: int | None
    output_tokens: int | None
    tool_calls: int
    checkpoint_validation_error: str | None
    checkpoint_summary: dict[str, object] | None
    response_shapes: tuple[dict[str, object], ...]


@dataclass(frozen=True)
class ReleaseReport:
    scenario_id: str
    invocation: ReleaseInvocation
    attempt_count: int
    retry_count: int
    hard_invariants: dict[str, bool]
    outcome_summary: dict[str, object] | None
    attempts: tuple[ReleaseAttemptReport, ...]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class ReleaseAcceptanceFailure(AssertionError):
    def __init__(self, message: str, report: ReleaseReport) -> None:
        super().__init__(message)
        self.report = report


ReleaseExecutor = Callable[[ReleaseScenario, ReleaseInvocation], Awaitable[ReleaseAttempt]]


def _hard_invariants(
    scenario: ReleaseScenario,
    invocation: ReleaseInvocation,
    outcome: ReleaseOutcome | None,
) -> dict[str, bool]:
    if outcome is None:
        return {
            "terminal_completed": False,
            "lifecycle_trace_complete": False,
            "accepted_evidence_present": False,
            "report_artifacts_present": False,
            "citation_bindings_valid": False,
            "paths_contained": False,
            "cleanup_complete": False,
            "checkpoint_isolated": False,
        }
    accepted = set(outcome.accepted_submission_refs)
    bound_refs = {ref for refs in outcome.citation_bindings.values() for ref in refs}
    collapsed_trace: list[str] = []
    max_consecutive_visits = 0
    consecutive_visits = 0
    for phase in outcome.lifecycle_trace:
        if collapsed_trace and phase == collapsed_trace[-1]:
            consecutive_visits += 1
        else:
            collapsed_trace.append(phase)
            consecutive_visits = 1
        max_consecutive_visits = max(max_consecutive_visits, consecutive_visits)
    return {
        "terminal_completed": outcome.terminal_status == "completed",
        "lifecycle_trace_complete": tuple(collapsed_trace) == scenario.expected_trace and max_consecutive_visits <= 3,
        "accepted_evidence_present": bool(accepted),
        "report_artifacts_present": set(scenario.required_artifacts) <= set(outcome.artifacts),
        "citation_bindings_valid": bool(outcome.citation_bindings) and bound_refs <= accepted,
        "paths_contained": outcome.contained,
        "cleanup_complete": outcome.cleaned_up,
        "checkpoint_isolated": outcome.invocation == invocation,
    }


def _outcome_summary(outcome: ReleaseOutcome | None) -> dict[str, object] | None:
    if outcome is None:
        return None
    return {
        "terminal_status": outcome.terminal_status,
        "lifecycle_trace": outcome.lifecycle_trace,
        "accepted_count": len(outcome.accepted_submission_refs),
        "artifacts": outcome.artifacts,
        "citation_claim_count": len(outcome.citation_bindings),
        "citation_ref_count": sum(len(refs) for refs in outcome.citation_bindings.values()),
        "contained": outcome.contained,
        "cleaned_up": outcome.cleaned_up,
    }


class ReleaseRunner:
    def __init__(self, *, executor: ReleaseExecutor, max_attempts: int) -> None:
        if not 1 <= max_attempts <= 2:
            raise ValueError("release_attempt_bound_invalid")
        self._executor = executor
        self._max_attempts = max_attempts

    async def run(self, scenario: ReleaseScenario, invocation: ReleaseInvocation) -> ReleaseReport:
        attempts: list[ReleaseAttempt] = []
        outcome: ReleaseOutcome | None = None
        for _ in range(self._max_attempts):
            attempt = await self._executor(scenario, invocation)
            attempts.append(attempt)
            if attempt.outcome is not None:
                outcome = attempt.outcome
                break
        invariants = _hard_invariants(scenario, invocation, outcome)
        report = ReleaseReport(
            scenario_id=scenario.scenario_id,
            invocation=invocation,
            attempt_count=len(attempts),
            retry_count=len(attempts) - 1,
            hard_invariants=invariants,
            outcome_summary=_outcome_summary(outcome),
            attempts=tuple(
                ReleaseAttemptReport(
                    index,
                    attempt.error_code,
                    attempt.wall_time_seconds,
                    attempt.input_tokens,
                    attempt.output_tokens,
                    attempt.tool_calls,
                    attempt.checkpoint_validation_error,
                    attempt.checkpoint_summary,
                    attempt.response_shapes,
                )
                for index, attempt in enumerate(attempts, start=1)
            ),
        )
        if not all(invariants.values()):
            failed = ",".join(name for name, passed in invariants.items() if not passed)
            raise ReleaseAcceptanceFailure(
                f"scenario={scenario.scenario_id} lane=release authenticity=full_real_pipeline: "
                f"hard invariants failed: {failed}",
                report,
            )
        return report


def _tool_call(action: str, call_id: str, research_id: str | None = None) -> AIMessage:
    args = {"action": action}
    if research_id is not None:
        args["research_id"] = research_id
    return AIMessage(content="", tool_calls=[{"name": "deep_research", "args": args, "id": call_id}])


def _runtime(messages: list[object], call_id: str):
    from types import SimpleNamespace

    return SimpleNamespace(state={"messages": messages}, context={}, tool_call_id=call_id)


def _command_payload(command: Command) -> tuple[dict[str, object], dict[str, object]]:
    message = command.update["messages"][0]
    return json.loads(message.content), message.artifact["human_input"]


def _response(request_id: str, message_id: str, *, kind: str, value: str) -> HumanMessage:
    payload: dict[str, object] = {
        "version": 1,
        "kind": "human_input_response",
        "source": "deep_research",
        "request_id": request_id,
        "response_kind": kind,
        "value": value,
    }
    if kind == "option":
        payload["option_id"] = value
    return HumanMessage(content=value, id=message_id, additional_kwargs={"human_input_response": payload})


def _contained_files(root, research_id: str) -> tuple[tuple[str, ...], bool]:
    bundle = root / "deep-research" / research_id
    files: list[str] = []
    contained = True
    if bundle.exists():
        resolved_root = root.resolve()
        for path in bundle.rglob("*"):
            if not path.is_file():
                continue
            try:
                path.resolve().relative_to(resolved_root)
            except ValueError:
                contained = False
            files.append(path.relative_to(bundle).as_posix())
    return tuple(sorted(files)), contained


async def _checkpoint_validation_error(host, invocation: ReleaseInvocation) -> str:
    saver = getattr(host, "_memory_saver", None)
    builders = getattr(host, "_builders", {})
    builder = builders.get("resume") or builders.get("start")
    if saver is None or builder is None:
        return "snapshot_unavailable"
    thread_id = derive_research_thread_key(
        effective_user_id=invocation.user_id,
        outer_thread_id=invocation.thread_id,
        research_id=invocation.research_id,
    )
    graph = builder.compile(checkpointer=saver)
    snapshot = await graph.aget_state({"configurable": {"thread_id": thread_id, "checkpoint_ns": ""}})
    values = dict(snapshot.values)
    known_fields = {field.name for field in fields(ResearchCheckpoint)}
    unknown = sorted(set(values) - known_fields)
    if unknown:
        return f"unexpected_field:{unknown[0]}"
    try:
        checkpoint = ResearchCheckpoint(**values)
    except TypeError as exc:
        match = re.search(r"unexpected keyword argument '([a-zA-Z0-9_]+)'", str(exc))
        return f"unexpected_field:{match.group(1)}" if match else "checkpoint_type_error"
    except ValueError as exc:
        tokens = re.findall(r"[a-z][a-z0-9_]{2,63}", str(exc).lower())
        suffixes = (
            "_invalid",
            "_missing",
            "_conflict",
            "_too_large",
            "_too_many",
            "_unsupported",
            "_not_canonical",
            "_exceeded",
        )
        return next((token for token in tokens if token.endswith(suffixes)), "checkpoint_value_error")
    interrupts = [interrupt for task in snapshot.tasks for interrupt in task.interrupts]
    status = project_lifecycle_status(checkpoint)
    if not interrupts:
        return "suspended_without_interrupt" if status is LifecycleStatus.SUSPENDED else "checkpoint_valid"
    if len(interrupts) != 1:
        return "multiple_pending_interrupts"
    try:
        PendingResearchInterrupt.model_validate(interrupts[0].value)
    except (TypeError, ValueError):
        return "pending_interrupt_invalid"
    if status is not LifecycleStatus.SUSPENDED:
        return "terminal_with_pending_interrupt"
    return "checkpoint_valid"


def _structural_checkpoint_summary(
    values: Mapping[str, object],
    *,
    pending_interrupt_count: int,
) -> dict[str, object]:
    status_counts: dict[str, int] = {}
    raw_statuses = values.get("work_status_by_id")
    if isinstance(raw_statuses, Mapping):
        for raw_status in raw_statuses.values():
            status = getattr(raw_status, "value", raw_status)
            label = str(status)
            status_counts[label] = status_counts.get(label, 0) + 1
    failure_codes: set[str] = set()
    raw_failures = values.get("terminal_failures_by_attempt_id")
    if isinstance(raw_failures, Mapping):
        for raw_failure in raw_failures.values():
            if isinstance(raw_failure, Mapping) and isinstance(raw_failure.get("failure_code"), str):
                failure_codes.add(str(raw_failure["failure_code"]))
    raw_trace = values.get("execution_trace")
    trace = tuple(str(phase) for phase in raw_trace) if isinstance(raw_trace, (tuple, list)) else ()
    raw_accepted = values.get("accepted_submission_refs")
    accepted_count = len(raw_accepted) if isinstance(raw_accepted, (tuple, list)) else 0
    return {
        "accepted_count": accepted_count,
        "execution_trace": trace,
        "failure_codes": tuple(sorted(failure_codes)),
        "pending_interrupt_count": pending_interrupt_count,
        "phase": str(values.get("phase", "")),
        "phase_status": str(values.get("phase_status", "")),
        "route": str(values.get("route", "")),
        "terminal_status": str(values.get("terminal_status", "")),
        "work_status_counts": dict(sorted(status_counts.items())),
    }


async def _checkpoint_summary(host, invocation: ReleaseInvocation) -> dict[str, object] | None:
    saver = getattr(host, "_memory_saver", None)
    builders = getattr(host, "_builders", {})
    builder = builders.get("resume") or builders.get("start")
    if saver is None or builder is None:
        return None
    thread_id = derive_research_thread_key(
        effective_user_id=invocation.user_id,
        outer_thread_id=invocation.thread_id,
        research_id=invocation.research_id,
    )
    graph = builder.compile(checkpointer=saver)
    snapshot = await graph.aget_state({"configurable": {"thread_id": thread_id, "checkpoint_ns": ""}})
    pending_count = sum(len(task.interrupts) for task in snapshot.tasks)
    return _structural_checkpoint_summary(dict(snapshot.values), pending_interrupt_count=pending_count)


async def execute_full_real_release(
    scenario: ReleaseScenario,
    invocation: ReleaseInvocation,
    *,
    environ: Mapping[str, str],
    workspace,
) -> ReleaseAttempt:
    started_at = time.monotonic()
    environment = preflight_release_environment(environ=environ)
    credential_names = {
        "deepseek": "DEEPSEEK_API_KEY",
        "anthropic": "ANTHROPIC_API_KEY",
        "openai": "OPENAI_API_KEY",
    }
    app_config = _app_config(environment.model_provider, environ[credential_names[environment.model_provider]])
    model = app_config.models[0]
    tracker = _UsageTracker(model_id=f"{environment.model_provider}/{model.model}")
    web = _LiveWebSearch(environ["TAVILY_API_KEY"])
    adapter = _LiveAdapter(
        workspace / invocation.checkpoint_key,
        app_config,
        identity=RunIdentity(invocation.user_id, invocation.thread_id, invocation.run_id, invocation.research_id),
    )
    recipe = ResearchGraphRecipe.create(
        implementation_modes={name: "real" for name in LOGICAL_NODES},
        work_unit_store_factory=adapter.create_work_unit_store,
        node_agent_bridge_factory=_BridgeFactory(focused_node=None, tracker=tracker, web=web),
    )
    host = build_control_graph_host(fingerprint_verifier=lambda _config: None, research_recipe=recipe)
    question = HumanMessage(content="Produce an evidence-bound report on grid energy storage.", id="release-start")
    start_call = _tool_call("start", "release-start-call")
    started = await run_deep_research(
        action="start",
        probe_id=None,
        runtime=_runtime([question, start_call], "release-start-call"),
        adapter=adapter,
        host_factory=lambda: host,
    )
    if not isinstance(started, Command):
        return ReleaseAttempt(
            outcome=None,
            error_code=f"start:{started.get('code', 'invalid')}",
            wall_time_seconds=time.monotonic() - started_at,
            input_tokens=tracker.input_tokens or None,
            output_tokens=tracker.output_tokens or None,
            tool_calls=web.calls,
            response_shapes=tuple(tracker.response_shapes[-16:]),
        )
    _control, hitl1 = _command_payload(started)
    profile = json.dumps(
        {
            "depth": "quick_overview",
            "audience": "domain_expert",
            "format": "detailed_report",
            "cost_tolerance": "minimal",
            "time_budget": "very_quick",
            "must_answer": ["What evidence supports the answer?"],
        }
    )
    profile_response = _response(str(hitl1["request_id"]), "release-profile", kind="text", value=profile)
    first_resume_call = _tool_call("resume", "release-resume-1", invocation.research_id)
    first_resume = await run_deep_research(
        action="resume",
        probe_id=None,
        research_id=invocation.research_id,
        runtime=_runtime([question, profile_response, first_resume_call], "release-resume-1"),
        adapter=adapter,
        host_factory=lambda: host,
    )
    if not isinstance(first_resume, Command):
        first_resume_code = str(first_resume.get("code", "invalid"))
        checkpoint_summary = await _checkpoint_summary(host, invocation)
        checkpoint_error = (
            await _checkpoint_validation_error(host, invocation)
            if first_resume_code == "checkpoint_inconsistent"
            else None
        )
        return ReleaseAttempt(
            outcome=None,
            error_code=f"first_resume:{first_resume_code}",
            wall_time_seconds=time.monotonic() - started_at,
            input_tokens=tracker.input_tokens or None,
            output_tokens=tracker.output_tokens or None,
            tool_calls=web.calls,
            checkpoint_validation_error=checkpoint_error,
            checkpoint_summary=checkpoint_summary,
            response_shapes=tuple(tracker.response_shapes[-16:]),
        )
    _control, hitl2 = _command_payload(first_resume)
    proceed = _response(str(hitl2["request_id"]), "release-proceed", kind="option", value="proceed")
    second_resume_call = _tool_call("resume", "release-resume-2", invocation.research_id)
    completed = await run_deep_research(
        action="resume",
        probe_id=None,
        research_id=invocation.research_id,
        runtime=_runtime([question, profile_response, proceed, second_resume_call], "release-resume-2"),
        adapter=adapter,
        host_factory=lambda: host,
    )
    if not isinstance(completed, dict):
        return ReleaseAttempt(
            outcome=None,
            error_code="second_resume:suspended",
            wall_time_seconds=time.monotonic() - started_at,
            input_tokens=tracker.input_tokens or None,
            output_tokens=tracker.output_tokens or None,
            tool_calls=web.calls,
            response_shapes=tuple(tracker.response_shapes[-16:]),
        )
    store = adapter.stores.get(invocation.research_id)
    records = await store.load_records() if store is not None else ()
    accepted = tuple(record.record_hash for record in records)
    files, contained = _contained_files(adapter.envelope.workspace_host_path, invocation.research_id)
    citation_path = (
        adapter.envelope.workspace_host_path
        / "deep-research"
        / invocation.research_id
        / "final"
        / "claim-citation-map.json"
    )
    bindings: dict[str, tuple[str, ...]] = {}
    if citation_path.is_file():
        raw = json.loads(citation_path.read_text(encoding="utf-8"))
        bindings = {
            str(claim): tuple(str(ref) for ref in value.get("backing_refs", ()))
            for claim, value in (raw.get("claims") or {}).items()
        }
    root = adapter.root
    root.resolve().relative_to(workspace.resolve())
    shutil.rmtree(root, ignore_errors=True)
    outcome = ReleaseOutcome(
        invocation=invocation,
        terminal_status=str(completed.get("status", "")),
        lifecycle_trace=tuple(completed.get("execution_trace", ())),
        accepted_submission_refs=accepted,
        artifacts=tuple(name for name in files if name.startswith("final/")),
        citation_bindings=bindings,
        contained=contained,
        cleaned_up=not root.exists(),
    )
    return ReleaseAttempt(
        outcome=outcome,
        error_code=None,
        wall_time_seconds=time.monotonic() - started_at,
        input_tokens=tracker.input_tokens or None,
        output_tokens=tracker.output_tokens or None,
        tool_calls=web.calls,
        response_shapes=tuple(tracker.response_shapes[-16:]),
    )


__all__ = [
    "RELEASE_SCENARIO",
    "ReleaseAcceptanceFailure",
    "ReleaseAttempt",
    "ReleaseInvocation",
    "ReleaseOutcome",
    "ReleasePreflightError",
    "ReleaseReport",
    "ReleaseRunner",
    "execute_full_real_release",
    "new_release_invocation",
    "preflight_release_environment",
]
