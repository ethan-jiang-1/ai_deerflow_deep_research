"""Request-independent Deep Research StateGraph recipe.

@impl REG-001
@impl REG-002
@impl REG-006
@impl GAK-003
@impl GAK-005
"""

from __future__ import annotations

import inspect
from collections.abc import Mapping
from dataclasses import replace
from typing import Any

from langgraph.graph import END, START, StateGraph
from langgraph.runtime import Runtime

from deerflow_deep_research.domain.gate import GateDefinition
from deerflow_deep_research.domain.invocation import GraphInvocationContext
from deerflow_deep_research.domain.lifecycle import make_attempt_id
from deerflow_deep_research.domain.node_spec import NodeCapability, NodeSpec
from deerflow_deep_research.domain.state import WORK_UNIT_GATE_PREVIEW_FIELDS, ResearchState, preview_work_unit_update
from deerflow_deep_research.domain.work_units import (
    WORK_UNIT_GATE_VIEW_KEY,
    WorkUnitGateView,
    validate_wrapper_gate_view,
)
from deerflow_deep_research.graph.implementation_map import resolve_implementations
from deerflow_deep_research.graph.nodes.gate_adapter import (
    default_gate_defs,
    evaluate_gate_for_node,
)
from deerflow_deep_research.graph.registry import load_research_node_specs
from deerflow_deep_research.graph.topology import LOGICAL_NODES


def _node_wrapper(
    logical_name: str,
    spec: NodeSpec,
    factory,
    gate_defs: Mapping[str, GateDefinition],
):
    async def run(state: ResearchState, runtime: Runtime[GraphInvocationContext]) -> dict[str, Any]:
        context = runtime.context
        current_attempt = make_attempt_id(state, logical_name)
        dependencies = context.dependency_resolver.resolve(
            logical_name=logical_name,
            attempt_id=current_attempt,
            policy=spec.policy,
        )
        declares_work_units = NodeCapability.WORK_UNIT_CONTROLLER in spec.capabilities
        if declares_work_units and context.work_units is None:
            raise ValueError("work_unit_capability_missing")
        if not declares_work_units and dependencies.work_units is not None:
            raise ValueError("work_unit_capability_undeclared")
        if declares_work_units:
            dependencies = replace(dependencies, work_units=context.work_units)
        declares_bootstrap = NodeCapability.BOOTSTRAP_BUNDLE in spec.capabilities
        if declares_bootstrap and factory is spec.real_factory:
            # The bootstrap store is a real-factory filesystem capability; the fake
            # factory is zero-IO (REG-002) and does not consume it, so it is attached
            # only when the real factory is selected.
            if context.bootstrap_bundle is None:
                raise ValueError("bootstrap_bundle_capability_missing")
            dependencies = replace(dependencies, bootstrap_bundle=context.bootstrap_bundle)
        elif dependencies.bootstrap_bundle is not None:
            raise ValueError("bootstrap_bundle_capability_undeclared")
        if dependencies.graph_context != context.graph_context:
            raise ValueError("dependency_context_mismatch")
        if dependencies.agent_context.node_name != logical_name:
            raise ValueError("dependency_node_mismatch")
        if dependencies.agent_context.attempt_id != current_attempt:
            raise ValueError("dependency_attempt_mismatch")
        node = factory(dependencies)
        result = node(state)
        result = await result if inspect.isawaitable(result) else result
        result = dict(result)

        gate_view = result.pop(WORK_UNIT_GATE_VIEW_KEY, None)
        if declares_work_units:
            if not isinstance(gate_view, WorkUnitGateView):
                raise ValueError("work_unit_gate_view_inconsistent")
        elif gate_view is not None:
            raise ValueError("work_unit_gate_view_undeclared")

        # Gate evaluation — delegated to nodes layer (architecture: graph → nodes → engine)
        gate_def = gate_defs.get(logical_name)
        if gate_def is not None:
            gate_state: Mapping[str, Any] = state
            if declares_work_units:
                preview_delta = {key: value for key, value in result.items() if key in WORK_UNIT_GATE_PREVIEW_FIELDS}
                gate_state = preview_work_unit_update(state, preview_delta)
                assert gate_view is not None
                validate_wrapper_gate_view(gate_view, gate_state, phase=logical_name)
                gate_state = {**gate_state, WORK_UNIT_GATE_VIEW_KEY: gate_view}
            gate_update = evaluate_gate_for_node(gate_state, logical_name, gate_def)
            overlap = set(result) & set(gate_update)
            if overlap:
                raise ValueError(f"node_gate_write_conflict:{','.join(sorted(overlap))}")
            result = {**result, **gate_update}

        return result

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
    gate_defs: Mapping[str, GateDefinition] | None = None,
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

    _gate_defs: Mapping[str, GateDefinition] = gate_defs if gate_defs is not None else default_gate_defs()

    builder = StateGraph(ResearchState, context_schema=GraphInvocationContext)
    for logical_name in LOGICAL_NODES:
        builder.add_node(
            logical_name,
            _node_wrapper(logical_name, loaded[logical_name], factories[logical_name], _gate_defs),
        )

    builder.add_edge(START, "bootstrap")
    builder.add_conditional_edges(
        "bootstrap",
        _route,
        {"needs_input": "hitl1", "profile_complete": "topic_planning", "exhausted": END},
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
