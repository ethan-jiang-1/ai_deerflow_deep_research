"""Red tests for the graph node wrapper's BOOTSTRAP_BUNDLE attach/forbid logic.

@impl BON-001
@impl BON-002
@impl NOA-001
"""

from __future__ import annotations

from typing import Any

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel

from deerflow_deep_research.domain.bootstrap import BootstrapMarker
from deerflow_deep_research.domain.context import GraphContextView, NodeAgentContext
from deerflow_deep_research.domain.enums import NodePhase
from deerflow_deep_research.domain.invocation import GraphInvocationContext, NodeDependencyResolver
from deerflow_deep_research.domain.node_spec import (
    NodeBuildDependencies,
    NodeCapability,
    NodeContracts,
    NodeSpec,
    PolicyRef,
)
from deerflow_deep_research.domain.profile import ResearchProfile
from deerflow_deep_research.domain.state import ContentRef, ResearchState
from deerflow_deep_research.graph.builder import _node_wrapper, _route
from deerflow_deep_research.graph.nodes.bootstrap import NODE_SPEC as BOOTSTRAP_SPEC

_RID = "r_" + "A" * 43


class _FakeStore:
    def __init__(self) -> None:
        self.establish_calls = 0

    async def establish_bundle(self, marker: BootstrapMarker) -> None:
        self.establish_calls += 1
        self.marker = marker

    async def read_marker(self) -> BootstrapMarker | None:
        return getattr(self, "marker", None)


class _FakeRequestStore:
    def __init__(self) -> None:
        self.write_calls = 0

    async def write_profile(self, profile: ResearchProfile) -> ContentRef:
        self.write_calls += 1
        return ContentRef(
            sandbox_path=f"workspace/deep-research/{_RID}/request/profile.json",
            content_hash="h_" + "A" * 43,
        )


class _Resolver:
    def __init__(self, graph_context: GraphContextView, *, request_bundle: _FakeRequestStore | None = None) -> None:
        self._gc = graph_context
        self._request_bundle = request_bundle

    def resolve(self, *, logical_name: str, attempt_id: str, policy: Any) -> NodeBuildDependencies:
        return NodeBuildDependencies(
            graph_context=self._gc,
            agent_context=NodeAgentContext(
                research_scope_id=self._gc.research_scope_id,
                node_name=logical_name,
                attempt_id=attempt_id,
                workspace_root=self._gc.workspace_root,
                attempt_root=self._gc.workspace_root,
                policy_name=policy.name,
            ),
            capabilities=type("_C", (), {"run_agent": lambda self, *, context, request: None})(),
            request_bundle=self._request_bundle,
        )


# NodeDependencyResolver is a runtime_checkable Protocol; _Resolver satisfies it.
assert isinstance(
    _Resolver(GraphContextView(research_scope_id="r", workspace_root="/x", uploads_root="/u", outputs_root="/o")),
    NodeDependencyResolver,
)


def _graph_context() -> GraphContextView:
    return GraphContextView(
        research_scope_id=_RID,
        workspace_root=f"/mnt/user-data/workspace/deep-research/{_RID}",
        uploads_root="/mnt/user-data/uploads",
        outputs_root=f"/mnt/user-data/outputs/deep-research/{_RID}",
    )


def _context(
    store: _FakeStore | None,
    *,
    request_bundle: _FakeRequestStore | None = None,
    resolver_request_bundle: _FakeRequestStore | None = None,
) -> GraphInvocationContext:
    gc = _graph_context()
    return GraphInvocationContext(
        graph_context=gc,
        dependency_resolver=_Resolver(gc, request_bundle=resolver_request_bundle),  # type: ignore[arg-type]
        bootstrap_bundle=store,
        request_bundle=request_bundle,
    )


def _state() -> dict[str, Any]:
    return {
        "schema_version": 2,
        "research_id": _RID,
        "outer_thread_id": "thread-1",
        "start_message_id": "human-start",
        "request_digest": "d_" + "B" * 43,
        "request_text": "question",
        "fixture_plan": {"bootstrap": ("needs_input",)},
        "phase": "bootstrap",
        "generation": 0,
        "execution_trace": (),
    }


def _compile(mode: str):
    factory = BOOTSTRAP_SPEC.real_factory if mode == "real" else BOOTSTRAP_SPEC.fake_factory
    builder = StateGraph(ResearchState, context_schema=GraphInvocationContext)
    builder.add_node("bootstrap", _node_wrapper("bootstrap", BOOTSTRAP_SPEC, factory, {}))
    builder.add_edge(START, "bootstrap")
    builder.add_conditional_edges("bootstrap", _route, {"needs_input": END, "profile_complete": END, "exhausted": END})
    return builder.compile(checkpointer=InMemorySaver())


def _config() -> dict:
    return {"configurable": {"thread_id": "t1"}}


class _Req(BaseModel):
    pass


class _Res(BaseModel):
    pass


def _request_bundle_spec(*, declares: bool, seen: list[object]) -> NodeSpec:
    def real_factory(dependencies: NodeBuildDependencies):
        seen.append(dependencies.request_bundle)

        def run(_state: ResearchState) -> dict[str, str]:
            return {"route": "accepted"}

        return run

    def fake_factory(dependencies: NodeBuildDependencies):
        seen.append(dependencies.request_bundle)

        def run(_state: ResearchState) -> dict[str, str]:
            return {"route": "accepted"}

        return run

    return NodeSpec(
        logical_name="hitl1",
        phase=NodePhase.ORCHESTRATION,
        policy=PolicyRef(name="hitl1-profile", version="v1"),
        contracts=NodeContracts(request_type=_Req, result_type=_Res),
        real_factory=real_factory,
        fake_factory=fake_factory,
        capabilities=frozenset({NodeCapability.REQUEST_BUNDLE}) if declares else frozenset(),
    )


def _compile_custom(spec: NodeSpec, mode: str):
    factory = spec.real_factory if mode == "real" else spec.fake_factory
    builder = StateGraph(ResearchState, context_schema=GraphInvocationContext)
    builder.add_node("hitl1", _node_wrapper("hitl1", spec, factory, {}))
    builder.add_edge(START, "hitl1")
    builder.add_conditional_edges("hitl1", _route, {"accepted": END})
    return builder.compile(checkpointer=InMemorySaver())


class TestWrapperBootstrapBundleAttach:
    async def test_real_factory_with_store_attaches_and_routes(self) -> None:
        store = _FakeStore()
        graph = _compile("real")
        await graph.ainvoke(_state(), config=_config(), context=_context(store))
        assert store.establish_calls == 1

    async def test_real_factory_without_store_fails_before_factory(self) -> None:
        graph = _compile("real")
        with pytest.raises(ValueError, match="bootstrap_bundle_capability_missing"):
            await graph.ainvoke(_state(), config=_config(), context=_context(None))

    async def test_fake_factory_without_store_runs_and_does_not_touch_store(self) -> None:
        graph = _compile("fake")
        store = _FakeStore()  # present on context but fake factory must not use it
        await graph.ainvoke(_state(), config=_config(), context=_context(store))
        assert store.establish_calls == 0


class TestWrapperRequestBundleAttach:
    async def test_real_declaring_factory_gets_request_bundle(self) -> None:
        seen: list[object] = []
        spec = _request_bundle_spec(declares=True, seen=seen)
        request_store = _FakeRequestStore()
        graph = _compile_custom(spec, "real")
        await graph.ainvoke(_state(), config=_config(), context=_context(None, request_bundle=request_store))
        assert seen == [request_store]

    async def test_real_declaring_factory_without_request_bundle_fails_before_factory(self) -> None:
        seen: list[object] = []
        spec = _request_bundle_spec(declares=True, seen=seen)
        graph = _compile_custom(spec, "real")
        with pytest.raises(ValueError, match="request_bundle_capability_missing"):
            await graph.ainvoke(_state(), config=_config(), context=_context(None))
        assert seen == []

    async def test_fake_declaring_factory_does_not_receive_request_bundle(self) -> None:
        seen: list[object] = []
        spec = _request_bundle_spec(declares=True, seen=seen)
        graph = _compile_custom(spec, "fake")
        await graph.ainvoke(_state(), config=_config(), context=_context(None, request_bundle=_FakeRequestStore()))
        assert seen == [None]

    async def test_dependency_request_bundle_without_declaration_fails(self) -> None:
        seen: list[object] = []
        spec = _request_bundle_spec(declares=False, seen=seen)
        graph = _compile_custom(spec, "real")
        with pytest.raises(ValueError, match="request_bundle_capability_undeclared"):
            await graph.ainvoke(
                _state(),
                config=_config(),
                context=_context(None, resolver_request_bundle=_FakeRequestStore()),
            )
        assert seen == []
