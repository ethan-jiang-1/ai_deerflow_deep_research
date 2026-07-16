"""Real readiness node — hard checks, critic, report plan, route determination.

Non-gated pattern (like hitl2, rerun): the node writes its own route.

@impl REA-001
@impl REA-002
@impl REA-003
@impl REA-004
@impl REA-005
@impl REA-006
@impl REA-007
"""

from __future__ import annotations

import base64
import hashlib
from typing import Any

from deerflow_deep_research.domain.lifecycle import LifecycleStatus, TerminalReason
from deerflow_deep_research.domain.node_spec import NodeBuildDependencies
from deerflow_deep_research.domain.state import ContentRef, PhaseStatus
from deerflow_deep_research.engine.fake_control import node_update

from .contracts import ReadinessReportPlan
from .critic import run_readiness_critic
from .hard_rules import has_structural_failure, run_hard_rules
from .materializer import materialize_report_plan


def _content_ref(research_id: str, plan: ReadinessReportPlan) -> ContentRef:
    """Build a ContentRef for the report plan matching SANDBOX_PATH_RE and CONTENT_HASH_RE."""
    raw = plan.model_dump_json().encode("utf-8")
    digest = hashlib.sha256(raw).digest()
    encoded = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
    return ContentRef(
        sandbox_path=f"workspace/deep-research/{research_id}/review/report-plan.json",
        content_hash=f"h_{encoded[:43]}",
        schema_version=1,
        short_summary=f"Readiness plan: {len(plan.writable_conclusions)} conclusions, "
        f"{len(plan.mandatory_uncertainties)} uncertainties",
    )


def build_real(_dependencies: NodeBuildDependencies):
    async def run(state: dict[str, Any]) -> dict[str, Any]:
        research_id = state.get("research_id", "unknown")

        # 1. Hard checks
        hard_failures = run_hard_rules(state)

        # 2. Critic
        must_answer = tuple(state.get("must_answer_questions") or ())
        accepted_refs = tuple(state.get("accepted_submission_refs") or ())
        critic_output = run_readiness_critic(must_answer, accepted_refs)

        # 3. Materialize report plan
        report_plan = materialize_report_plan(critic_output, hard_failures)

        # 4. Route determination
        blocked_count = sum(
            1 for pq in critic_output.per_question if pq.verdict == "blocked_repair_required"
        )

        if has_structural_failure(hard_failures):
            route = "exhausted"
            terminal_status = LifecycleStatus.BLOCKED.value
            terminal_reason = TerminalReason.GATE_BLOCKED.value
            phase_status = PhaseStatus.TERMINAL.value
        elif blocked_count > 0:
            route = "repair_targeted"
            terminal_status = None
            terminal_reason = None
            phase_status = PhaseStatus.WAITING.value
        else:
            route = "pass"
            terminal_status = None
            terminal_reason = None
            phase_status = PhaseStatus.WAITING.value

        return {
            **node_update("readiness", route=route, phase_status=phase_status),
            "readiness_hard_failures": tuple(
                {"code": f.code, "detail": f.detail, "refs": f.refs} for f in hard_failures
            ),
            "readiness_critic_summary": critic_output.model_dump(),
            "readiness_blocked_count": blocked_count,
            "readiness_report_plan": _content_ref(research_id, report_plan),
            **(dict(terminal_status=terminal_status) if terminal_status else {}),
            **(dict(terminal_reason=terminal_reason) if terminal_reason else {}),
        }

    return run
