"""@impl GAK-001, GAK-003 — Gate domain types and sole-writer authority tests."""

from __future__ import annotations

import pytest

from deerflow_deep_research.domain.failure_codes import FailureCode
from deerflow_deep_research.domain.gate import (
    Failure,
    GateDefinition,
    GateResult,
    GateRule,
    PhaseVerdict,
)
from deerflow_deep_research.domain.lifecycle import GateVerdict as BranchGateVerdict
from deerflow_deep_research.domain.state import (
    AUTHORITY_WRITERS,
    GATED_FIELDS,
    WriterRole,
    apply_research_update,
)

# ---------------------------------------------------------------------------
# 7.2 — GateDefinition construction validation
# ---------------------------------------------------------------------------


class TestGateDefinitionConstruction:
    def test_valid_route_map_accepted(self) -> None:
        gate_def = GateDefinition(
            phase="wave0",
            rules=(GateRule("r", lambda s: None, FailureCode.WORK_FAILED),),
            route_map={PhaseVerdict.PASS: "pass", PhaseVerdict.REPAIR: "repair", PhaseVerdict.BLOCKED: "exhausted"},
        )
        assert gate_def.resolve_route(PhaseVerdict.PASS, ()) == "pass"

    def test_missing_verdict_key_rejected(self) -> None:
        with pytest.raises((ValueError, KeyError)):
            # route_map missing BLOCKED — but BLOCKED is reachable if a hard rule exists
            GateDefinition(
                phase="wave0",
                rules=(
                    GateRule("r", lambda s: Failure(FailureCode.MISSING_WORK_SPEC, "r"), FailureCode.MISSING_WORK_SPEC),
                ),
                route_map={PhaseVerdict.PASS: "pass", PhaseVerdict.REPAIR: "repair"},
            ).resolve_route(PhaseVerdict.BLOCKED, ())

    def test_unknown_route_label_rejected(self) -> None:
        with pytest.raises(ValueError, match="unknown route label"):
            GateDefinition(
                phase="wave0",
                rules=(GateRule("r", lambda s: None, FailureCode.WORK_FAILED),),
                route_map={PhaseVerdict.PASS: "unknown_edge"},
            )

    def test_empty_rules_rejected(self) -> None:
        with pytest.raises(ValueError, match="at least one rule"):
            GateDefinition(phase="wave0", rules=(), route_map={PhaseVerdict.PASS: "pass"})

    def test_budget_out_of_range_rejected(self) -> None:
        with pytest.raises(ValueError, match="default_budget"):
            GateDefinition(
                phase="wave0",
                rules=(GateRule("r", lambda s: None, FailureCode.WORK_FAILED),),
                default_budget=11,
                route_map={PhaseVerdict.PASS: "pass"},
            )

    def test_route_resolver_accepted(self) -> None:
        gate_def = GateDefinition(
            phase="readiness",
            rules=(GateRule("r", lambda s: None, FailureCode.REPAIR_TARGETED),),
            route_resolver=lambda v, f: "repair_targeted" if v is PhaseVerdict.REPAIR else "pass",
        )
        assert gate_def.resolve_route(PhaseVerdict.REPAIR, ()) == "repair_targeted"


# ---------------------------------------------------------------------------
# 7.3 — PhaseVerdict vs GateVerdict distinctness
# ---------------------------------------------------------------------------


class TestPhaseVerdictDistinct:
    def test_phase_verdict_has_more_values(self) -> None:
        assert len(PhaseVerdict) > len(BranchGateVerdict)
        assert PhaseVerdict.BLOCKED.value == "blocked"
        assert PhaseVerdict.NEEDS_HUMAN.value == "needs_human"
        assert BranchGateVerdict.PASS.value == PhaseVerdict.PASS.value == "pass"

    def test_no_value_collision_confusion(self) -> None:
        """PhaseVerdict and GateVerdict share 'pass'/'repair' values but are distinct types."""
        pv = PhaseVerdict.REPAIR
        bv = BranchGateVerdict.REPAIR
        assert pv.value == bv.value
        assert not isinstance(bv, PhaseVerdict)
        assert not isinstance(pv, BranchGateVerdict)


# ---------------------------------------------------------------------------
# 10.1-10.4 — Sole-writer authority
# ---------------------------------------------------------------------------


class TestGateSoleWriter:
    def test_gate_writes_accepted(self) -> None:
        update = {
            "route": "pass",
            "latest_gate_feedback": {"phase": "wave0"},
            "gate_attempts_by_phase": {"wave0": 1},
            "repair_budget_by_phase": {"wave0": 3},
        }
        result = apply_research_update({"generation": 0}, update, writer=WriterRole.GATE)
        assert result["route"] == "pass"

    def test_worker_write_rejected(self) -> None:
        update = {"route": "pass"}
        with pytest.raises(ValueError, match="writer_not_authorized"):
            apply_research_update({"generation": 0}, update, writer=WriterRole.WORKER)

    def test_repair_write_rejected(self) -> None:
        update = {"latest_gate_feedback": {}}
        with pytest.raises(ValueError, match="writer_not_authorized"):
            apply_research_update({"generation": 0}, update, writer=WriterRole.REPAIR)

    def test_route_in_gated_fields(self) -> None:
        assert "route" in GATED_FIELDS

    def test_gate_in_authority_writers(self) -> None:
        assert WriterRole.GATE in AUTHORITY_WRITERS

    def test_generation_decrease_rejected(self) -> None:
        with pytest.raises(ValueError, match="generation_decrease"):
            apply_research_update({"generation": 5}, {"generation": 3}, writer=WriterRole.GATE)


# ---------------------------------------------------------------------------
# Failure / GateResult model tests
# ---------------------------------------------------------------------------


class TestFailureModel:
    def test_classification_resolved_from_code(self) -> None:
        f = Failure(code=FailureCode.MISSING_WORK_SPEC, rule_name="test")
        assert f.classification == "hard"

    def test_optional_ref(self) -> None:
        f = Failure(code=FailureCode.WORK_FAILED, rule_name="test", ref="work_1")
        assert f.ref == "work_1"
        f2 = Failure(code=FailureCode.WORK_FAILED, rule_name="test")
        assert f2.ref is None


class TestGateResultModel:
    def test_model_dump_serializable(self) -> None:
        gr = GateResult(phase="wave0", verdict=PhaseVerdict.PASS, route="pass", attempt=1, remaining_budget=3)
        d = gr.model_dump(mode="json")
        assert d["phase"] == "wave0"
        assert d["verdict"] == "pass"
        assert d["route"] == "pass"
        assert isinstance(d["failures"], list)

    def test_inspect_auto_generated(self) -> None:
        gr = GateResult(phase="wave0", verdict=PhaseVerdict.PASS, route="pass")
        assert gr.inspect == "no issues"

    def test_inspect_with_failures(self) -> None:
        f = Failure(code=FailureCode.WORK_FAILED, rule_name="r", description="boom")
        gr = GateResult(
            phase="wave0", verdict=PhaseVerdict.REPAIR, route="repair", failures=(f,), attempt=1, remaining_budget=2
        )
        assert "WORK_FAILED" in gr.inspect.upper() or "work_failed" in gr.inspect

    def test_consecutive_stored(self) -> None:
        gr = GateResult(phase="wave0", verdict=PhaseVerdict.REPAIR, route="repair", consecutive=2)
        assert gr.consecutive == 2
        d = gr.model_dump()
        assert d["consecutive"] == 2

    def test_new_generation_none_on_repair(self) -> None:
        gr = GateResult(phase="wave0", verdict=PhaseVerdict.REPAIR, route="repair", new_generation=None)
        assert gr.new_generation is None
