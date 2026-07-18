"""Canonical deterministic replay families and cases.

@impl EVH-001
@impl EVH-008
"""

from __future__ import annotations

from tests.assets.evidence import AssetClass, AuthenticityLevel, StableSeam
from tests.scenarios.contracts import (
    ScenarioBounds,
    ScenarioCase,
    ScenarioExpectations,
    ScenarioFamily,
    ScenarioLane,
)
from tests.scenarios.inputs import (
    FaultPoint,
    LifecycleAction,
    LifecycleActionKind,
    ModelTurn,
    ScenarioInputs,
    ToolOutcome,
    ToolStep,
)
from tests.scenarios.observation import InvariantName

REQUIRED_FIRST_WAVE_FAMILY_IDS = frozenset(
    {
        "quick-factual",
        "claim-verification",
        "insufficient-evidence",
        "prompt-injection",
        "malformed-output",
        "tool-unavailable-timeout",
        "budget-exhaustion",
        "partial-worker-success",
        "checkpoint-control",
        "sandbox-filesystem-failure",
    }
)

QUICK_FACTUAL_FAMILY = ScenarioFamily(
    family_id="quick-factual",
    risk_intent="Accept one bounded factual source and bind answer support to validated ledger authority.",
    requirement_ids=("EVH-001", "EVH-008"),
    regression_ids=(),
    permitted_degradation=(),
)

QUICK_FACTUAL_CASE = ScenarioCase(
    case_id="quick-factual",
    family_id=QUICK_FACTUAL_FAMILY.family_id,
    lane=ScenarioLane.DETERMINISTIC,
    entrypoint="wave0-worker",
    asset_class=AssetClass.DETERMINISTIC_WORKFLOW_CONFORMANCE,
    seam=StableSeam.RUNTIME_INTEGRATION,
    authenticity=AuthenticityLevel.SCRIPTED_REAL_WORKFLOW,
    preconditions=("one-topic", "contained-workspace", "empty-ledger"),
    inputs=ScenarioInputs(
        model_turns=(
            ModelTurn(content="Call bounded web search.", tool_names=("web_search",)),
            ModelTurn(content="Malformed draft requiring bounded repair."),
            ModelTurn(content="Return one validated factual source."),
        ),
        tool_steps=(
            ToolStep(
                tool_name="web_search",
                arguments=(("query", "wave0"),),
                outcome=ToolOutcome.RESULT,
                result="fixed search result",
            ),
        ),
    ),
    bounds=ScenarioBounds(max_attempts=1, max_model_calls=3, max_tool_calls=1, max_wall_seconds=10),
    expectations=ScenarioExpectations(citations=("quick-factual-answer",)),
    hard_invariants=(
        InvariantName.ATTEMPTS_BOUNDED,
        InvariantName.ACCEPTED_AUTHORITY,
        InvariantName.PATHS_CONTAINED,
        InvariantName.ARTIFACTS_HASHED,
        InvariantName.CITATIONS_BOUND,
    ),
    applicable_metrics=("citation-binding-rate",),
)

CLAIM_VERIFICATION_FAMILY = ScenarioFamily(
    family_id="claim-verification",
    risk_intent="Preserve supported, contradicted, and uncertain evidence labels from validated worker authority.",
    requirement_ids=("EVH-001", "EVH-002"),
    regression_ids=(),
    permitted_degradation=(),
)

CLAIM_VERIFICATION_CASE = ScenarioCase(
    case_id="claim-verification",
    family_id=CLAIM_VERIFICATION_FAMILY.family_id,
    lane=ScenarioLane.DETERMINISTIC,
    entrypoint="wave1-worker",
    asset_class=AssetClass.DETERMINISTIC_WORKFLOW_CONFORMANCE,
    seam=StableSeam.RUNTIME_INTEGRATION,
    authenticity=AuthenticityLevel.SCRIPTED_REAL_WORKFLOW,
    preconditions=("one-topic", "contained-workspace", "empty-ledger"),
    inputs=ScenarioInputs(
        model_turns=(
            ModelTurn(content="Call bounded web search.", tool_names=("web_search",)),
            ModelTurn(content="Return labeled supported, contradicted, and uncertain evidence."),
        ),
        tool_steps=(
            ToolStep(
                tool_name="web_search",
                arguments=(("query", "wave1"),),
                outcome=ToolOutcome.RESULT,
                result="fixed search result",
            ),
        ),
    ),
    bounds=ScenarioBounds(max_attempts=1, max_model_calls=2, max_tool_calls=1, max_wall_seconds=10),
    expectations=ScenarioExpectations(),
    hard_invariants=(
        InvariantName.ATTEMPTS_BOUNDED,
        InvariantName.ACCEPTED_AUTHORITY,
        InvariantName.PATHS_CONTAINED,
        InvariantName.ARTIFACTS_HASHED,
        InvariantName.LABELED_EVIDENCE_COMPLETE,
    ),
    applicable_metrics=("labeled-citation-precision", "contradiction-recall"),
)

INSUFFICIENT_EVIDENCE_FAMILY = ScenarioFamily(
    family_id="insufficient-evidence",
    risk_intent="Record validated degraded source limitations without unsupported facts or fabricated citations.",
    requirement_ids=("EVH-001", "EVH-002", "EVH-008"),
    regression_ids=(),
    permitted_degradation=("insufficient-evidence",),
)

INSUFFICIENT_EVIDENCE_CASE = ScenarioCase(
    case_id="insufficient-evidence",
    family_id=INSUFFICIENT_EVIDENCE_FAMILY.family_id,
    lane=ScenarioLane.DETERMINISTIC,
    entrypoint="wave0-worker",
    asset_class=AssetClass.DETERMINISTIC_WORKFLOW_CONFORMANCE,
    seam=StableSeam.RUNTIME_INTEGRATION,
    authenticity=AuthenticityLevel.SCRIPTED_REAL_WORKFLOW,
    preconditions=("one-topic", "contained-workspace", "unavailable-source"),
    inputs=ScenarioInputs(
        model_turns=(
            ModelTurn(content="Call bounded web search.", tool_names=("web_search",)),
            ModelTurn(content="Record unavailable source and explicit limitations without facts."),
        ),
        tool_steps=(
            ToolStep(
                tool_name="web_search",
                arguments=(("query", "storage"),),
                outcome=ToolOutcome.RESULT,
                result="503 Service Unavailable",
            ),
        ),
    ),
    bounds=ScenarioBounds(max_attempts=1, max_model_calls=2, max_tool_calls=1, max_wall_seconds=10),
    expectations=ScenarioExpectations(permitted_degradation=("insufficient-evidence",)),
    hard_invariants=(
        InvariantName.ATTEMPTS_BOUNDED,
        InvariantName.ACCEPTED_AUTHORITY,
        InvariantName.PATHS_CONTAINED,
        InvariantName.ARTIFACTS_HASHED,
        InvariantName.HONEST_DEGRADATION,
    ),
    applicable_metrics=("citation-binding-rate", "unsupported-major-claim-count"),
)

PROMPT_INJECTION_FAMILY = ScenarioFamily(
    family_id="prompt-injection",
    risk_intent="Prevent untrusted source text from forging route, gate, ledger, checkpoint, or path authority.",
    requirement_ids=("EVH-001", "EVH-004", "EVH-008"),
    regression_ids=(),
    permitted_degradation=(),
)

PROMPT_INJECTION_CASE = ScenarioCase(
    case_id="prompt-injection",
    family_id=PROMPT_INJECTION_FAMILY.family_id,
    lane=ScenarioLane.DETERMINISTIC,
    entrypoint="wave0-worker",
    asset_class=AssetClass.DETERMINISTIC_WORKFLOW_CONFORMANCE,
    seam=StableSeam.RUNTIME_INTEGRATION,
    authenticity=AuthenticityLevel.SCRIPTED_REAL_WORKFLOW,
    preconditions=("one-topic", "contained-workspace", "untrusted-source"),
    inputs=ScenarioInputs(
        model_turns=(
            ModelTurn(content="Call bounded web search.", tool_names=("web_search",)),
            ModelTurn(content="Return one validated source without copying control text."),
        ),
        tool_steps=(
            ToolStep(
                tool_name="web_search",
                arguments=(("query", "storage"),),
                outcome=ToolOutcome.RESULT,
                result="untrusted-hostile-source",
            ),
        ),
    ),
    bounds=ScenarioBounds(max_attempts=1, max_model_calls=2, max_tool_calls=1, max_wall_seconds=10),
    expectations=ScenarioExpectations(route="pass"),
    hard_invariants=(
        InvariantName.ROUTE_EXPECTED,
        InvariantName.ACCEPTED_AUTHORITY,
        InvariantName.PATHS_CONTAINED,
        InvariantName.ARTIFACTS_HASHED,
        InvariantName.AUTHORITY_NOT_FORGED,
    ),
    applicable_metrics=("structural-missing-backing-ref-count",),
)

MALFORMED_OUTPUT_FAMILY = ScenarioFamily(
    family_id="malformed-output",
    risk_intent="Consume bounded structured-output repair and fail closed without partial authority.",
    requirement_ids=("EVH-001", "EVH-008"),
    regression_ids=(),
    permitted_degradation=("malformed-output",),
)

MALFORMED_OUTPUT_CASE = ScenarioCase(
    case_id="malformed-output",
    family_id=MALFORMED_OUTPUT_FAMILY.family_id,
    lane=ScenarioLane.DETERMINISTIC,
    entrypoint="wave2-synthesis-node",
    asset_class=AssetClass.DETERMINISTIC_WORKFLOW_CONFORMANCE,
    seam=StableSeam.NODE_INTERFACE,
    authenticity=AuthenticityLevel.SCRIPTED_REAL_WORKFLOW,
    preconditions=("contained-workspace", "empty-accepted-ledger"),
    inputs=ScenarioInputs(
        model_turns=(
            ModelTurn(content="Malformed initial structured output."),
            ModelTurn(content="Malformed bounded repair output."),
        ),
    ),
    bounds=ScenarioBounds(max_attempts=1, max_model_calls=2, max_tool_calls=0, max_wall_seconds=10),
    expectations=ScenarioExpectations(permitted_degradation=("malformed-output",)),
    hard_invariants=(
        InvariantName.ATTEMPTS_BOUNDED,
        InvariantName.PATHS_CONTAINED,
        InvariantName.NO_PARTIAL_AUTHORITY,
    ),
    applicable_metrics=("structural-missing-backing-ref-count",),
)

TOOL_UNAVAILABLE_TIMEOUT_FAMILY = ScenarioFamily(
    family_id="tool-unavailable-timeout",
    risk_intent="Fail closed on unavailable tool configuration and wall-time exhaustion while preserving cancellation.",
    requirement_ids=("EVH-001", "EVH-003"),
    regression_ids=(),
    permitted_degradation=("tool-unavailable-timeout",),
)

TOOL_UNAVAILABLE_TIMEOUT_CASE = ScenarioCase(
    case_id="tool-unavailable-timeout",
    family_id=TOOL_UNAVAILABLE_TIMEOUT_FAMILY.family_id,
    lane=ScenarioLane.DETERMINISTIC,
    entrypoint="runtime-node-agent-bridge",
    asset_class=AssetClass.DETERMINISTIC_WORKFLOW_CONFORMANCE,
    seam=StableSeam.RUNTIME_INTEGRATION,
    authenticity=AuthenticityLevel.SCRIPTED_REAL_WORKFLOW,
    preconditions=("contained-workspace", "no-publication-store"),
    inputs=ScenarioInputs(
        model_turns=(ModelTurn(content="Wait for one bounded bridge outcome."),),
        tool_steps=(
            ToolStep(
                tool_name="web_search",
                arguments=(("query", "storage"),),
                outcome=ToolOutcome.UNAVAILABLE,
            ),
        ),
    ),
    bounds=ScenarioBounds(max_attempts=1, max_model_calls=1, max_tool_calls=1, max_wall_seconds=2),
    expectations=ScenarioExpectations(permitted_degradation=("tool-unavailable-timeout",)),
    hard_invariants=(
        InvariantName.ATTEMPTS_BOUNDED,
        InvariantName.PATHS_CONTAINED,
        InvariantName.NO_PARTIAL_AUTHORITY,
        InvariantName.FAULT_OUTCOMES_COMPLETE,
    ),
    applicable_metrics=("structural-missing-backing-ref-count",),
)

BUDGET_EXHAUSTION_FAMILY = ScenarioFamily(
    family_id="budget-exhaustion",
    risk_intent="Enforce exact model/tool call bounds before another model handler or partial publication.",
    requirement_ids=("EVH-001", "EVH-003"),
    regression_ids=(),
    permitted_degradation=("budget-exhaustion",),
)

BUDGET_EXHAUSTION_CASE = ScenarioCase(
    case_id="budget-exhaustion",
    family_id=BUDGET_EXHAUSTION_FAMILY.family_id,
    lane=ScenarioLane.DETERMINISTIC,
    entrypoint="runtime-node-agent-bridge",
    asset_class=AssetClass.DETERMINISTIC_WORKFLOW_CONFORMANCE,
    seam=StableSeam.RUNTIME_INTEGRATION,
    authenticity=AuthenticityLevel.SCRIPTED_REAL_WORKFLOW,
    preconditions=("contained-workspace", "one-model-call-budget", "one-tool-call-budget"),
    inputs=ScenarioInputs(
        model_turns=(ModelTurn(content="Call one bounded web search.", tool_names=("web_search",)),),
        tool_steps=(
            ToolStep(
                tool_name="web_search",
                arguments=(("query", "storage"),),
                outcome=ToolOutcome.RESULT,
                result="fixed source result",
            ),
        ),
    ),
    bounds=ScenarioBounds(max_attempts=1, max_model_calls=1, max_tool_calls=1, max_wall_seconds=5),
    expectations=ScenarioExpectations(permitted_degradation=("budget-exhaustion",)),
    hard_invariants=(
        InvariantName.ATTEMPTS_BOUNDED,
        InvariantName.PATHS_CONTAINED,
        InvariantName.NO_PARTIAL_AUTHORITY,
        InvariantName.BUDGET_EXHAUSTED,
    ),
    applicable_metrics=("structural-missing-backing-ref-count",),
)

PARTIAL_WORKER_SUCCESS_FAMILY = ScenarioFamily(
    family_id="partial-worker-success",
    risk_intent=(
        "Preserve accepted worker authority while failed work drives distinct repair, fatigue, and exhausted gates."
    ),
    requirement_ids=("EVH-001", "EVH-003", "EVH-008"),
    regression_ids=(),
    permitted_degradation=(),
)

PARTIAL_WORKER_SUCCESS_CASE = ScenarioCase(
    case_id="partial-worker-success",
    family_id=PARTIAL_WORKER_SUCCESS_FAMILY.family_id,
    lane=ScenarioLane.DETERMINISTIC,
    entrypoint="work-unit-controller-gate",
    asset_class=AssetClass.DETERMINISTIC_WORKFLOW_CONFORMANCE,
    seam=StableSeam.RUNTIME_INTEGRATION,
    authenticity=AuthenticityLevel.REAL_NODE_FAKE_CAPABILITIES,
    preconditions=("three-work-units", "one-worker-failure", "contained-workspace"),
    inputs=ScenarioInputs(),
    bounds=ScenarioBounds(max_attempts=3, max_model_calls=0, max_tool_calls=0, max_wall_seconds=10),
    expectations=ScenarioExpectations(route="exhausted", terminal="blocked"),
    hard_invariants=(
        InvariantName.ROUTE_EXPECTED,
        InvariantName.ATTEMPTS_BOUNDED,
        InvariantName.ACCEPTED_AUTHORITY,
        InvariantName.PATHS_CONTAINED,
        InvariantName.ARTIFACTS_HASHED,
        InvariantName.PARTIAL_WORK_OUTCOMES_COMPLETE,
    ),
    applicable_metrics=("structural-missing-backing-ref-count",),
)

CHECKPOINT_CONTROL_FAMILY = ScenarioFamily(
    family_id="checkpoint-control",
    risk_intent="Keep duplicate resume, cancellation, terminal state, and checkpoint identity stable across restarts.",
    requirement_ids=("EVH-001", "EVH-003"),
    regression_ids=(),
    permitted_degradation=(),
)

CHECKPOINT_CONTROL_CASE = ScenarioCase(
    case_id="checkpoint-control",
    family_id=CHECKPOINT_CONTROL_FAMILY.family_id,
    lane=ScenarioLane.DETERMINISTIC,
    entrypoint="lifecycle-mixed-graph",
    asset_class=AssetClass.DETERMINISTIC_WORKFLOW_CONFORMANCE,
    seam=StableSeam.LIFECYCLE_MIXED_GRAPH,
    authenticity=AuthenticityLevel.REAL_NODE_FAKE_CAPABILITIES,
    preconditions=("file-sqlite-checkpointer", "fresh-process-per-action", "contained-workspace"),
    inputs=ScenarioInputs(
        lifecycle_actions=(
            LifecycleAction(LifecycleActionKind.START),
            LifecycleAction(LifecycleActionKind.RESUME),
            LifecycleAction(LifecycleActionKind.RESUME),
            LifecycleAction(LifecycleActionKind.CANCEL),
            LifecycleAction(LifecycleActionKind.CANCEL),
            LifecycleAction(LifecycleActionKind.RESUME),
            LifecycleAction(LifecycleActionKind.STATUS),
        ),
    ),
    bounds=ScenarioBounds(max_attempts=7, max_model_calls=0, max_tool_calls=0, max_wall_seconds=60),
    expectations=ScenarioExpectations(terminal="cancelled"),
    hard_invariants=(
        InvariantName.ATTEMPTS_BOUNDED,
        InvariantName.IDENTITY_ISOLATED,
        InvariantName.PATHS_CONTAINED,
        InvariantName.CHECKPOINT_CONTROL_COMPLETE,
    ),
    applicable_metrics=("checkpoint-transition-count",),
)

SANDBOX_FILESYSTEM_FAILURE_FAMILY = ScenarioFamily(
    family_id="sandbox-filesystem-failure",
    risk_intent="Preserve contained prior-or-single-new ledger authority across atomic publication faults and replay.",
    requirement_ids=("EVH-001", "EVH-003"),
    regression_ids=(),
    permitted_degradation=(),
)

SANDBOX_FILESYSTEM_FAILURE_CASE = ScenarioCase(
    case_id="sandbox-filesystem-failure",
    family_id=SANDBOX_FILESYSTEM_FAILURE_FAMILY.family_id,
    lane=ScenarioLane.DETERMINISTIC,
    entrypoint="work-unit-store",
    asset_class=AssetClass.CODE_CORRECTNESS,
    seam=StableSeam.RUNTIME_INTEGRATION,
    authenticity=None,
    preconditions=("prior-ledger-authority", "contained-workspace", "fresh-store-per-fault"),
    inputs=ScenarioInputs(
        fault_points=(
            FaultPoint.BEFORE_STAGING_WRITE,
            FaultPoint.AFTER_STAGING_FSYNC,
            FaultPoint.AFTER_LEDGER_REPLACE,
            FaultPoint.AFTER_DIRECTORY_FSYNC,
        ),
    ),
    bounds=ScenarioBounds(max_attempts=4, max_model_calls=0, max_tool_calls=0, max_wall_seconds=10),
    expectations=ScenarioExpectations(),
    hard_invariants=(
        InvariantName.ATTEMPTS_BOUNDED,
        InvariantName.PATHS_CONTAINED,
        InvariantName.FILESYSTEM_AUTHORITY_ATOMIC,
    ),
    applicable_metrics=("accepted-authority-count",),
)

FIRST_WAVE_FAMILIES = (
    QUICK_FACTUAL_FAMILY,
    CLAIM_VERIFICATION_FAMILY,
    INSUFFICIENT_EVIDENCE_FAMILY,
    PROMPT_INJECTION_FAMILY,
    MALFORMED_OUTPUT_FAMILY,
    TOOL_UNAVAILABLE_TIMEOUT_FAMILY,
    BUDGET_EXHAUSTION_FAMILY,
    PARTIAL_WORKER_SUCCESS_FAMILY,
    CHECKPOINT_CONTROL_FAMILY,
    SANDBOX_FILESYSTEM_FAILURE_FAMILY,
)
FIRST_WAVE_CASES = (
    QUICK_FACTUAL_CASE,
    CLAIM_VERIFICATION_CASE,
    INSUFFICIENT_EVIDENCE_CASE,
    PROMPT_INJECTION_CASE,
    MALFORMED_OUTPUT_CASE,
    TOOL_UNAVAILABLE_TIMEOUT_CASE,
    BUDGET_EXHAUSTION_CASE,
    PARTIAL_WORKER_SUCCESS_CASE,
    CHECKPOINT_CONTROL_CASE,
    SANDBOX_FILESYSTEM_FAILURE_CASE,
)

__all__ = [
    "BUDGET_EXHAUSTION_CASE",
    "BUDGET_EXHAUSTION_FAMILY",
    "CLAIM_VERIFICATION_CASE",
    "CLAIM_VERIFICATION_FAMILY",
    "CHECKPOINT_CONTROL_CASE",
    "CHECKPOINT_CONTROL_FAMILY",
    "FIRST_WAVE_CASES",
    "FIRST_WAVE_FAMILIES",
    "INSUFFICIENT_EVIDENCE_CASE",
    "INSUFFICIENT_EVIDENCE_FAMILY",
    "MALFORMED_OUTPUT_CASE",
    "MALFORMED_OUTPUT_FAMILY",
    "PARTIAL_WORKER_SUCCESS_CASE",
    "PARTIAL_WORKER_SUCCESS_FAMILY",
    "PROMPT_INJECTION_CASE",
    "PROMPT_INJECTION_FAMILY",
    "SANDBOX_FILESYSTEM_FAILURE_CASE",
    "SANDBOX_FILESYSTEM_FAILURE_FAMILY",
    "TOOL_UNAVAILABLE_TIMEOUT_CASE",
    "TOOL_UNAVAILABLE_TIMEOUT_FAMILY",
    "QUICK_FACTUAL_CASE",
    "QUICK_FACTUAL_FAMILY",
    "REQUIRED_FIRST_WAVE_FAMILY_IDS",
]
