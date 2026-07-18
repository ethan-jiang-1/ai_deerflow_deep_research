"""Late-node live seed builders publish only through validated store boundaries.

@impl EVH-005
@impl EVH-007
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

from deerflow_deep_research.domain.bundle import evidence_ledger_path, synthesis_findings_path
from deerflow_deep_research.domain.state import validate_research_state
from deerflow_deep_research.domain.synthesis import SynthesisResult
from deerflow_deep_research.domain.wave1 import Wave1SourceIntakeResult
from deerflow_deep_research.domain.work_units import (
    Wave0SourceIntakeResult,
    compute_record_hash,
    parse_submission_ledger,
)
from tests.fixtures.live_seeds import build_live_seed_bundle


async def test_wave0_seed_publishes_validated_authority_and_compact_checkpoint(tmp_path) -> None:
    seeded = await build_live_seed_bundle(tmp_path, include_wave1=False)
    checkpoint = validate_research_state(seeded.checkpoint)
    records = await seeded.store.load_records()

    assert checkpoint.accepted_submission_refs == (records[0].record_hash,)
    assert len(records) == 1
    assert records[0].phase.value == "wave0"
    assert records[0].source_refs[0].canonical_url == "https://example.invalid/wave0"
    assert await seeded.store.read_canonical_bytes(records[0].result_ref, max_bytes=16_384)
    assert "Synthetic Wave0 evidence body" not in json.dumps(seeded.checkpoint)


async def test_wave0_wave1_seed_uses_real_ledger_chain_and_contained_artifacts(tmp_path) -> None:
    seeded = await build_live_seed_bundle(tmp_path, include_wave1=True)
    records = await seeded.store.load_records()
    ledger = await seeded.store.read_canonical_bytes(evidence_ledger_path(seeded.research_id), max_bytes=128 * 1024)
    parsed = parse_submission_ledger(ledger)

    assert parsed == records
    assert all(compute_record_hash(record) == record.record_hash for record in records)
    assert tuple(record.phase.value for record in records) == ("wave0", "wave1")
    assert records[1].previous_record_hash == records[0].record_hash
    assert seeded.checkpoint["accepted_submission_refs"] == tuple(record.record_hash for record in records)
    assert seeded.checkpoint["topic_registry"] == (
        {
            "topic_id": "storage",
            "title": "Synthetic storage",
            "scope": "Synthetic storage evidence",
            "must_answer_bindings": ("What supports the synthetic finding?",),
        },
    )
    assert all(
        ref.content_ref.startswith(f"workspace/deep-research/{seeded.research_id}/work/")
        for record in records
        for ref in record.source_refs
    )
    wave0_result = await seeded.store.read_canonical_bytes(records[0].result_ref, max_bytes=16_384)
    wave1_result = await seeded.store.read_canonical_bytes(records[1].result_ref, max_bytes=16_384)
    assert Wave0SourceIntakeResult.model_validate_json(wave0_result).schema_version == 1
    assert Wave1SourceIntakeResult.model_validate_json(wave1_result).schema_version == 1
    for record in records:
        for source in record.source_refs:
            assert await seeded.store.read_canonical_bytes(source.content_ref, max_bytes=16_384)


async def test_seed_replay_is_idempotent_through_submit_boundary(tmp_path) -> None:
    first = await build_live_seed_bundle(tmp_path, include_wave1=True)
    first_hashes = tuple(record.record_hash for record in await first.store.load_records())
    replay = await build_live_seed_bundle(tmp_path, research_id=first.research_id, include_wave1=True)
    assert tuple(record.record_hash for record in await replay.store.load_records()) == first_hashes


async def test_targeted_seed_publishes_valid_synthesis_and_dispatch_projection(tmp_path) -> None:
    seeded = await build_live_seed_bundle(tmp_path, include_wave1=True, include_synthesis_gap=True)
    artifact = await seeded.store.read_canonical_bytes(synthesis_findings_path(seeded.research_id), max_bytes=16_384)
    synthesis = SynthesisResult.model_validate_json(artifact)

    assert len(synthesis.gaps) == 1
    gap = synthesis.gaps[0]
    assert gap.gap_id == "gap:focused-targeted"
    assert seeded.synthesis_gaps == (
        {
            **gap.model_dump(mode="python"),
            "search_required": True,
        },
    )
    assert "synthesis_gaps" not in seeded.checkpoint
    assert validate_research_state(seeded.checkpoint).research_id == seeded.research_id


def test_seed_builder_never_fabricates_ledger_lines() -> None:
    source = (Path(__file__).parents[1] / "fixtures/live_seeds.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    calls = [node.func for node in ast.walk(tree) if isinstance(node, ast.Call)]
    names = [
        function.id if isinstance(function, ast.Name) else function.attr
        for function in calls
        if isinstance(function, (ast.Name, ast.Attribute))
    ]
    string_constants = {
        node.value for node in ast.walk(tree) if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }
    assert names.count("submit_candidate_if_active") == 2
    assert not {"encode_submission_ledger", "parse_submission_ledger", "write_bytes", "write_text"} & set(names)
    assert "submissions.jsonl" not in string_constants
