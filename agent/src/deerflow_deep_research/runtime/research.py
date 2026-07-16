"""Research lifecycle handlers bound to the generic GraphHost.

@impl REG-004
@impl REG-005
@impl REG-006
@impl REG-011
@impl RUI-006
"""

from __future__ import annotations

import base64
import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from typing import Any

from langgraph.types import Command

from deerflow_deep_research.agents.policies import ExecutionBudget, ExecutionPolicy
from deerflow_deep_research.domain.invocation import GraphInvocationContext, WorkUnitControllerDependencies
from deerflow_deep_research.domain.lifecycle import (
    DeepResearchControlResult,
    Durability,
    InfrastructureResultCode,
    InternalCancelDecision,
    LifecycleAction,
    LifecycleStatus,
    ResultCode,
    WorkUnitStorageReason,
)
from deerflow_deep_research.domain.node_spec import NodeBuildDependencies, PolicyRef
from deerflow_deep_research.domain.state import (
    FakeFixturePlan,
    ResearchCheckpoint,
    fixture_plan_to_checkpoint,
    project_lifecycle_status,
)
from deerflow_deep_research.graph.builder import build_research_graph
from deerflow_deep_research.runtime.bootstrap_bundle import BootstrapBundleStore
from deerflow_deep_research.runtime.checkpoint import derive_research_thread_key, resolve_effective_provider
from deerflow_deep_research.runtime.human_input import (
    ConsumedResponseRetry,
    HumanInputError,
    SelectedStartMessage,
    extract_resume_response,
    find_consumed_retry,
    pending_from_snapshot,
    project_suspension,
)
from deerflow_deep_research.runtime.node_agent_bridge import RuntimeNodeAgentBridge
from deerflow_deep_research.runtime.projection import (
    RuntimeWorkUnitDependencyResolver,
    build_node_dependencies,
    project_node_agent,
    project_research_scope,
)
from deerflow_deep_research.runtime.request_bundle import RequestBundleStore
from deerflow_deep_research.runtime.runtime_adapter import TrustedRuntimeEnvelope
from deerflow_deep_research.runtime.work_unit_store import WorkUnitStore

RESEARCH_ID_RE = re.compile(r"^r_[A-Za-z0-9_-]{43}$")


def derive_research_id(*, effective_user_id: str, outer_thread_id: str) -> str:
    payload = json.dumps(
        ["deep-research/thread/v1", effective_user_id, outer_thread_id],
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode()
    return "r_" + base64.urlsafe_b64encode(hashlib.sha256(payload).digest()).decode().rstrip("=")


def digest_request(text: str) -> str:
    payload = json.dumps(["deep-research/request/v1", text], ensure_ascii=False, separators=(",", ":")).encode()
    return "d_" + base64.urlsafe_b64encode(hashlib.sha256(payload).digest()).decode().rstrip("=")


class FakeUnavailableCapabilities:
    async def run_agent(self, *, context, request):
        raise RuntimeError("full_fake_agent_capability_unavailable")


class RuntimeNodeDependencyResolver:
    def __init__(self, graph_context, capabilities: Any | None = None) -> None:
        self._graph_context = graph_context
        self._capabilities = capabilities if capabilities is not None else FakeUnavailableCapabilities()

    def resolve(self, *, logical_name: str, attempt_id: str, policy: PolicyRef) -> NodeBuildDependencies:
        agent_context = project_node_agent(
            self._graph_context,
            node_name=logical_name,
            attempt_id=attempt_id,
            policy_name=policy.name,
        )
        return build_node_dependencies(self._graph_context, agent_context, self._capabilities)


@dataclass(frozen=True)
class ResearchActionInput:
    action: LifecycleAction
    research_id: str
    tool_call_id: str
    messages: tuple[Any, ...]
    start_message: SelectedStartMessage | None = None
    fixture_plan: FakeFixturePlan | None = None


@dataclass(frozen=True)
class ResearchGraphRecipe:
    builder: Any
    requires_work_units: bool = False
    requires_bootstrap_bundle: bool = False
    requires_request_bundle: bool = False
    requires_node_agent_bridge: bool = False
    requires_wave0_worker_bridge: bool = False
    requires_wave1_worker_bridge: bool = False
    work_unit_store_factory: Any = None
    request_bundle_store_factory: Any = None
    node_agent_bridge_factory: Any = None

    @classmethod
    def create(
        cls,
        *,
        work_unit_store_factory: Any = None,
        request_bundle_store_factory: Any = None,
        node_agent_bridge_factory: Any = None,
        implementation_modes: Mapping[str, str] | None = None,
    ) -> ResearchGraphRecipe:
        modes = dict(implementation_modes or {})
        hitl1_real = modes.get("hitl1") == "real"
        bootstrap_real = modes.get("bootstrap") == "real"
        topic_planning_real = modes.get("topic_planning") == "real"
        wave0_real = modes.get("wave0") == "real"
        wave1_real = modes.get("wave1") == "real"
        targeted_evidence_real = modes.get("targeted_evidence") == "real"
        if hitl1_real and not bootstrap_real:
            raise ValueError("hitl1_real_requires_bootstrap_real")
        if topic_planning_real and not hitl1_real:
            raise ValueError("topic_planning_real_requires_hitl1_real")
        if wave0_real and not topic_planning_real:
            raise ValueError("wave0_real_requires_topic_planning_real")
        if wave1_real and not (wave0_real and targeted_evidence_real):
            raise ValueError("wave1_real_requires_wave0_and_targeted_evidence_real")
        return cls(
            builder=build_research_graph(implementation_modes=implementation_modes),
            requires_work_units=True,
            requires_bootstrap_bundle=bootstrap_real,
            requires_request_bundle=hitl1_real,
            requires_node_agent_bridge=hitl1_real or topic_planning_real,
            requires_wave0_worker_bridge=wave0_real,
            requires_wave1_worker_bridge=wave1_real,
            work_unit_store_factory=work_unit_store_factory,
            request_bundle_store_factory=request_bundle_store_factory,
            node_agent_bridge_factory=node_agent_bridge_factory,
        )


def _hitl1_node_agent_policy(graph_context: Any) -> ExecutionPolicy:
    """Zero-tool, one-model-call policy for HITL1 brief generation.

    @impl HIN-001
    @impl NOA-001
    @impl NOA-002
    """
    return ExecutionPolicy(
        policy_name="hitl1-structured-brief",
        allowed_tool_names=frozenset(),
        read_roots=(graph_context.workspace_root, graph_context.uploads_root),
        write_roots=(),
        attempt_root=graph_context.workspace_root,
        budget=ExecutionBudget(
            max_model_calls=1,
            max_total_tool_calls=1,
            max_tool_calls_per_response=1,
            max_parallel_tool_calls=1,
            total_token_budget=8_192,
            per_call_output_token_cap=2_048,
            per_tool_result_bytes=1,
            structured_result_bytes=4_096,
            wall_time_seconds=30.0,
        ),
    )


def _build_hitl1_capabilities(envelope: TrustedRuntimeEnvelope, graph_context: Any, factory: Any) -> Any:
    """Construct the shared node-agent bridge for real HITL1 and real topic planning.

    When both hitl1 and topic_planning are real, the same bridge serves both nodes
    under a single zero-tool, one-model-call ExecutionPolicy. The policy is the
    enforcement upper bound; each node's NodeExecutionRequest carries its own
    objective and structured-output schema within that bound.
    """
    policy = _hitl1_node_agent_policy(graph_context)
    bridge_factory = factory or RuntimeNodeAgentBridge
    return bridge_factory(
        envelope=envelope,
        policy=policy,
        tools_resolver=lambda _envelope, _policy: (),
    )


# Web search/fetch tool names a Wave0 source-intake worker may use. Concrete
# provisioning is operator configuration; the bridge resolver intersects this set
# with the tools configured for the deep-research agent. (WAN-002 / WAN-005)
WAVE0_WORKER_TOOL_NAMES = frozenset(
    {"tavily_search", "tavily_extract", "duckduckgo_search", "jina_ai", "firecrawl_scrape"}
)


def _wave0_worker_policy(graph_context: Any) -> ExecutionPolicy:
    """Bounded multi-tool policy for a Wave0 source-intake worker.

    @impl WAN-002
    @impl NOA-001
    @impl NOA-002
    """
    return ExecutionPolicy(
        policy_name="wave0-source-intake",
        allowed_tool_names=WAVE0_WORKER_TOOL_NAMES,
        read_roots=(graph_context.workspace_root, graph_context.uploads_root),
        write_roots=(graph_context.workspace_root,),
        attempt_root=graph_context.workspace_root,
        budget=ExecutionBudget(
            max_model_calls=3,
            max_total_tool_calls=12,
            max_tool_calls_per_response=4,
            max_parallel_tool_calls=2,
            total_token_budget=24_576,
            per_call_output_token_cap=4_096,
            per_tool_result_bytes=131_072,
            structured_result_bytes=8_192,
            wall_time_seconds=120.0,
        ),
    )


def _build_wave0_capabilities(envelope: TrustedRuntimeEnvelope, graph_context: Any, factory: Any) -> Any:
    """Construct the Wave0 worker node-agent bridge with real web tools.

    Unlike the HITL1/topic-planning bridge, this uses the default tools resolver
    so the worker receives configured web search/fetch tools filtered by the
    policy. Per-attempt isolation of controller artifacts is enforced by the
    attempt-scoped artifact writer; fetched content is untrusted data.
    """
    policy = _wave0_worker_policy(graph_context)
    bridge_factory = factory or RuntimeNodeAgentBridge
    return bridge_factory(envelope=envelope, policy=policy)


WAVE1_WORKER_TOOL_NAMES = frozenset(
    {"tavily_search", "tavily_extract", "duckduckgo_search", "jina_ai", "firecrawl_scrape"}
)


def _wave1_worker_policy(graph_context: Any) -> ExecutionPolicy:
    """Bounded multi-tool policy for a Wave1 evidence extraction worker."""
    return ExecutionPolicy(
        policy_name="wave1-evidence-extraction",
        allowed_tool_names=WAVE1_WORKER_TOOL_NAMES,
        read_roots=(graph_context.workspace_root, graph_context.uploads_root),
        write_roots=(graph_context.workspace_root,),
        attempt_root=graph_context.workspace_root,
        budget=ExecutionBudget(
            max_model_calls=3,
            max_total_tool_calls=20,
            max_tool_calls_per_response=5,
            max_parallel_tool_calls=2,
            total_token_budget=32_768,
            per_call_output_token_cap=8_192,
            per_tool_result_bytes=131_072,
            structured_result_bytes=16_384,
            wall_time_seconds=180.0,
        ),
    )


def _build_wave1_capabilities(envelope: TrustedRuntimeEnvelope, graph_context: Any, factory: Any) -> Any:
    policy = _wave1_worker_policy(graph_context)
    bridge_factory = factory or RuntimeNodeAgentBridge
    return bridge_factory(envelope=envelope, policy=policy)


def _durability(envelope: TrustedRuntimeEnvelope) -> Durability:
    return Durability(resolve_effective_provider(envelope.app_config).durability)


def _checkpoint(snapshot: Any) -> ResearchCheckpoint:
    if not snapshot or not snapshot.values:
        raise HumanInputError("research_not_found", "research checkpoint does not exist")
    try:
        return ResearchCheckpoint(**dict(snapshot.values))
    except (TypeError, ValueError) as exc:
        message = str(exc)
        code = (
            "schema_unsupported"
            if "schema_unsupported" in message or "schema_version" in message
            else "checkpoint_inconsistent"
        )
        raise HumanInputError(code, "research checkpoint is invalid") from exc


def _result_from_snapshot(
    *,
    action: LifecycleAction,
    snapshot: Any,
    envelope: TrustedRuntimeEnvelope,
    code: ResultCode | None = None,
) -> tuple[DeepResearchControlResult, Any]:
    checkpoint = _checkpoint(snapshot)
    pending = pending_from_snapshot(snapshot)
    status = project_lifecycle_status(checkpoint)
    if status is LifecycleStatus.SUSPENDED and pending is None:
        raise HumanInputError("checkpoint_inconsistent", "suspended lifecycle has no pending interrupt")
    if status is not LifecycleStatus.SUSPENDED and pending is not None:
        raise HumanInputError("checkpoint_inconsistent", "terminal lifecycle still has a pending interrupt")
    resolved_code = code or ResultCode(status.value)
    result = DeepResearchControlResult(
        action=action,
        code=resolved_code,
        durability=_durability(envelope),
        research_id=checkpoint.research_id,
        status=status,
        phase=checkpoint.phase,
        generation=checkpoint.generation,
        request_id=pending.request.request_id if pending is not None else None,
        terminal_reason=checkpoint.terminal_reason,
    )
    return result, pending


def _project_action_result(
    *,
    action_input: ResearchActionInput,
    snapshot: Any,
    envelope: TrustedRuntimeEnvelope,
    status_read: bool = False,
) -> dict[str, Any] | Command:
    code = ResultCode.STATUS_OK if status_read else None
    result, pending = _result_from_snapshot(action=action_input.action, snapshot=snapshot, envelope=envelope, code=code)
    if pending is not None and not status_read:
        return project_suspension(pending=pending, result=result, tool_call_id=action_input.tool_call_id)
    return result.model_dump(mode="json", exclude_none=True)


def denial_result(
    *,
    action: LifecycleAction,
    code: ResultCode | InfrastructureResultCode,
    research_id: str | None = None,
    durability: Durability = Durability.UNAVAILABLE,
    infrastructure_reason: WorkUnitStorageReason | None = None,
) -> dict[str, Any]:
    return DeepResearchControlResult(
        action=action,
        code=code,
        durability=durability,
        research_id=research_id,
        infrastructure_reason=infrastructure_reason,
    ).model_dump(mode="json", exclude_none=True)


class ResearchActionHandler:
    def __init__(self, action: LifecycleAction, recipe: ResearchGraphRecipe) -> None:
        self.action = action.value
        self._lifecycle_action = action
        self._recipe = recipe

    def build_graph(self) -> Any:
        return self._recipe.builder

    def derive_namespace(self, envelope: TrustedRuntimeEnvelope, action_input: ResearchActionInput) -> str:
        return derive_research_thread_key(
            effective_user_id=envelope.effective_user_id,
            outer_thread_id=envelope.outer_thread_id,
            research_id=action_input.research_id,
        )

    async def _context(
        self,
        envelope: TrustedRuntimeEnvelope,
        research_id: str,
        *,
        include_work_units: bool = True,
    ) -> GraphInvocationContext:
        graph_context = project_research_scope(envelope, research_scope_id=research_id)
        capabilities = (
            _build_hitl1_capabilities(envelope, graph_context, self._recipe.node_agent_bridge_factory)
            if include_work_units and self._recipe.requires_node_agent_bridge
            else None
        )
        wave0_capabilities = (
            _build_wave0_capabilities(envelope, graph_context, self._recipe.node_agent_bridge_factory)
            if include_work_units and self._recipe.requires_wave0_worker_bridge
            else None
        )
        wave1_capabilities = (
            _build_wave1_capabilities(envelope, graph_context, self._recipe.node_agent_bridge_factory)
            if include_work_units and self._recipe.requires_wave1_worker_bridge
            else wave0_capabilities  # fall back to wave0 capabilities (same tool set)
        )
        base_resolver = RuntimeNodeDependencyResolver(graph_context, capabilities)
        worker_caps = wave1_capabilities or wave0_capabilities
        worker_resolver = RuntimeNodeDependencyResolver(graph_context, worker_caps)
        work_units = None
        bootstrap_bundle = None
        request_bundle = None
        if include_work_units and self._recipe.requires_work_units:
            store_factory = self._recipe.work_unit_store_factory or WorkUnitStore.create
            store = await store_factory(envelope, research_id=research_id)
            work_units = WorkUnitControllerDependencies(
                store=store,
                resolver=RuntimeWorkUnitDependencyResolver(graph_context, worker_resolver, store),
            )
            if self._recipe.requires_bootstrap_bundle:
                bootstrap_bundle = await BootstrapBundleStore.create(envelope, research_id=research_id)
            if self._recipe.requires_request_bundle:
                request_factory = self._recipe.request_bundle_store_factory or RequestBundleStore.create
                request_bundle = await request_factory(envelope, research_id=research_id)
        return GraphInvocationContext(
            graph_context=graph_context,
            dependency_resolver=base_resolver,
            work_units=work_units,
            bootstrap_bundle=bootstrap_bundle,
            request_bundle=request_bundle,
        )


class StartResearchHandler(ResearchActionHandler):
    def __init__(self, recipe: ResearchGraphRecipe) -> None:
        super().__init__(LifecycleAction.START, recipe)

    async def execute(self, graph, *, config, envelope, action_input: ResearchActionInput):
        if action_input.start_message is None:
            return denial_result(action=LifecycleAction.START, code=ResultCode.START_MESSAGE_INVALID)
        snapshot = await graph.aget_state(config)
        request_digest = digest_request(action_input.start_message.text)
        if snapshot and snapshot.values:
            try:
                checkpoint = _checkpoint(snapshot)
            except HumanInputError as exc:
                return denial_result(
                    action=LifecycleAction.START,
                    code=ResultCode(exc.code),
                    research_id=action_input.research_id,
                    durability=_durability(envelope),
                )
            if (
                checkpoint.start_message_id != action_input.start_message.message_id
                or checkpoint.request_digest != request_digest
            ):
                result, _pending = _result_from_snapshot(
                    action=LifecycleAction.START,
                    snapshot=snapshot,
                    envelope=envelope,
                    code=ResultCode.THREAD_RESEARCH_EXISTS,
                )
                return result.model_dump(mode="json", exclude_none=True)
            return _project_action_result(action_input=action_input, snapshot=snapshot, envelope=envelope)

        initial = ResearchCheckpoint(
            research_id=action_input.research_id,
            outer_thread_id=envelope.outer_thread_id,
            start_message_id=action_input.start_message.message_id,
            request_digest=request_digest,
            request_text=action_input.start_message.text,
            fixture_plan=action_input.fixture_plan or FakeFixturePlan(),
        )
        values = asdict(initial)
        values["fixture_plan"] = fixture_plan_to_checkpoint(initial.fixture_plan)
        values["phase"] = initial.phase.value
        values["phase_status"] = initial.phase_status.value
        values["waiting_for"] = initial.waiting_for
        values["terminal_status"] = initial.terminal_status.value if initial.terminal_status is not None else None
        values["terminal_reason"] = initial.terminal_reason.value if initial.terminal_reason is not None else None
        await graph.ainvoke(values, config=config, context=await self._context(envelope, action_input.research_id))
        return _project_action_result(
            action_input=action_input,
            snapshot=await graph.aget_state(config),
            envelope=envelope,
        )


class ResumeResearchHandler(ResearchActionHandler):
    def __init__(self, recipe: ResearchGraphRecipe) -> None:
        super().__init__(LifecycleAction.RESUME, recipe)

    async def execute(self, graph, *, config, envelope, action_input: ResearchActionInput):
        snapshot = await graph.aget_state(config)
        try:
            checkpoint = _checkpoint(snapshot)
            retry = find_consumed_retry(
                action_input.messages,
                consumed_request_ids=checkpoint.consumed_request_ids,
                consumed_message_ids=checkpoint.consumed_message_ids,
            )
            if isinstance(retry, ConsumedResponseRetry):
                return _project_action_result(action_input=action_input, snapshot=snapshot, envelope=envelope)
            pending = pending_from_snapshot(snapshot)
            if pending is None:
                return denial_result(
                    action=LifecycleAction.RESUME,
                    code=ResultCode.INVALID_TRANSITION,
                    research_id=action_input.research_id,
                    durability=_durability(envelope),
                )
            response = extract_resume_response(
                action_input.messages,
                pending,
                consumed_request_ids=checkpoint.consumed_request_ids,
                consumed_message_ids=checkpoint.consumed_message_ids,
            )
        except HumanInputError as exc:
            code = ResultCode(exc.code)
            return denial_result(
                action=LifecycleAction.RESUME,
                code=code,
                research_id=None if code is ResultCode.RESEARCH_NOT_FOUND else action_input.research_id,
                durability=_durability(envelope),
            )
        await graph.ainvoke(
            Command(resume=response.model_dump(mode="json")),
            config=config,
            context=await self._context(envelope, action_input.research_id),
        )
        return _project_action_result(
            action_input=action_input,
            snapshot=await graph.aget_state(config),
            envelope=envelope,
        )


class StatusResearchHandler(ResearchActionHandler):
    def __init__(self, recipe: ResearchGraphRecipe) -> None:
        super().__init__(LifecycleAction.STATUS, recipe)

    async def execute(self, graph, *, config, envelope, action_input: ResearchActionInput):
        snapshot = await graph.aget_state(config)
        if not snapshot or not snapshot.values:
            return denial_result(action=LifecycleAction.STATUS, code=ResultCode.RESEARCH_NOT_FOUND)
        try:
            return _project_action_result(
                action_input=action_input,
                snapshot=snapshot,
                envelope=envelope,
                status_read=True,
            )
        except HumanInputError as exc:
            return denial_result(
                action=LifecycleAction.STATUS,
                code=ResultCode(exc.code),
                durability=_durability(envelope),
            )


class CancelResearchHandler(ResearchActionHandler):
    def __init__(self, recipe: ResearchGraphRecipe) -> None:
        super().__init__(LifecycleAction.CANCEL, recipe)

    async def execute(self, graph, *, config, envelope, action_input: ResearchActionInput):
        snapshot = await graph.aget_state(config)
        try:
            checkpoint = _checkpoint(snapshot)
            if project_lifecycle_status(checkpoint) in {
                LifecycleStatus.COMPLETED,
                LifecycleStatus.STOPPED,
                LifecycleStatus.CANCELLED,
                LifecycleStatus.BLOCKED,
            }:
                return _project_action_result(action_input=action_input, snapshot=snapshot, envelope=envelope)
            pending = pending_from_snapshot(snapshot)
            if pending is None:
                return denial_result(
                    action=LifecycleAction.CANCEL,
                    code=ResultCode.INVALID_TRANSITION,
                    research_id=action_input.research_id,
                    durability=_durability(envelope),
                )
        except HumanInputError as exc:
            return denial_result(
                action=LifecycleAction.CANCEL,
                code=ResultCode(exc.code),
                durability=_durability(envelope),
            )
        await graph.ainvoke(
            Command(resume=InternalCancelDecision().model_dump(mode="json")),
            config=config,
            context=await self._context(envelope, action_input.research_id, include_work_units=False),
        )
        return _project_action_result(
            action_input=action_input,
            snapshot=await graph.aget_state(config),
            envelope=envelope,
        )


def build_research_handlers(recipe: ResearchGraphRecipe | None = None) -> tuple[ResearchActionHandler, ...]:
    recipe = recipe or ResearchGraphRecipe.create()
    return (
        StartResearchHandler(recipe),
        ResumeResearchHandler(recipe),
        StatusResearchHandler(recipe),
        CancelResearchHandler(recipe),
    )


__all__ = [
    "ResearchActionInput",
    "ResearchGraphRecipe",
    "RuntimeNodeDependencyResolver",
    "build_research_handlers",
    "denial_result",
    "derive_research_id",
    "digest_request",
]
