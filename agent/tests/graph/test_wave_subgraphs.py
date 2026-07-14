"""Wave fixture recipes reuse the shared work-unit component (REG-002)."""

from __future__ import annotations

from deerflow_deep_research.graph.components.work_units import run_fixture_work_unit_component
from deerflow_deep_research.graph.nodes.wave0 import subgraph as wave0_subgraph
from deerflow_deep_research.graph.nodes.wave1 import subgraph as wave1_subgraph


def test_wave_recipes_use_distinct_three_item_fixture_intents() -> None:
    assert tuple(intent.scope for intent in wave0_subgraph.WAVE0_FIXTURE_INTENTS) == (
        ("wave0:fixture:0",),
        ("wave0:fixture:1",),
        ("wave0:fixture:2",),
    )
    assert tuple(intent.scope for intent in wave1_subgraph.WAVE1_FIXTURE_INTENTS) == (
        ("wave1:fixture:0",),
        ("wave1:fixture:1",),
        ("wave1:fixture:2",),
    )
    assert all(
        intent.required_outputs == ("fixture.json",)
        for intent in (*wave0_subgraph.WAVE0_FIXTURE_INTENTS, *wave1_subgraph.WAVE1_FIXTURE_INTENTS)
    )


def test_both_wave_recipes_delegate_to_the_same_component_submit_path() -> None:
    assert wave0_subgraph.run_fixture_work_unit_component is run_fixture_work_unit_component
    assert wave1_subgraph.run_fixture_work_unit_component is run_fixture_work_unit_component
    forbidden_local_authorities = {
        "StateGraph",
        "WorkUnitStore",
        "validate_submission_candidate",
        "commit_candidate",
    }
    assert not forbidden_local_authorities & set(vars(wave0_subgraph))
    assert not forbidden_local_authorities & set(vars(wave1_subgraph))
