"""Request-independent Deep Research StateGraph recipe.

@impl REG-001
@impl REG-002
@impl REG-006
"""

from __future__ import annotations

import inspect
from collections.abc import Mapping
from typing import Any

from langgraph.graph import END, START, StateGraph
from langgraph.runtime import Runtime

from deerflow_deep_research.domain.invocation import GraphInvocationContext
from deerflow_deep_research.domain.lifecycle import make_attempt_id
from deerflow_deep_research.domain.node_spec import NodeSpec
from deerflow_deep_research.domain.state import ResearchState
from deerflow_deep_research.graph.implementation_map import resolve_implementations
from deerflow_deep_research.graph.registry import load_research_node_specs
from deerflow_deep_research.graph.topology import LOGICAL_NODES


def _node_wrapper(logical_name: str, spec: NodeSpec, factory):
    async def run(state: ResearchState, runtime: Runtime[GraphInvocationContext]) -> dict[str, Any]:
        context = runtime.context
        current_attempt = make_attempt_id(state, logical_name)
        dependencies = context.dependency_resolver.resolve(
            logical_name=logical_name,
            attempt_id=current_attempt,
            policy=spec.policy,
        )
        if dependencies.graph_context != context.graph_context:
            raise ValueError("dependency_context_mismatch")
        if dependencies.agent_context.node_name != logical_name:
            raise ValueError("dependency_node_mismatch")
        if dependencies.agent_context.attempt_id != current_attempt:
            raise ValueError("dependency_attempt_mismatch")
        node = factory(dependencies)
        result = node(state)
        return await result if inspect.isawaitable(result) else result

    run.__name__ = f"run_{logical_name}"
    return run


def _route(state: ResearchState) -> str:
    route = state.get("route")
    if not isinstance(route, str):
        raise ValueError("typed_route_missing")
    return route


def build_research_graph(
    *,
    implementation_modes: Mapping[str, str] | None = None,
    spec_overrides: Mapping[str, NodeSpec] | None = None,
) -> StateGraph:
    loaded = dict(load_research_node_specs())
    if spec_overrides:
        unknown = set(spec_overrides) - set(loaded)
        if unknown:
            raise ValueError(f"unknown spec override: {', '.join(sorted(unknown))}")
        loaded.update(spec_overrides)
    if tuple(loaded) != LOGICAL_NODES:
        raise ValueError("research registry order does not match topology")
    modes = dict(implementation_modes or {name: "fake" for name in LOGICAL_NODES})
    factories = resolve_implementations(loaded, modes)

    builder = StateGraph(ResearchState, context_schema=GraphInvocationContext)
    for logical_name in LOGICAL_NODES:
        builder.add_node(logical_name, _node_wrapper(logical_name, loaded[logical_name], factories[logical_name]))

    builder.add_edge(START, "bootstrap")
    builder.add_conditional_edges(
        "bootstrap",
        _route,
        {"needs_input": "hitl1", "profile_complete": "topic_planning"},
    )
    builder.add_conditional_edges("hitl1", _route, {"accepted": "topic_planning", "cancel": END})
    builder.add_edge("topic_planning", "wave0")
    builder.add_conditional_edges("wave0", _route, {"repair": "wave0", "pass": "wave1", "exhausted": END})
    builder.add_conditional_edges(
        "wave1",
        _route,
        {"repair": "wave1", "pass": "wave2_synthesis", "exhausted": END},
    )
    builder.add_conditional_edges(
        "wave2_synthesis",
        _route,
        {"evidence_needed": "targeted_evidence", "pass": "hitl2"},
    )
    builder.add_edge("targeted_evidence", "wave2_synthesis")
    builder.add_conditional_edges(
        "hitl2",
        _route,
        {
            "revise_view": "wave2_synthesis",
            "repair": "targeted_evidence",
            "rerun": "rerun",
            "proceed": "readiness",
            "stop": END,
            "cancel": END,
        },
    )
    builder.add_conditional_edges("rerun", _route, {"next": "topic_planning", "exhausted": END})
    builder.add_conditional_edges(
        "readiness",
        _route,
        {
            "repair_targeted": "targeted_evidence",
            "repair_synthesis": "wave2_synthesis",
            "repair_hitl2": "hitl2",
            "pass": "final_delivery",
            "exhausted": END,
        },
    )
    builder.add_conditional_edges(
        "final_delivery",
        _route,
        {"repair": "final_delivery", "evidence_blocked": "readiness", "pass": END, "exhausted": END},
    )
    return builder


__all__ = ["build_research_graph"]
