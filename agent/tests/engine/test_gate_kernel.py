"""@impl GAK-001, GAK-004, GAK-006 — Gate evaluation engine tests."""

from __future__ import annotations

from deerflow_deep_research.domain.failure_codes import FailureCode
from deerflow_deep_research.domain.gate import (
    Failure,
    GateDefinition,
    GateResult,
    GateRule,
    PhaseVerdict,
)
from deerflow_deep_research.domain.state import FakeFixturePlan, fixture_plan_to_checkpoint
from deerflow_deep_research.engine.gate_kernel import evaluate_gate, gate_result_to_state_update


def _mk_rule(name: str, code: FailureCode, should_fail: bool = True, ref: str | None = None):
    def evaluate(state):
        if should_fail:
            return Failure(code=code, rule_name=name, description=f"fail: {name}", ref=ref)
        return None

    return GateRule(name=name, evaluate=evaluate, failure_code=code)


def _state(**overrides):
    base = {
        "generation": 0,
        "fixture_plan": {},
        "execution_trace": (),
        "gate_attempts_by_phase": {},
        "repair_budget_by_phase": {},
        "latest_gate_feedback": None,
    }
    return {**base, **overrides}


def _gate_def(phase="wave0", rules=None, default_budget=3, route_map=None):
    if rules is None:
        rules = (_mk_rule("always_pass", FailureCode.WORK_FAILED, should_fail=False),)
    if route_map is None:
        route_map = {PhaseVerdict.PASS: "pass", PhaseVerdict.REPAIR: "repair", PhaseVerdict.BLOCKED: "exhausted"}
    return GateDefinition(phase=phase, rules=rules, default_budget=default_budget, route_map=route_map)


# ---------------------------------------------------------------------------
# 8.1-8.5 — Basic verdict derivation
# ---------------------------------------------------------------------------


class TestBasicVerdicts:
    def test_all_pass(self) -> None:
        result = evaluate_gate(_state(), "wave0", _gate_def())
        assert result.verdict is PhaseVerdict.PASS
        assert result.failures == ()
        assert result.route == "pass"
        assert result.degraded is False

    def test_single_repairable_repair(self) -> None:
        rule = _mk_rule("r", FailureCode.WORK_FAILED)
        gd = _gate_def(rules=(rule,))
        result = evaluate_gate(_state(), "wave0", gd)
        assert result.verdict is PhaseVerdict.REPAIR
        assert len(result.failures) == 1
        assert result.route == "repair"

    def test_hard_failure_blocked(self) -> None:
        rule = _mk_rule("r", FailureCode.IDENTITY_MISMATCH)
        gd = _gate_def(rules=(rule,))
        result = evaluate_gate(_state(), "wave0", gd)
        assert result.verdict is PhaseVerdict.BLOCKED
        assert result.route == "exhausted"

    def test_budget_exhaustion_blocked(self) -> None:
        rule = _mk_rule("r", FailureCode.WORK_FAILED)
        gd = _gate_def(rules=(rule,), default_budget=0)
        result = evaluate_gate(_state(), "wave0", gd)
        assert result.verdict is PhaseVerdict.BLOCKED
        assert any(f.code is FailureCode.REPAIR_BUDGET_EXHAUSTED for f in result.failures)

    def test_degradable_only_pass_degraded(self) -> None:
        rule = _mk_rule("r", FailureCode.UNTRUSTED_SOURCE)
        gd = _gate_def(rules=(rule,))
        result = evaluate_gate(_state(), "wave0", gd)
        assert result.verdict is PhaseVerdict.PASS
        assert result.degraded is True
        assert result.route == "pass"


# ---------------------------------------------------------------------------
# 8.6-8.8 — Collect-all, stability, purity
# ---------------------------------------------------------------------------


class TestCollectAll:
    def test_hard_plus_repairable_collects_both(self) -> None:
        r1 = _mk_rule("r1", FailureCode.IDENTITY_MISMATCH)
        r2 = _mk_rule("r2", FailureCode.WORK_FAILED)
        gd = _gate_def(rules=(r1, r2))
        result = evaluate_gate(_state(), "wave0", gd)
        assert len(result.failures) == 2
        assert result.verdict is PhaseVerdict.BLOCKED


class TestStability:
    def test_same_input_same_output(self) -> None:
        rules = (_mk_rule("r", FailureCode.WORK_FAILED),)
        gd = _gate_def(rules=rules)
        s = _state()
        r1 = evaluate_gate(s, "wave0", gd)
        r2 = evaluate_gate(s, "wave0", gd)
        assert r1.verdict == r2.verdict
        assert r1.fingerprint == r2.fingerprint
        assert r1.route == r2.route

    def test_rule_order_determines_failure_order(self) -> None:
        r1 = _mk_rule("rule_A", FailureCode.WORK_FAILED)
        r2 = _mk_rule("rule_B", FailureCode.WORK_TIMED_OUT)
        gd = _gate_def(rules=(r1, r2))
        result = evaluate_gate(_state(), "wave0", gd)
        assert result.failures[0].rule_name == "rule_A"
        assert result.failures[1].rule_name == "rule_B"


class TestPurity:
    def test_no_state_mutation(self) -> None:
        s = _state(generation=5)
        before = dict(s)
        evaluate_gate(s, "wave0", _gate_def())
        assert dict(s) == before


# ---------------------------------------------------------------------------
# 8.9-8.10 — route_map, lazy budget
# ---------------------------------------------------------------------------


class TestRouteMap:
    def test_blocked_maps_to_exhausted(self) -> None:
        rule = _mk_rule("r", FailureCode.IDENTITY_MISMATCH)
        gd = _gate_def(rules=(rule,))
        result = evaluate_gate(_state(), "wave0", gd)
        assert result.route == "exhausted"


class TestLazyBudget:
    def test_missing_budget_uses_default(self) -> None:
        gd = _gate_def(default_budget=5)
        result = evaluate_gate(_state(), "wave0", gd)
        assert result.remaining_budget == 5  # no decrement on PASS


# ---------------------------------------------------------------------------
# 8.11-8.12 — NEEDS_HUMAN reserved, route_resolver
# ---------------------------------------------------------------------------


class TestNeedsHuman:
    def test_needs_human_exists_but_not_produced(self) -> None:
        assert PhaseVerdict.NEEDS_HUMAN.value == "needs_human"
        gd = _gate_def()
        result = evaluate_gate(_state(), "wave0", gd)
        assert result.verdict is not PhaseVerdict.NEEDS_HUMAN


class TestRouteResolver:
    def test_readiness_repair_targeted(self) -> None:
        plan = FakeFixturePlan(readiness=("repair_targeted", "pass"))
        s = _state(fixture_plan=fixture_plan_to_checkpoint(plan))
        from deerflow_deep_research.engine.gate_fixtures import build_fixture_gate_defs

        gd = build_fixture_gate_defs()["readiness"]
        result = evaluate_gate(s, "readiness", gd)
        assert result.route == "repair_targeted"

    def test_final_delivery_evidence_blocked(self) -> None:
        plan = FakeFixturePlan(final_delivery=("evidence_blocked", "pass"))
        s = _state(fixture_plan=fixture_plan_to_checkpoint(plan))
        from deerflow_deep_research.engine.gate_fixtures import build_fixture_gate_defs

        gd = build_fixture_gate_defs()["final_delivery"]
        result = evaluate_gate(s, "final_delivery", gd)
        assert result.route == "evidence_blocked"


# ---------------------------------------------------------------------------
# 9.1-9.6 — Repair loop and fatigue
# ---------------------------------------------------------------------------


class TestRepairLoop:
    def test_repair_then_pass(self) -> None:
        rule = _mk_rule("r", FailureCode.WORK_FAILED)
        gd = _gate_def(rules=(rule,))
        s = _state()
        r1 = evaluate_gate(s, "wave0", gd)
        assert r1.verdict is PhaseVerdict.REPAIR
        assert r1.attempt == 1
        assert r1.remaining_budget == 2  # 3 - 1

        # Simulate state update after first evaluation
        s2 = _state(
            gate_attempts_by_phase={"wave0": 1},
            repair_budget_by_phase={"wave0": 2},
            latest_gate_feedback=r1.model_dump(),
            generation=0,
        )
        # Replace rule to pass on second attempt
        gd2 = _gate_def(rules=(_mk_rule("always_pass", FailureCode.WORK_FAILED, should_fail=False),))
        r2 = evaluate_gate(s2, "wave0", gd2)
        assert r2.verdict is PhaseVerdict.PASS
        assert r2.attempt == 2
        assert r2.remaining_budget == 2  # unchanged on PASS

    def test_budget_exhaustion_after_n_repairs(self) -> None:
        rule = _mk_rule("r", FailureCode.WORK_FAILED)
        gd = _gate_def(rules=(rule,), default_budget=2)
        s = _state()
        r1 = evaluate_gate(s, "wave0", gd)
        assert r1.verdict is PhaseVerdict.REPAIR
        assert r1.remaining_budget == 1

        s2 = _state(
            gate_attempts_by_phase={"wave0": 1},
            repair_budget_by_phase={"wave0": 1},
            latest_gate_feedback=r1.model_dump(),
        )
        r2 = evaluate_gate(s2, "wave0", gd)
        assert r2.verdict is PhaseVerdict.REPAIR
        assert r2.remaining_budget == 0

        s3 = _state(
            gate_attempts_by_phase={"wave0": 2},
            repair_budget_by_phase={"wave0": 0},
            latest_gate_feedback=r2.model_dump(),
        )
        r3 = evaluate_gate(s3, "wave0", gd)
        assert r3.verdict is PhaseVerdict.BLOCKED


class TestFatigue:
    def test_fatigue_escalation_after_3_same(self) -> None:
        rule = _mk_rule("r", FailureCode.WORK_FAILED)
        gd = _gate_def(rules=(rule,), default_budget=5)  # plenty of budget
        s = _state()

        r1 = evaluate_gate(s, "wave0", gd)
        assert r1.consecutive == 1

        s2 = _state(
            gate_attempts_by_phase={"wave0": 1},
            repair_budget_by_phase={"wave0": 4},
            latest_gate_feedback=r1.model_dump(),
        )
        r2 = evaluate_gate(s2, "wave0", gd)
        assert r2.consecutive == 2

        s3 = _state(
            gate_attempts_by_phase={"wave0": 2},
            repair_budget_by_phase={"wave0": 3},
            latest_gate_feedback=r2.model_dump(),
        )
        r3 = evaluate_gate(s3, "wave0", gd)
        assert r3.verdict is PhaseVerdict.BLOCKED
        assert any(f.code is FailureCode.FATIGUE_ESCALATION for f in r3.failures)

    def test_different_fingerprint_resets(self) -> None:
        r1 = _mk_rule("rule_A", FailureCode.WORK_FAILED)
        gd1 = _gate_def(rules=(r1,), default_budget=5)
        s = _state()
        res1 = evaluate_gate(s, "wave0", gd1)
        assert res1.consecutive == 1

        # Different rule → different fingerprint
        r2 = _mk_rule("rule_B", FailureCode.WORK_TIMED_OUT)
        gd2 = _gate_def(rules=(r2,), default_budget=5)
        s2 = _state(
            gate_attempts_by_phase={"wave0": 1},
            repair_budget_by_phase={"wave0": 4},
            latest_gate_feedback=res1.model_dump(),
        )
        res2 = evaluate_gate(s2, "wave0", gd2)
        assert res2.consecutive == 1  # reset

    def test_cross_phase_isolation(self) -> None:
        rule = _mk_rule("r", FailureCode.WORK_FAILED)
        gd = _gate_def(rules=(rule,))
        s = _state()
        r_wave0 = evaluate_gate(s, "wave0", gd)
        assert r_wave0.consecutive == 1

        # wave1 reads wave0's feedback — different phase → reset
        s2 = _state(latest_gate_feedback=r_wave0.model_dump())
        r_wave1 = evaluate_gate(s2, "wave1", gd)
        assert r_wave1.consecutive == 1  # cross-phase reset

    def test_consecutive_persists_in_feedback(self) -> None:
        rule = _mk_rule("r", FailureCode.WORK_FAILED)
        gd = _gate_def(rules=(rule,))
        r1 = evaluate_gate(_state(), "wave0", gd)
        assert r1.consecutive == 1
        d = r1.model_dump()
        assert d["consecutive"] == 1
        assert d["phase"] == "wave0"


# ---------------------------------------------------------------------------
# 9.x — gate_result_to_state_update
# ---------------------------------------------------------------------------


class TestStateUpdate:
    def test_full_dict_written(self) -> None:
        """Cross-phase data preserved via full-dict writes."""
        r1 = GateResult(phase="wave0", verdict=PhaseVerdict.PASS, route="pass", attempt=1, remaining_budget=3)
        s = _state(gate_attempts_by_phase={"wave1": 2}, repair_budget_by_phase={"wave1": 5})
        update = gate_result_to_state_update(r1, "wave0", s)
        assert update["gate_attempts_by_phase"]["wave0"] == 1
        assert update["gate_attempts_by_phase"]["wave1"] == 2  # preserved!
        assert update["repair_budget_by_phase"]["wave1"] == 5  # preserved!

    def test_terminal_fields_on_blocked(self) -> None:
        r = GateResult(
            phase="wave0",
            verdict=PhaseVerdict.BLOCKED,
            route="exhausted",
            attempt=3,
            remaining_budget=0,
            new_generation=1,
        )
        update = gate_result_to_state_update(r, "wave0", _state())
        assert update["terminal_status"] == "blocked"
        assert update["terminal_reason"] == "gate_blocked"
        assert update["phase_status"] == "terminal"
        assert update["generation"] == 1

    def test_no_terminal_fields_on_pass(self) -> None:
        r = GateResult(phase="wave0", verdict=PhaseVerdict.PASS, route="pass", attempt=1, new_generation=None)
        update = gate_result_to_state_update(r, "wave0", _state())
        assert "terminal_status" not in update
        assert "generation" not in update
