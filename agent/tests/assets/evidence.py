"""Canonical test-evidence vocabulary and synthetic claim validation.

@impl EVH-006
@impl EVH-007
@impl EVH-008
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Set
from dataclasses import dataclass
from enum import StrEnum

CLAIM_ID_RE = re.compile(r"^[a-z][a-z0-9-]{2,63}$")
CASE_ID_RE = re.compile(r"^[a-z][a-z0-9-]{2,63}$")
REQUIREMENT_ID_RE = re.compile(r"^[A-Z]{3}-\d{3}$")
DISCOVERY_ID_RE = re.compile(r"^(?:LIVE|RELEASE)-\d{8}-\d{2}$")
MAX_REQUIREMENT_IDS = 32
MAX_DISCOVERY_IDS = 64
SELECTOR_RE = re.compile(
    r"^tests/[A-Za-z0-9_./-]+\.py::"
    r"(?:[A-Za-z_][A-Za-z0-9_]*::)*"
    r"test_[A-Za-z0-9_]+"
    r"(?:\[[^\]\r\n]{1,128}\])?$"
)


class AssetClass(StrEnum):
    CODE_CORRECTNESS = "code-correctness"
    DETERMINISTIC_WORKFLOW_CONFORMANCE = "deterministic-workflow-conformance"
    LIVE_BEHAVIORAL_EVALUATION = "live-behavioral-evaluation"
    RELEASE_ACCEPTANCE = "release-acceptance"


class StableSeam(StrEnum):
    DOMAIN_ENGINE = "domain-engine"
    NODE_INTERFACE = "node-interface"
    RUNTIME_INTEGRATION = "runtime-integration"
    LIFECYCLE_MIXED_GRAPH = "lifecycle-mixed-graph"
    PUBLIC_ENTRY = "public-entry"


class AuthenticityLevel(StrEnum):
    FAKE_GRAPH = "fake-graph"
    REAL_NODE_FAKE_CAPABILITIES = "real-node-fake-capabilities"
    SCRIPTED_REAL_WORKFLOW = "scripted-real-workflow"
    LIVE_REAL_DEPENDENCIES = "live-real-dependencies"
    FULL_REAL_PIPELINE = "full-real-pipeline"


class FocusedSelection(StrEnum):
    FAST = "fast"
    INTEGRATION = "integration"
    WORKFLOW = "workflow"
    LIVE = "live"
    RELEASE = "release"


class EvidenceClaimError(ValueError):
    pass


@dataclass(frozen=True)
class TestEvidenceClaim:
    claim_id: str
    selector: str
    expected_selection: FocusedSelection
    requirement_ids: tuple[str, ...]
    asset_class: AssetClass
    seam: StableSeam
    authenticity: AuthenticityLevel | None = None
    scenario_case_id: str | None = None
    discovery_ids: tuple[str, ...] = ()

    __test__ = False

    def __post_init__(self) -> None:
        if not isinstance(self.claim_id, str) or not CLAIM_ID_RE.fullmatch(self.claim_id):
            raise ValueError("claim_id_invalid")
        if not isinstance(self.selector, str) or not self.selector or len(self.selector) > 512:
            raise ValueError("claim_selector_invalid")
        if "*" in self.selector or "?" in self.selector:
            raise ValueError("claim_selector_pattern_forbidden")
        if not SELECTOR_RE.fullmatch(self.selector):
            raise ValueError("claim_selector_not_exact")
        _require_enum(self.expected_selection, FocusedSelection, "claim_expected_selection_invalid")
        _require_enum(self.asset_class, AssetClass, "claim_asset_class_invalid")
        _require_enum(self.seam, StableSeam, "claim_seam_invalid")
        if self.authenticity is not None:
            _require_enum(self.authenticity, AuthenticityLevel, "claim_authenticity_invalid")
        allowed_selections = {
            AssetClass.CODE_CORRECTNESS: {FocusedSelection.FAST, FocusedSelection.INTEGRATION},
            AssetClass.DETERMINISTIC_WORKFLOW_CONFORMANCE: {FocusedSelection.WORKFLOW},
            AssetClass.LIVE_BEHAVIORAL_EVALUATION: {FocusedSelection.LIVE},
            AssetClass.RELEASE_ACCEPTANCE: {FocusedSelection.RELEASE},
        }
        if self.expected_selection not in allowed_selections[self.asset_class]:
            raise ValueError("claim_asset_selection_conflict")
        if not isinstance(self.requirement_ids, tuple):
            raise ValueError("claim_requirement_ids_invalid")
        if not self.requirement_ids or any(
            not isinstance(value, str) or not REQUIREMENT_ID_RE.fullmatch(value) for value in self.requirement_ids
        ):
            raise ValueError("claim_requirement_ids_invalid")
        if len(self.requirement_ids) > MAX_REQUIREMENT_IDS:
            raise ValueError("claim_requirement_ids_oversize")
        if len(set(self.requirement_ids)) != len(self.requirement_ids):
            raise ValueError("claim_requirement_ids_duplicate")
        if self.scenario_case_id is not None and (
            not isinstance(self.scenario_case_id, str) or not CASE_ID_RE.fullmatch(self.scenario_case_id)
        ):
            raise ValueError("claim_scenario_case_id_invalid")
        if not isinstance(self.discovery_ids, tuple):
            raise ValueError("claim_discovery_ids_invalid")
        if any(not isinstance(value, str) or not DISCOVERY_ID_RE.fullmatch(value) for value in self.discovery_ids):
            raise ValueError("claim_discovery_ids_invalid")
        if len(self.discovery_ids) > MAX_DISCOVERY_IDS:
            raise ValueError("claim_discovery_ids_oversize")
        if len(set(self.discovery_ids)) != len(self.discovery_ids):
            raise ValueError("claim_discovery_ids_duplicate")


def _require_enum(value: object, enum_type: type[StrEnum], code: str) -> None:
    if not isinstance(value, enum_type):
        raise ValueError(code)


def validate_evidence_claims(
    claims: Iterable[TestEvidenceClaim],
    *,
    supplied_case_ids: Set[str],
    collected_selectors: Set[str],
) -> None:
    claims = tuple(claims)
    errors: list[str] = []
    claim_ids: set[str] = set()
    for claim in claims:
        if claim.claim_id in claim_ids:
            errors.append(f"duplicate claim id: {claim.claim_id}")
        claim_ids.add(claim.claim_id)

    by_case: dict[str, list[TestEvidenceClaim]] = {case_id: [] for case_id in supplied_case_ids}
    for claim in claims:
        if claim.scenario_case_id is None:
            continue
        if claim.scenario_case_id not in supplied_case_ids:
            errors.append(f"{claim.claim_id}: unknown scenario case {claim.scenario_case_id}")
            continue
        by_case[claim.scenario_case_id].append(claim)

    for case_id, bound_claims in sorted(by_case.items()):
        if len(bound_claims) != 1:
            errors.append(f"scenario case {case_id} resolves to {len(bound_claims)} claims")
            continue
        claim = bound_claims[0]
        if case_id not in claim.selector:
            errors.append(f"{claim.claim_id}: selector does not contain stable case id {case_id}")

    for claim in claims:
        if claim.selector not in collected_selectors:
            errors.append(f"{claim.claim_id}: uncollected selector {claim.selector}")

    selectors: dict[str, str] = {}
    for claim in claims:
        prior = selectors.get(claim.selector)
        if prior is not None and not (
            claim.scenario_case_id is not None
            and any(error.startswith(f"scenario case {claim.scenario_case_id} resolves to") for error in errors)
        ):
            errors.append(f"duplicate selector: {claim.selector} ({prior}, {claim.claim_id})")
        selectors[claim.selector] = claim.claim_id

    if errors:
        raise EvidenceClaimError("\n".join(errors))


def claim_index(claims: Iterable[TestEvidenceClaim]) -> dict[str, TestEvidenceClaim]:
    """Index a central claim catalog while enforcing global identity."""
    indexed: dict[str, TestEvidenceClaim] = {}
    selectors: dict[str, str] = {}
    errors: list[str] = []
    for claim in claims:
        if claim.claim_id in indexed:
            errors.append(f"duplicate claim id: {claim.claim_id}")
        prior = selectors.get(claim.selector)
        if prior is not None:
            errors.append(f"duplicate selector: {claim.selector} ({prior}, {claim.claim_id})")
        indexed[claim.claim_id] = claim
        selectors[claim.selector] = claim.claim_id
    if errors:
        raise EvidenceClaimError("\n".join(errors))
    return indexed


def validate_inventory_claim_references(
    references: Iterable[tuple[str, tuple[str, ...]]],
    *,
    claims: Mapping[str, TestEvidenceClaim],
) -> None:
    """Resolve inventory references and reject conflicting selector metadata."""
    errors: list[str] = []
    referenced_selectors: dict[str, tuple[str, TestEvidenceClaim]] = {}
    for owner_id, claim_ids in references:
        for claim_id in claim_ids:
            claim = claims.get(claim_id)
            if claim is None:
                errors.append(f"{owner_id}: unknown claim {claim_id}")
                continue
            prior = referenced_selectors.get(claim.selector)
            if prior is not None:
                prior_id, prior_claim = prior
                if claim != prior_claim:
                    errors.append(
                        f"{owner_id}: contradictory selector reference {claim.selector}; "
                        f"{prior_id} uses {prior_claim.claim_id}, registered claim is {claim.claim_id}"
                    )
            else:
                referenced_selectors[claim.selector] = (owner_id, claim)
    if errors:
        raise EvidenceClaimError("\n".join(errors))


def validate_claim_selections(
    claims: Iterable[TestEvidenceClaim],
    *,
    focused_selectors: Mapping[FocusedSelection, Set[str]],
) -> None:
    errors: list[str] = []
    missing = set(FocusedSelection) - focused_selectors.keys()
    for selection in sorted(missing, key=lambda value: value.value):
        errors.append(f"missing focused collection: {selection.value}")

    for claim in claims:
        expected = focused_selectors.get(claim.expected_selection)
        if expected is None:
            continue
        if claim.selector not in expected:
            errors.append(
                f"{claim.claim_id}: selector missing from expected {claim.expected_selection.value} selection: "
                f"{claim.selector}"
            )
        for selection, selectors in focused_selectors.items():
            if selection is not claim.expected_selection and claim.selector in selectors:
                errors.append(
                    f"{claim.claim_id}: selector also collected by {selection.value} selection: {claim.selector}"
                )

    if errors:
        raise EvidenceClaimError("\n".join(errors))


def _correctness_claim(
    claim_id: str,
    selector: str,
    seam: StableSeam,
    *,
    requirement_ids: tuple[str, ...] = ("EVH-008",),
    authenticity: AuthenticityLevel | None = None,
    discovery_ids: tuple[str, ...] = (),
) -> TestEvidenceClaim:
    selection = FocusedSelection.INTEGRATION if selector.startswith("tests/integration/") else FocusedSelection.FAST
    return TestEvidenceClaim(
        claim_id=claim_id,
        selector=selector,
        expected_selection=selection,
        requirement_ids=requirement_ids,
        asset_class=AssetClass.CODE_CORRECTNESS,
        seam=seam,
        authenticity=authenticity,
        discovery_ids=discovery_ids,
    )


EVIDENCE_CLAIMS = (
    TestEvidenceClaim(
        claim_id="workflow-hitl1-zero-tool-bridge",
        selector="tests/integration/test_zero_tool_node_conformance.py::test_hitl1_brief_generation_crosses_real_zero_tool_bridge",
        expected_selection=FocusedSelection.WORKFLOW,
        requirement_ids=("EVH-008", "EVH-009"),
        asset_class=AssetClass.DETERMINISTIC_WORKFLOW_CONFORMANCE,
        seam=StableSeam.NODE_INTERFACE,
        authenticity=AuthenticityLevel.SCRIPTED_REAL_WORKFLOW,
    ),
    TestEvidenceClaim(
        claim_id="workflow-topic-planning-zero-tool-bridge",
        selector="tests/integration/test_zero_tool_node_conformance.py::test_topic_planning_crosses_real_zero_tool_bridge",
        expected_selection=FocusedSelection.WORKFLOW,
        requirement_ids=("EVH-008", "EVH-009"),
        asset_class=AssetClass.DETERMINISTIC_WORKFLOW_CONFORMANCE,
        seam=StableSeam.NODE_INTERFACE,
        authenticity=AuthenticityLevel.SCRIPTED_REAL_WORKFLOW,
    ),
    TestEvidenceClaim(
        claim_id="workflow-wave2-zero-tool-bridge",
        selector="tests/integration/test_zero_tool_node_conformance.py::test_wave2_crosses_real_zero_tool_bridge",
        expected_selection=FocusedSelection.WORKFLOW,
        requirement_ids=("EVH-008", "EVH-009"),
        asset_class=AssetClass.DETERMINISTIC_WORKFLOW_CONFORMANCE,
        seam=StableSeam.NODE_INTERFACE,
        authenticity=AuthenticityLevel.SCRIPTED_REAL_WORKFLOW,
    ),
    TestEvidenceClaim(
        claim_id="workflow-wave0-worker-bridge",
        selector="tests/integration/test_worker_bridge_conformance.py::test_scripted_worker_traverses_real_bridge_tool_policy_artifacts_and_ledger[quick-factual]",
        expected_selection=FocusedSelection.WORKFLOW,
        requirement_ids=("EVH-008", "EVH-009"),
        asset_class=AssetClass.DETERMINISTIC_WORKFLOW_CONFORMANCE,
        seam=StableSeam.RUNTIME_INTEGRATION,
        authenticity=AuthenticityLevel.SCRIPTED_REAL_WORKFLOW,
        scenario_case_id="quick-factual",
    ),
    TestEvidenceClaim(
        claim_id="workflow-targeted-evidence-worker-bridge",
        selector="tests/integration/test_worker_bridge_conformance.py::test_scripted_worker_traverses_real_bridge_tool_policy_artifacts_and_ledger[targeted_evidence]",
        expected_selection=FocusedSelection.WORKFLOW,
        requirement_ids=("EVH-008", "EVH-009"),
        asset_class=AssetClass.DETERMINISTIC_WORKFLOW_CONFORMANCE,
        seam=StableSeam.RUNTIME_INTEGRATION,
        authenticity=AuthenticityLevel.SCRIPTED_REAL_WORKFLOW,
    ),
    TestEvidenceClaim(
        claim_id="workflow-wave1-worker-bridge",
        selector="tests/integration/test_worker_bridge_conformance.py::test_scripted_worker_traverses_real_bridge_tool_policy_artifacts_and_ledger[claim-verification]",
        expected_selection=FocusedSelection.WORKFLOW,
        requirement_ids=("EVH-008", "EVH-009"),
        asset_class=AssetClass.DETERMINISTIC_WORKFLOW_CONFORMANCE,
        seam=StableSeam.RUNTIME_INTEGRATION,
        authenticity=AuthenticityLevel.SCRIPTED_REAL_WORKFLOW,
        scenario_case_id="claim-verification",
    ),
    TestEvidenceClaim(
        claim_id="workflow-insufficient-evidence-wave0",
        selector="tests/integration/test_adversarial_worker_path.py::test_low_quality_or_unavailable_sources_are_explicitly_degraded[insufficient-evidence]",
        expected_selection=FocusedSelection.WORKFLOW,
        requirement_ids=("EVH-001", "EVH-002", "EVH-008", "EVH-009"),
        asset_class=AssetClass.DETERMINISTIC_WORKFLOW_CONFORMANCE,
        seam=StableSeam.RUNTIME_INTEGRATION,
        authenticity=AuthenticityLevel.SCRIPTED_REAL_WORKFLOW,
        scenario_case_id="insufficient-evidence",
    ),
    TestEvidenceClaim(
        claim_id="workflow-prompt-injection-wave0",
        selector="tests/integration/test_adversarial_worker_path.py::test_authority_forging_source_text_cannot_control_ledger_or_gate[prompt-injection]",
        expected_selection=FocusedSelection.WORKFLOW,
        requirement_ids=("EVH-001", "EVH-004", "EVH-008", "EVH-009"),
        asset_class=AssetClass.DETERMINISTIC_WORKFLOW_CONFORMANCE,
        seam=StableSeam.RUNTIME_INTEGRATION,
        authenticity=AuthenticityLevel.SCRIPTED_REAL_WORKFLOW,
        scenario_case_id="prompt-injection",
    ),
    TestEvidenceClaim(
        claim_id="workflow-malformed-output-wave2",
        selector="tests/integration/test_zero_tool_node_conformance.py::test_wave2_malformed_output_consumes_repair_and_leaves_no_partial_authority[malformed-output]",
        expected_selection=FocusedSelection.WORKFLOW,
        requirement_ids=("EVH-001", "EVH-008", "EVH-009"),
        asset_class=AssetClass.DETERMINISTIC_WORKFLOW_CONFORMANCE,
        seam=StableSeam.NODE_INTERFACE,
        authenticity=AuthenticityLevel.SCRIPTED_REAL_WORKFLOW,
        scenario_case_id="malformed-output",
    ),
    TestEvidenceClaim(
        claim_id="workflow-tool-unavailable-timeout-bridge",
        selector="tests/eval/test_fault_injection.py::test_tool_unavailable_timeout_bridge_fails_closed[tool-unavailable-timeout]",
        expected_selection=FocusedSelection.WORKFLOW,
        requirement_ids=("EVH-001", "EVH-003", "EVH-009"),
        asset_class=AssetClass.DETERMINISTIC_WORKFLOW_CONFORMANCE,
        seam=StableSeam.RUNTIME_INTEGRATION,
        authenticity=AuthenticityLevel.SCRIPTED_REAL_WORKFLOW,
        scenario_case_id="tool-unavailable-timeout",
    ),
    TestEvidenceClaim(
        claim_id="workflow-budget-exhaustion-bridge",
        selector="tests/unit/test_node_agent_bridge.py::test_real_bridge_enforces_exact_model_tool_budget_without_publication[budget-exhaustion]",
        expected_selection=FocusedSelection.WORKFLOW,
        requirement_ids=("EVH-001", "EVH-003", "EVH-009"),
        asset_class=AssetClass.DETERMINISTIC_WORKFLOW_CONFORMANCE,
        seam=StableSeam.RUNTIME_INTEGRATION,
        authenticity=AuthenticityLevel.SCRIPTED_REAL_WORKFLOW,
        scenario_case_id="budget-exhaustion",
    ),
    TestEvidenceClaim(
        claim_id="workflow-partial-worker-submit-gate",
        selector="tests/integration/test_wave0_work_units.py::test_partial_worker_success_projects_distinct_gate_outcomes_from_authoritative_state[partial-worker-success]",
        expected_selection=FocusedSelection.WORKFLOW,
        requirement_ids=("EVH-001", "EVH-003", "EVH-008", "EVH-009"),
        asset_class=AssetClass.DETERMINISTIC_WORKFLOW_CONFORMANCE,
        seam=StableSeam.RUNTIME_INTEGRATION,
        authenticity=AuthenticityLevel.REAL_NODE_FAKE_CAPABILITIES,
        scenario_case_id="partial-worker-success",
    ),
    TestEvidenceClaim(
        claim_id="workflow-checkpoint-control-restart",
        selector="tests/integration/test_provider_durability.py::test_checkpoint_control_survives_process_restarts[checkpoint-control]",
        expected_selection=FocusedSelection.WORKFLOW,
        requirement_ids=("EVH-001", "EVH-003", "EVH-009"),
        asset_class=AssetClass.DETERMINISTIC_WORKFLOW_CONFORMANCE,
        seam=StableSeam.LIFECYCLE_MIXED_GRAPH,
        authenticity=AuthenticityLevel.REAL_NODE_FAKE_CAPABILITIES,
        scenario_case_id="checkpoint-control",
    ),
    TestEvidenceClaim(
        claim_id="store-prior-authority-fault-matrix",
        selector="tests/unit/test_work_unit_store.py::test_prior_authority_survives_atomic_publication_fault_matrix[sandbox-filesystem-failure]",
        expected_selection=FocusedSelection.FAST,
        requirement_ids=("EVH-001", "EVH-003"),
        asset_class=AssetClass.CODE_CORRECTNESS,
        seam=StableSeam.RUNTIME_INTEGRATION,
        authenticity=None,
        scenario_case_id="sandbox-filesystem-failure",
    ),
    _correctness_claim(
        "live-discovery-workspace-cleanup",
        "tests/unit/test_work_unit_storage.py::test_runtime_verifier_cleanup_is_idempotent_with_real_local_sandbox",
        StableSeam.RUNTIME_INTEGRATION,
        requirement_ids=("EVH-006", "EVH-010"),
        discovery_ids=("LIVE-20260717-01",),
    ),
    _correctness_claim(
        "live-discovery-model-construction",
        "tests/unit/test_live_evaluation.py::test_live_model_config_constructs_with_one_retry_authority",
        StableSeam.RUNTIME_INTEGRATION,
        requirement_ids=("EVH-006", "EVH-010"),
        discovery_ids=("LIVE-20260717-02",),
    ),
    _correctness_claim(
        "live-discovery-canary-precondition",
        "tests/unit/test_live_evaluation.py::test_live_canary_setup_payloads_satisfy_real_node_parsers",
        StableSeam.NODE_INTERFACE,
        requirement_ids=("EVH-006", "EVH-010"),
        discovery_ids=("LIVE-20260717-03",),
    ),
    _correctness_claim(
        "live-discovery-wave0-prompt-contract",
        "tests/graph/test_wave0_worker.py::test_build_wave0_worker_prompt_carries_topic_constraints",
        StableSeam.NODE_INTERFACE,
        requirement_ids=("EVH-006", "EVH-010"),
        discovery_ids=("LIVE-20260717-04",),
    ),
    _correctness_claim(
        "live-discovery-tool-required",
        "tests/unit/test_node_agent_bridge.py::test_request_requiring_tool_execution_rejects_direct_model_answer",
        StableSeam.RUNTIME_INTEGRATION,
        requirement_ids=("EVH-006", "EVH-010"),
        discovery_ids=("LIVE-20260717-06",),
    ),
    _correctness_claim(
        "release-discovery-final-publication",
        "tests/unit/test_final_delivery_real.py::TestRealFinalDelivery::test_materializes_report_and_citation_map_with_matching_refs",
        StableSeam.RUNTIME_INTEGRATION,
        requirement_ids=("EVH-006", "EVH-010"),
        discovery_ids=("RELEASE-20260717-01",),
    ),
    _correctness_claim(
        "release-discovery-profile-budget",
        "tests/graph/test_topic_planning_prompts.py::test_very_quick_overview_limits_plan_to_one_topic",
        StableSeam.NODE_INTERFACE,
        requirement_ids=("EVH-006", "EVH-010"),
        discovery_ids=("RELEASE-20260717-02",),
    ),
    _correctness_claim(
        "release-discovery-wave2-structured-repair",
        "tests/graph/test_wave2_synthesis_real.py::test_real_synthesis_repairs_malformed_output_once_without_tools",
        StableSeam.NODE_INTERFACE,
        requirement_ids=("EVH-006", "EVH-010"),
        discovery_ids=("RELEASE-20260717-08",),
    ),
    _correctness_claim(
        "release-discovery-topic-bound",
        "tests/graph/test_topic_planning_node.py::test_minimal_quick_profile_repairs_multi_topic_plan_to_exactly_one",
        StableSeam.NODE_INTERFACE,
        requirement_ids=("EVH-006", "EVH-010"),
        discovery_ids=("RELEASE-20260717-10",),
    ),
    _correctness_claim(
        "release-discovery-synthesis-semantic-floor",
        "tests/graph/test_wave2_synthesis_real.py::test_real_synthesis_rejects_empty_repair_when_accepted_evidence_exists",
        StableSeam.NODE_INTERFACE,
        requirement_ids=("EVH-006", "EVH-010"),
        discovery_ids=("RELEASE-20260717-13",),
    ),
    _correctness_claim(
        "release-discovery-readiness-provenance",
        "tests/unit/test_readiness_real.py::TestRealReadiness::test_canonical_ledger_hash_passes_provenance",
        StableSeam.DOMAIN_ENGINE,
        requirement_ids=("EVH-006", "EVH-010"),
        discovery_ids=("RELEASE-20260717-14",),
    ),
    _correctness_claim(
        "release-discovery-visible-retry-trace",
        "tests/unit/test_release_control_plane.py::test_release_trace_accepts_consecutive_visible_internal_retries",
        StableSeam.PUBLIC_ENTRY,
        requirement_ids=("EVH-006", "EVH-010"),
        discovery_ids=("RELEASE-20260717-15",),
    ),
    _correctness_claim(
        "release-discovery-dotenv-handoff",
        "tests/unit/test_release_control_plane.py::test_release_make_target_shares_optional_dotenv_with_preflight_and_pytest",
        StableSeam.PUBLIC_ENTRY,
        requirement_ids=("EVH-006", "EVH-010"),
        discovery_ids=("RELEASE-20260717-16",),
    ),
    _correctness_claim(
        "release-discovery-redacted-schema-diagnostics",
        "tests/unit/test_live_evaluation.py::test_live_usage_tracker_reports_synthesis_schema_errors_without_values",
        StableSeam.RUNTIME_INTEGRATION,
        requirement_ids=("EVH-006", "EVH-010"),
        discovery_ids=("RELEASE-20260717-17",),
    ),
    _correctness_claim(
        "shape-wave0-url-canonicalization",
        "tests/graph/test_wave0_provider_shapes.py::test_wave0_provider_shape[shape-wave0-url-canonicalization]",
        StableSeam.NODE_INTERFACE,
        requirement_ids=("EVH-006", "EVH-010"),
        discovery_ids=("RELEASE-20260717-03",),
    ),
    _correctness_claim(
        "shape-wave0-fetch-status-alias",
        "tests/graph/test_wave0_provider_shapes.py::test_wave0_provider_shape[shape-wave0-fetch-status-alias]",
        StableSeam.NODE_INTERFACE,
        requirement_ids=("EVH-006", "EVH-010"),
        discovery_ids=("RELEASE-20260717-04",),
    ),
    _correctness_claim(
        "shape-wave0-limitations-list",
        "tests/graph/test_wave0_provider_shapes.py::test_wave0_provider_shape[shape-wave0-limitations-list]",
        StableSeam.NODE_INTERFACE,
        requirement_ids=("EVH-006", "EVH-010"),
        discovery_ids=("RELEASE-20260717-05",),
    ),
    _correctness_claim(
        "shape-wave0-partial-source-degradation",
        "tests/graph/test_wave0_provider_shapes.py::test_wave0_provider_shape[shape-wave0-partial-source-degradation]",
        StableSeam.NODE_INTERFACE,
        requirement_ids=("EVH-006", "EVH-010"),
        discovery_ids=("RELEASE-20260717-12",),
    ),
    _correctness_claim(
        "shape-wave0-duplicate-source-fail-closed",
        "tests/graph/test_wave0_provider_shapes.py::test_wave0_provider_shape[shape-wave0-duplicate-source-fail-closed]",
        StableSeam.NODE_INTERFACE,
        requirement_ids=("EVH-006", "EVH-010"),
        discovery_ids=("RELEASE-20260717-12",),
    ),
    _correctness_claim(
        "shape-wave1-provider-identifiers",
        "tests/unit/test_wave1_provider_shapes.py::test_wave1_provider_shape[shape-wave1-provider-identifiers]",
        StableSeam.DOMAIN_ENGINE,
        requirement_ids=("EVH-006", "EVH-010"),
        discovery_ids=("RELEASE-20260717-07",),
    ),
    _correctness_claim(
        "shape-wave1-source-id-ref-rewrites",
        "tests/unit/test_wave1_provider_shapes.py::test_wave1_provider_shape[shape-wave1-source-id-ref-rewrites]",
        StableSeam.DOMAIN_ENGINE,
        requirement_ids=("EVH-006", "EVH-010"),
        discovery_ids=("RELEASE-20260717-18",),
    ),
    _correctness_claim(
        "shape-wave1-source-order",
        "tests/integration/test_wave1_work_units.py::test_real_wave1_canonicalizes_provider_source_order_before_candidate_validation[shape-wave1-source-order]",
        StableSeam.RUNTIME_INTEGRATION,
        requirement_ids=("EVH-006", "EVH-010"),
        discovery_ids=("RELEASE-20260717-21",),
    ),
    *(
        _correctness_claim(
            case_id,
            f"tests/graph/test_wave2_provider_shapes.py::test_wave2_provider_shape[{case_id}]",
            StableSeam.NODE_INTERFACE,
            requirement_ids=("EVH-006", "EVH-010"),
            discovery_ids=(discovery_id,),
        )
        for case_id, discovery_id in (
            ("shape-wave2-provider-field-aliases", "RELEASE-20260717-09"),
            ("shape-wave2-gap-priority-alias", "RELEASE-20260717-11"),
            ("shape-wave2-description-string-gaps", "RELEASE-20260717-19"),
            ("shape-wave2-sparse-findings", "RELEASE-20260717-20"),
            ("shape-wave2-relation-endpoints", "RELEASE-20260717-22"),
            ("shape-wave2-singular-affected-topic", "RELEASE-20260717-23"),
            ("shape-wave2-alternate-relation", "RELEASE-20260717-24"),
            ("shape-wave2-missing-gap-identity", "RELEASE-20260717-25"),
        )
    ),
    _correctness_claim(
        "shape-wave2-evidence-alias-binding",
        "tests/graph/test_wave2_synthesis_real.py::test_real_synthesis_maps_source_aliases_to_accepted_record_refs[shape-wave2-evidence-alias-binding]",
        StableSeam.NODE_INTERFACE,
        requirement_ids=("EVH-006", "EVH-010"),
        discovery_ids=("RELEASE-20260717-20",),
    ),
    TestEvidenceClaim(
        claim_id="live-wave0-provider-tool-selection",
        selector="tests/live/test_canaries.py::test_live_prefix_canary[live-one-topic-wave0]",
        expected_selection=FocusedSelection.LIVE,
        requirement_ids=("EVH-005", "EVH-010"),
        asset_class=AssetClass.LIVE_BEHAVIORAL_EVALUATION,
        seam=StableSeam.LIFECYCLE_MIXED_GRAPH,
        authenticity=AuthenticityLevel.LIVE_REAL_DEPENDENCIES,
        discovery_ids=("LIVE-20260717-05",),
    ),
    TestEvidenceClaim(
        claim_id="live-wave1-focused-provider",
        selector="tests/live/test_canaries.py::test_live_prefix_canary[live-one-topic-wave1]",
        expected_selection=FocusedSelection.LIVE,
        requirement_ids=("EVH-005", "EVH-009"),
        asset_class=AssetClass.LIVE_BEHAVIORAL_EVALUATION,
        seam=StableSeam.RUNTIME_INTEGRATION,
        authenticity=AuthenticityLevel.LIVE_REAL_DEPENDENCIES,
    ),
    TestEvidenceClaim(
        claim_id="live-wave2-focused-provider",
        selector="tests/live/test_canaries.py::test_live_prefix_canary[live-wave2-synthesis]",
        expected_selection=FocusedSelection.LIVE,
        requirement_ids=("EVH-005", "EVH-009"),
        asset_class=AssetClass.LIVE_BEHAVIORAL_EVALUATION,
        seam=StableSeam.RUNTIME_INTEGRATION,
        authenticity=AuthenticityLevel.LIVE_REAL_DEPENDENCIES,
    ),
    TestEvidenceClaim(
        claim_id="live-targeted-focused-provider",
        selector="tests/live/test_canaries.py::test_live_prefix_canary[live-one-gap-targeted-evidence]",
        expected_selection=FocusedSelection.LIVE,
        requirement_ids=("EVH-005", "EVH-009"),
        asset_class=AssetClass.LIVE_BEHAVIORAL_EVALUATION,
        seam=StableSeam.RUNTIME_INTEGRATION,
        authenticity=AuthenticityLevel.LIVE_REAL_DEPENDENCIES,
    ),
    _correctness_claim(
        "live-report-archive-contract",
        "tests/unit/test_live_evaluation.py::test_live_report_archive_scan_requires_nonempty_schema_valid_reports",
        StableSeam.DOMAIN_ENGINE,
        requirement_ids=("EVH-005", "EVH-010"),
    ),
    TestEvidenceClaim(
        claim_id="release-full-real-acceptance",
        selector="tests/e2e/test_release_acceptance.py::test_full_real_release_acceptance",
        expected_selection=FocusedSelection.RELEASE,
        requirement_ids=("EVH-004", "EVH-005", "EVH-009"),
        asset_class=AssetClass.RELEASE_ACCEPTANCE,
        seam=StableSeam.PUBLIC_ENTRY,
        authenticity=AuthenticityLevel.FULL_REAL_PIPELINE,
    ),
    _correctness_claim(
        "real-recipe-compiles",
        "tests/unit/test_research_runtime_capabilities.py::test_all_real_recipe_compiles",
        StableSeam.DOMAIN_ENGINE,
        requirement_ids=("EVH-006", "EVH-008"),
    ),
    _correctness_claim(
        "non-interactive-policy-forwarding",
        "tests/unit/test_non_interactive.py::test_tool_forwards_non_interactive_policy_to_action_input",
        StableSeam.PUBLIC_ENTRY,
        requirement_ids=("EVH-006", "EVH-008"),
        authenticity=AuthenticityLevel.REAL_NODE_FAKE_CAPABILITIES,
    ),
    _correctness_claim(
        "model-resolver-empty-config",
        "tests/unit/test_node_agent_bridge.py::test_default_model_resolver_rejects_empty_model_config",
        StableSeam.RUNTIME_INTEGRATION,
        requirement_ids=("EVH-006", "EVH-008"),
    ),
    _correctness_claim(
        "demo-adapter-unique-sandbox",
        "tests/unit/test_demo_core.py::test_demo_adapter_provides_legal_unique_sandbox",
        StableSeam.RUNTIME_INTEGRATION,
        requirement_ids=("EVH-006", "EVH-008"),
    ),
    _correctness_claim(
        "store-verified-temp-workspace",
        "tests/unit/test_work_unit_store.py::test_store_factory_accepts_verified_temp_workspace",
        StableSeam.RUNTIME_INTEGRATION,
        requirement_ids=("EVH-006", "EVH-008"),
    ),
    _correctness_claim(
        "tool-resolver-missing-allowed-tools",
        "tests/unit/test_node_agent_bridge.py::test_default_tools_resolver_rejects_missing_allowed_tools",
        StableSeam.RUNTIME_INTEGRATION,
        requirement_ids=("EVH-006", "EVH-008"),
    ),
    _correctness_claim(
        "worker-policy-tool-specs",
        "tests/unit/test_research_runtime_capabilities.py::test_worker_policies_specify_every_allowed_tool",
        StableSeam.NODE_INTERFACE,
        requirement_ids=("EVH-006", "EVH-008"),
    ),
    _correctness_claim(
        "distinct-worker-policy-routing",
        "tests/unit/test_research_runtime_capabilities.py::test_all_real_context_routes_distinct_worker_policies",
        StableSeam.LIFECYCLE_MIXED_GRAPH,
        requirement_ids=("EVH-006", "EVH-008"),
        authenticity=AuthenticityLevel.REAL_NODE_FAKE_CAPABILITIES,
    ),
    _correctness_claim(
        "budget-large-history-admission",
        "tests/unit/test_budget_middleware.py::test_large_tool_result_history_uses_bounded_admission",
        StableSeam.NODE_INTERFACE,
        requirement_ids=("EVH-006", "EVH-008"),
    ),
    _correctness_claim(
        "budget-max-model-calls",
        "tests/unit/test_budget_middleware.py::test_max_model_calls_refused_before_handler",
        StableSeam.NODE_INTERFACE,
        requirement_ids=("EVH-006", "EVH-008"),
    ),
    _correctness_claim(
        "budget-parallel-tool-calls",
        "tests/unit/test_budget_middleware.py::test_parallel_tool_call_limit",
        StableSeam.NODE_INTERFACE,
        requirement_ids=("EVH-006", "EVH-008"),
    ),
    _correctness_claim(
        "topic-planning-invalid-output",
        "tests/graph/test_topic_planning_node.py::test_repeated_invalid_plan_exhausts_without_topic_state",
        StableSeam.NODE_INTERFACE,
        requirement_ids=("EVH-006", "EVH-008"),
        authenticity=AuthenticityLevel.REAL_NODE_FAKE_CAPABILITIES,
    ),
    _correctness_claim(
        "gate-fatigue-reset",
        "tests/engine/test_gate_kernel.py::TestFatigue::test_successful_evaluation_resets_prior_failure_fatigue",
        StableSeam.DOMAIN_ENGINE,
        requirement_ids=("EVH-006", "EVH-008"),
    ),
    _correctness_claim(
        "bootstrap-marker-needs-input",
        "tests/graph/test_bootstrap_node.py::TestBuildRealRoutesOnBinding::test_bound_marker_routes_needs_input_with_no_model_call",
        StableSeam.NODE_INTERFACE,
    ),
    _correctness_claim(
        "bootstrap-divergent-read-back",
        "tests/graph/test_bootstrap_node.py::TestBuildRealRoutesOnBinding::test_divergent_read_back_fails_closed_terminal",
        StableSeam.NODE_INTERFACE,
    ),
    _correctness_claim(
        "hitl1-complete-response",
        "tests/graph/test_hitl1_node.py::test_complete_response_writes_profile_and_routes_accepted",
        StableSeam.NODE_INTERFACE,
    ),
    _correctness_claim(
        "hitl1-run-agent-failure",
        "tests/graph/test_hitl1_node.py::test_run_agent_failure_exhausts_without_partial_state",
        StableSeam.NODE_INTERFACE,
    ),
    _correctness_claim(
        "topic-planning-valid-plan",
        "tests/graph/test_topic_planning_node.py::test_valid_plan_routes_next_and_records_registry",
        StableSeam.NODE_INTERFACE,
    ),
    _correctness_claim(
        "wave0-complete-lifecycle",
        "tests/integration/test_wave0_lifecycle.py::test_mixed_wave0_complete_lifecycle",
        StableSeam.LIFECYCLE_MIXED_GRAPH,
    ),
    _correctness_claim(
        "wave0-all-workers-fail",
        "tests/integration/test_wave0_lifecycle.py::test_wave0_blocked_when_worker_fails_every_topic",
        StableSeam.LIFECYCLE_MIXED_GRAPH,
    ),
    _correctness_claim(
        "wave1-worker-ledger-success",
        "tests/integration/test_wave1_work_units.py::test_real_wave1_crosses_worker_context_artifact_validator_and_ledger",
        StableSeam.RUNTIME_INTEGRATION,
        requirement_ids=("EVH-006", "EVH-008", "EVH-010"),
        discovery_ids=("RELEASE-20260717-06",),
    ),
    _correctness_claim(
        "wave1-malformed-worker-output",
        "tests/integration/test_wave1_work_units.py::test_real_wave1_malformed_output_becomes_typed_worker_failure_without_ledger[shape-wave1-malformed-submit]",
        StableSeam.RUNTIME_INTEGRATION,
        requirement_ids=("EVH-006", "EVH-008", "EVH-010"),
        discovery_ids=("RELEASE-20260717-18",),
    ),
    _correctness_claim(
        "wave2-canonical-findings",
        "tests/graph/test_wave2_synthesis_real.py::test_real_synthesis_uses_node_context_and_materializes_canonical_findings",
        StableSeam.NODE_INTERFACE,
    ),
    _correctness_claim(
        "wave2-malformed-output",
        "tests/graph/test_wave2_synthesis_real.py::test_real_synthesis_malformed_output_fails_without_artifact",
        StableSeam.NODE_INTERFACE,
    ),
    _correctness_claim(
        "targeted-evidence-valid-artifact",
        "tests/graph/test_targeted_evidence_real.py::test_source_diagnostic_uses_node_context_and_materializes_validated_artifact",
        StableSeam.NODE_INTERFACE,
    ),
    _correctness_claim(
        "targeted-evidence-malformed-output",
        "tests/graph/test_targeted_evidence_real.py::test_source_diagnostic_malformed_output_fails_without_artifact",
        StableSeam.NODE_INTERFACE,
    ),
    _correctness_claim(
        "hitl2-proceed-route",
        "tests/unit/test_hitl2_real.py::TestRealHitl2Factory::test_proceed_route",
        StableSeam.NODE_INTERFACE,
    ),
    _correctness_claim(
        "hitl2-stale-request-rejected",
        "tests/unit/test_hitl2_real.py::TestRealHitl2Factory::test_stale_request_id_rejected",
        StableSeam.NODE_INTERFACE,
        requirement_ids=("EVH-003", "EVH-008"),
    ),
    _correctness_claim(
        "rerun-full-scope-lifecycle",
        "tests/unit/test_rerun_real.py::TestRealRerunFactory::test_full_scope_full_lifecycle",
        StableSeam.NODE_INTERFACE,
    ),
    _correctness_claim(
        "rerun-generation-ceiling",
        "tests/unit/test_rerun_real.py::TestRealRerunFactory::test_generation_at_ceiling_exhausted",
        StableSeam.NODE_INTERFACE,
    ),
    _correctness_claim(
        "readiness-all-clear",
        "tests/unit/test_readiness_real.py::TestRealReadiness::test_all_clear_routes_pass",
        StableSeam.NODE_INTERFACE,
    ),
    _correctness_claim(
        "readiness-no-evidence",
        "tests/unit/test_readiness_real.py::TestRealReadiness::test_no_evidence_routes_exhausted",
        StableSeam.NODE_INTERFACE,
    ),
    _correctness_claim(
        "final-delivery-completed",
        "tests/unit/test_final_delivery_real.py::TestRealFinalDelivery::test_produces_report_refs_and_completed",
        StableSeam.NODE_INTERFACE,
    ),
    _correctness_claim(
        "final-delivery-empty-evidence",
        "tests/unit/test_final_delivery_real.py::TestRealFinalDelivery::test_handles_empty_evidence",
        StableSeam.NODE_INTERFACE,
    ),
    _correctness_claim(
        "lifecycle-consumed-resume-cancel",
        "tests/integration/test_research_lifecycle_tool.py::test_consumed_resume_reprojects_next_interrupt_and_cancel_is_idempotent",
        StableSeam.PUBLIC_ENTRY,
        requirement_ids=("EVH-003", "EVH-008"),
    ),
    _correctness_claim(
        "bridge-wall-time-timeout",
        "tests/eval/test_fault_injection.py::test_wall_time_timeout_returns_typed_budget_exhausted_outcome",
        StableSeam.NODE_INTERFACE,
        requirement_ids=("EVH-003", "EVH-008"),
    ),
    _correctness_claim(
        "store-atomic-publication-replay",
        "tests/unit/test_work_unit_store.py::test_atomic_publication_fault_boundaries_replay_from_last_parent_checkpoint[after_staging_fsync-False]",
        StableSeam.RUNTIME_INTEGRATION,
        requirement_ids=("EVH-003", "EVH-008"),
    ),
    _correctness_claim(
        "store-conflicting-worker-result",
        "tests/integration/test_work_unit_submit_boundary.py::test_same_hash_replays_and_different_hash_conflicts_at_real_store_boundary",
        StableSeam.RUNTIME_INTEGRATION,
        requirement_ids=("EVH-003", "EVH-008"),
    ),
    _correctness_claim(
        "provider-subprocess-restart",
        "tests/integration/test_provider_durability.py::test_file_sqlite_research_resumes_after_real_subprocess_restart",
        StableSeam.LIFECYCLE_MIXED_GRAPH,
        requirement_ids=("EVH-003", "EVH-008"),
    ),
)


__all__ = [
    "AssetClass",
    "AuthenticityLevel",
    "EVIDENCE_CLAIMS",
    "EvidenceClaimError",
    "FocusedSelection",
    "StableSeam",
    "TestEvidenceClaim",
    "claim_index",
    "validate_evidence_claims",
    "validate_claim_selections",
    "validate_inventory_claim_references",
]
