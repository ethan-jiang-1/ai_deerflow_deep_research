"""Red tests for the real bootstrap node factory.

@impl BON-002
@impl BON-003
"""

from __future__ import annotations

from typing import Any

import pytest

from deerflow_deep_research.domain.bootstrap import BootstrapMarker
from deerflow_deep_research.domain.context import GraphContextView, NodeAgentContext
from deerflow_deep_research.domain.lifecycle import LifecycleStatus, TerminalReason
from deerflow_deep_research.domain.node_spec import NodeBuildDependencies
from deerflow_deep_research.domain.state import PhaseStatus
from deerflow_deep_research.graph.nodes.bootstrap.node import build_real

_RID = "r_" + "a" * 43
_DIGEST = "d_" + "b" * 43
_MID = "human-start"


def _marker(
    *,
    research_id: str = _RID,
    start_message_id: str = _MID,
    request_digest: str = _DIGEST,
    state_schema_version: int = 2,
) -> BootstrapMarker:
    return BootstrapMarker(
        research_id=research_id,
        start_message_id=start_message_id,
        request_digest=request_digest,
        state_schema_version=state_schema_version,
    )


class _FakeStore:
    """Controllable bootstrap store: records establish, returns a configured read-back."""

    def __init__(self, *, read_back: BootstrapMarker | None | str = "same") -> None:
        # "same" -> return the marker that was established; otherwise return the literal.
        self._read_back = read_back
        self.established: BootstrapMarker | None = None
        self.establish_calls = 0

    async def establish_bundle(self, marker: BootstrapMarker) -> None:
        self.established = marker
        self.establish_calls += 1

    async def read_marker(self) -> BootstrapMarker | None:
        if self._read_back == "same":
            return self.established
        return self._read_back  # type: ignore[return-value]


def _deps(store: _FakeStore) -> NodeBuildDependencies:
    ctx = GraphContextView(
        research_scope_id="r_test",
        workspace_root=f"/mnt/user-data/workspace/deep-research/{_RID}",
        uploads_root="/mnt/user-data/uploads",
        outputs_root="/mnt/user-data/outputs",
    )
    agent_ctx = NodeAgentContext(
        research_scope_id="r_test",
        node_name="bootstrap",
        attempt_id="g0_bootstrap_a01",
        workspace_root=ctx.workspace_root,
        attempt_root=ctx.workspace_root,
        policy_name="skeleton-bootstrap",
    )

    class _Caps:
        async def run_agent(self, *, context: object, request: object) -> object: ...

    return NodeBuildDependencies(
        graph_context=ctx,
        agent_context=agent_ctx,
        capabilities=_Caps(),
        bootstrap_bundle=store,
    )


def _state(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "research_id": _RID,
        "start_message_id": _MID,
        "request_digest": _DIGEST,
        "schema_version": 2,
        "fixture_plan": {"bootstrap": ("profile_complete",)},  # must be ignored by real node
    }
    base.update(overrides)
    return base


class TestBuildRealRoutesOnBinding:
    async def test_bound_marker_routes_needs_input_with_no_model_call(self) -> None:
        store = _FakeStore()
        run = build_real(_deps(store))
        result = await run(_state())
        assert result["route"] == "needs_input"
        assert result["phase"] == "bootstrap"
        assert store.establish_calls == 1
        assert store.established == _marker()

    async def test_fixture_plan_is_ignored_for_route(self) -> None:
        # fixture_plan says profile_complete, but the real node routes from the binding.
        store = _FakeStore()
        run = build_real(_deps(store))
        result = await run(_state(fixture_plan={"bootstrap": ("profile_complete",)}))
        assert result["route"] == "needs_input"

    async def test_divergent_read_back_fails_closed_terminal(self) -> None:
        store = _FakeStore(read_back=_marker(research_id="r_" + "z" * 43))
        run = build_real(_deps(store))
        result = await run(_state())
        assert result["route"] == "exhausted"
        assert result["phase_status"] == PhaseStatus.TERMINAL.value
        assert result["terminal_status"] == LifecycleStatus.BLOCKED.value
        assert result["terminal_reason"] == TerminalReason.GATE_BLOCKED.value

    async def test_missing_read_back_fails_closed_terminal(self) -> None:
        store = _FakeStore(read_back=None)
        run = build_real(_deps(store))
        result = await run(_state())
        assert result["route"] == "exhausted"
        assert result["terminal_status"] == LifecycleStatus.BLOCKED.value

    async def test_state_schema_version_mismatch_fails_closed(self) -> None:
        store = _FakeStore(read_back=_marker(state_schema_version=3))
        run = build_real(_deps(store))
        result = await run(_state(schema_version=2))
        assert result["route"] == "exhausted"
        assert result["terminal_status"] == LifecycleStatus.BLOCKED.value


class TestBuildRealGuards:
    def test_missing_store_raises(self) -> None:
        deps = NodeBuildDependencies(
            graph_context=GraphContextView(
                research_scope_id="r_test",
                workspace_root="/mnt/user-data/workspace/deep-research/x",
                uploads_root="/mnt/user-data/uploads",
                outputs_root="/mnt/user-data/outputs",
            ),
            agent_context=NodeAgentContext(
                research_scope_id="r_test",
                node_name="bootstrap",
                attempt_id="g0_bootstrap_a01",
                workspace_root="/mnt/user-data/workspace/deep-research/x",
                attempt_root="/mnt/user-data/workspace/deep-research/x",
                policy_name="skeleton-bootstrap",
            ),
            capabilities=type("_C", (), {"run_agent": lambda self, *, context, request: None})(),
            bootstrap_bundle=None,
        )
        with pytest.raises(ValueError, match="bootstrap_bundle_capability_missing"):
            build_real(deps)
