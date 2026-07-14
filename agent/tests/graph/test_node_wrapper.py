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

from deerflow_deep_research.domain.bootstrap import BootstrapMarker
from deerflow_deep_research.domain.context import GraphContextView, NodeAgentContext
from deerflow_deep_research.domain.invocation import GraphInvocationContext, NodeDependencyResolver
from deerflow_deep_research.domain.node_spec import NodeBuildDependencies
from deerflow_deep_research.domain.state import ResearchState
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


class _Resolver:
    def __init__(self, graph_context: GraphContextView) -> None:
        self._gc = graph_context

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


def _context(store: _FakeStore | None) -> GraphInvocationContext:
    gc = _graph_context()
    return GraphInvocationContext(
        graph_context=gc,
        dependency_resolver=_Resolver(gc),  # type: ignore[arg-type]
        bootstrap_bundle=store,
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
