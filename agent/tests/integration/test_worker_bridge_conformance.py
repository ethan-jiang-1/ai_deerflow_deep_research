"""Complete deterministic worker paths through bridge, tool, store, and ledger.

@impl EVH-003
@impl EVH-004
@impl EVH-008
"""

from __future__ import annotations

import json
import time
from datetime import UTC, datetime
from pathlib import Path

import pytest

from deerflow_deep_research.agents.policies import ExecutionBudget, ExecutionPolicy, ToolPolicySpec
from deerflow_deep_research.domain.context import GraphContextView, NodeAgentContext
from deerflow_deep_research.domain.invocation import WorkUnitControllerDependencies
from deerflow_deep_research.domain.node_spec import NodeBuildDependencies
from deerflow_deep_research.graph.nodes.targeted_evidence import NODE_SPEC as TARGETED_SPEC
from deerflow_deep_research.graph.nodes.wave0.subgraph import run_wave0_work_units_real
from deerflow_deep_research.graph.nodes.wave1.subgraph import run_wave1_work_units_real
from deerflow_deep_research.runtime.node_agent_bridge import RuntimeNodeAgentBridge
from deerflow_deep_research.runtime.projection import RuntimeWorkUnitDependencyResolver
from deerflow_deep_research.runtime.work_unit_store import WorkUnitStore
from tests.fixtures.fake_models import ScriptedChatModel, ai_message
from tests.fixtures.runtime import local_runtime_envelope, unique_run_identity
from tests.fixtures.scripted_tools import ScriptedTool
from tests.scenarios.assertions import assert_scenario
from tests.scenarios.inputs import ObservedToolCall, ScriptExecutionObservation, validate_script_observation
from tests.scenarios.observation import (
    CheckpointFacts,
    EvidenceState,
    LabeledEvidenceFact,
    LedgerFacts,
    SandboxFacts,
    ScenarioObservation,
)
from tests.scenarios.replays import (
    CLAIM_VERIFICATION_CASE,
    CLAIM_VERIFICATION_FAMILY,
    QUICK_FACTUAL_CASE,
    QUICK_FACTUAL_FAMILY,
)

NOW = datetime(2026, 7, 17, tzinfo=UTC)


def _structured_output(phase: str, attempt_id: str) -> str:
    if phase == "wave0":
        return json.dumps(
            {
                "schema_version": 1,
                "sources": [
                    {
                        "source_id": "source:w0",
                        "canonical_url": "https://example.com/w0",
                        "title": "Wave0 source",
                        "fetch_status": "fetched",
                    }
                ],
                "baseline_facts": ["A supported fact."],
                "limitations": "",
            }
        )
    if phase == "wave1":
        return json.dumps(
            {
                "schema_version": 1,
                "sources": [
                    {
                        "source_id": "source:w1",
                        "canonical_url": "https://example.com/w1",
                        "title": "Wave1 source",
                    }
                ],
                "claims": [
                    {
                        "claim_id": "claim:w1_supported",
                        "statement": "The evidence supports this claim.",
                        "support_refs": ["source:w1"],
                        "counter_refs": [],
                    },
                    {
                        "claim_id": "claim:w1_contradicted",
                        "statement": "The evidence contradicts this claim.",
                        "support_refs": [],
                        "counter_refs": ["source:w1"],
                    },
                    {
                        "claim_id": "claim:w1_uncertain",
                        "statement": "The available evidence is uncertain.",
                        "support_refs": [],
                        "counter_refs": [],
                    },
                ],
                "open_questions": [
                    {
                        "question_id": "q:w1_uncertain",
                        "question": "What additional evidence would resolve uncertainty?",
                        "state": "targeted_search",
                    }
                ],
            }
        )
    return json.dumps(
        {
            "schema_version": 1,
            "gap_id": "gap:cost",
            "gap_status": "resolved",
            "sources": [
                {
                    "source_id": "source:targeted",
                    "canonical_url": "https://example.com/targeted",
                    "title": "Targeted source",
                }
            ],
            "limitations": "",
        }
    )


class _BridgeResolver:
    def __init__(self, graph: GraphContextView, bridge: RuntimeNodeAgentBridge) -> None:
        self.graph = graph
        self.bridge = bridge

    def resolve(self, *, logical_name, attempt_id, policy):
        return NodeBuildDependencies(
            graph_context=self.graph,
            agent_context=NodeAgentContext(
                research_scope_id=self.graph.research_scope_id,
                node_name=logical_name,
                attempt_id=attempt_id,
                workspace_root=self.graph.workspace_root,
                attempt_root=f"{self.graph.workspace_root}/attempts/{attempt_id}",
                policy_name=policy.name,
            ),
            capabilities=self.bridge,
        )


def _state(research_id: str) -> dict:
    return {
        "research_id": research_id,
        "generation": 0,
        "execution_trace": (),
        "pending_work_ids": (),
        "batch_cursor": 0,
        "next_work_ordinal": 0,
        "next_attempt_ordinal_by_work_id": {},
        "work_specs_by_id": {},
        "attempts_by_id": {},
        "work_status_by_id": {},
        "active_attempt_by_work_id": {},
        "terminal_failures_by_attempt_id": {},
        "accepted_submission_refs": (),
    }


@pytest.mark.workflow
@pytest.mark.parametrize(
    "phase",
    [
        pytest.param("wave0", id="quick-factual"),
        pytest.param("targeted_evidence", id="targeted_evidence"),
        pytest.param("wave1", id="claim-verification"),
    ],
)
async def test_scripted_worker_traverses_real_bridge_tool_policy_artifacts_and_ledger(
    tmp_path: Path,
    phase: str,
) -> None:
    identity = unique_run_identity()
    envelope = local_runtime_envelope(tmp_path, identity=identity)
    workspace = f"/mnt/user-data/workspace/deep-research/{identity.research_id}"
    graph = GraphContextView(
        research_scope_id=identity.research_id,
        workspace_root=workspace,
        uploads_root="/mnt/user-data/uploads",
        outputs_root=f"/mnt/user-data/outputs/deep-research/{identity.research_id}",
    )
    search = ScriptedTool.create("web_search", "fixed search result")
    responses = [
        ai_message(tool_calls=[{"name": "web_search", "args": {"query": phase}, "id": f"{phase}-search"}]),
    ]
    if phase == "wave0":
        responses.append(ai_message("I found a source, but this draft is not valid JSON."))
    responses.append(ai_message(_structured_output(phase, "a00")))
    model = ScriptedChatModel(responses=responses)
    policy = ExecutionPolicy(
        policy_name=f"{phase.replace('_', '-')}-scripted-worker",
        allowed_tool_names=frozenset({"web_search"}),
        read_roots=(workspace,),
        write_roots=(),
        attempt_root=workspace,
        budget=ExecutionBudget(3, 3, 1, 1, 16_384, 2_048, 4_096, 8_192, 5),
        tool_specs=(ToolPolicySpec("web_search", "read", native_cancellable=True),),
    )
    bridge = RuntimeNodeAgentBridge(
        envelope=envelope,
        policy=policy,
        model_resolver=lambda _envelope: model,
        tools_resolver=lambda _envelope, _policy: (search.as_langchain_tool(),),
    )
    store = WorkUnitStore(
        workspace_host_path=envelope.workspace_host_path,
        research_id=identity.research_id,
        clock=lambda: datetime.now(UTC),
        monotonic=time.monotonic,
        lock_sleep=time.sleep,
        token_factory=lambda: "8" * 32,
        fault_hook=None,
    )
    controller = WorkUnitControllerDependencies(
        store=store,
        resolver=RuntimeWorkUnitDependencyResolver(graph, _BridgeResolver(graph, bridge), store),
    )
    state = _state(identity.research_id)
    topic = ({"topic_id": "storage", "title": "Storage", "scope": "Storage economics"},)

    if phase == "wave0":
        result = await run_wave0_work_units_real(
            state,
            controller=controller,
            topic_registry=topic,
            clock=lambda: NOW,
        )
        accepted = result.parent_update["accepted_submission_refs"]
    elif phase == "wave1":
        result = await run_wave1_work_units_real(
            state,
            controller=controller,
            topic_registry=topic,
            capabilities=bridge,
            wave0_urls=frozenset(),
            clock=lambda: NOW,
        )
        accepted = result.parent_update["accepted_submission_refs"]
    else:
        dependencies = NodeBuildDependencies(
            graph_context=graph,
            agent_context=NodeAgentContext(
                research_scope_id=identity.research_id,
                node_name="targeted_evidence",
                attempt_id="g0-targeted-evidence-a1",
                workspace_root=workspace,
                attempt_root=f"{workspace}/attempts/targeted-evidence",
                policy_name=policy.policy_name,
            ),
            capabilities=bridge,
            work_units=controller,
        )
        update = await TARGETED_SPEC.real_factory(dependencies)(
            state
            | {
                "unresolved_gaps": ("gap:cost",),
                "critic_work_items": (),
            }
        )
        accepted = update["accepted_submission_refs"]

    records = await store.load_records()
    assert len(search.calls) == 1
    assert model.calls == (3 if phase == "wave0" else 2)
    assert len(accepted) == 1
    assert len(records) == 1
    assert records[0].source_refs[0].content_ref.endswith("/cache/source-0.json")
    if phase == "wave0":
        record = records[0]
        validate_script_observation(
            QUICK_FACTUAL_CASE.inputs,
            QUICK_FACTUAL_CASE.bounds,
            ScriptExecutionObservation(
                model_calls=model.calls,
                tool_calls=(ObservedToolCall("web_search", (("query", "wave0"),)),),
                bound_tool_names=("web_search",),
            ),
        )
        assertion = assert_scenario(
            QUICK_FACTUAL_FAMILY,
            QUICK_FACTUAL_CASE,
            ScenarioObservation(
                checkpoint=CheckpointFacts(route=None, terminal=None, identity_isolated=True, attempt_count=1),
                ledger=LedgerFacts(
                    accepted_refs=(record.record_hash,),
                    conflict_detected=False,
                    replay_idempotent=True,
                ),
                sandbox=SandboxFacts(
                    paths_contained=True,
                    artifact_hashes=((record.result_ref, record.result_hash),),
                    citation_bindings=(("quick-factual-answer", (record.record_hash,)),),
                ),
                diagnostic_codes=("accepted",),
            ),
        )
        assert assertion.case_id == "quick-factual"
    elif phase == "wave1":
        record = records[0]
        persisted = json.loads(await store.read_canonical_bytes(record.result_ref, max_bytes=256 * 1024))
        claims = {claim["claim_id"]: claim for claim in persisted["claims"]}
        assert persisted["open_questions"] == [
            {
                "question": "What additional evidence would resolve uncertainty?",
                "question_id": "q:w1_uncertain",
                "state": "targeted_search",
            }
        ]
        validate_script_observation(
            CLAIM_VERIFICATION_CASE.inputs,
            CLAIM_VERIFICATION_CASE.bounds,
            ScriptExecutionObservation(
                model_calls=model.calls,
                tool_calls=(ObservedToolCall("web_search", (("query", "wave1"),)),),
                bound_tool_names=("web_search",),
            ),
        )
        source_id = record.source_refs[0].source_id
        assertion = assert_scenario(
            CLAIM_VERIFICATION_FAMILY,
            CLAIM_VERIFICATION_CASE,
            ScenarioObservation(
                checkpoint=CheckpointFacts(route=None, terminal=None, identity_isolated=True, attempt_count=1),
                ledger=LedgerFacts((record.record_hash,), False, True),
                sandbox=SandboxFacts(True, ((record.result_ref, record.result_hash),), ()),
                diagnostic_codes=("accepted",),
                evidence_facts=(
                    LabeledEvidenceFact(
                        "claim:w1_supported",
                        EvidenceState.SUPPORTED,
                        tuple(claims["claim:w1_supported"]["support_refs"]),
                    ),
                    LabeledEvidenceFact(
                        "claim:w1_contradicted",
                        EvidenceState.CONTRADICTED,
                        tuple(claims["claim:w1_contradicted"]["counter_refs"]),
                    ),
                    LabeledEvidenceFact("claim:w1_uncertain", EvidenceState.UNCERTAIN, ()),
                ),
            ),
        )
        assert source_id in claims["claim:w1_supported"]["support_refs"]
        assert source_id in claims["claim:w1_contradicted"]["counter_refs"]
        assert assertion.case_id == "claim-verification"
