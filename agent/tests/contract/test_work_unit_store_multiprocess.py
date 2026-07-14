from __future__ import annotations

import asyncio
import multiprocessing
import time
from datetime import UTC, datetime
from pathlib import Path

from deerflow_deep_research.domain.work_units import (
    CandidateResult,
    compute_candidate_hash,
    compute_work_spec_hash,
    parse_submission_ledger,
)
from deerflow_deep_research.runtime.work_unit_store import WorkUnitStore

RESEARCH_ID = "r_" + "M" * 43
NOW = datetime(2026, 7, 14, tzinfo=UTC)


def _candidate(*, attempt_ordinal: int = 0, result_marker: str = "B") -> CandidateResult:
    work_id = "g0_wave0_w0000"
    attempt_id = f"{work_id}_a{attempt_ordinal:02d}"
    spec = {
        "schema_version": 1,
        "research_id": RESEARCH_ID,
        "generation": 0,
        "phase": "wave0",
        "work_id": work_id,
        "work_ordinal": 0,
        "worker_role": "fixture_worker",
        "scope": ("multiprocess",),
        "result_contract": "fixture.work-unit",
        "result_schema_version": 1,
        "required_outputs": (),
    }
    root = f"workspace/deep-research/{RESEARCH_ID}/work/{work_id}/{attempt_id}"
    payload = {
        "schema_version": 1,
        "research_id": RESEARCH_ID,
        "generation": 0,
        "phase": "wave0",
        "work_id": work_id,
        "attempt_id": attempt_id,
        "worker_role": "fixture_worker",
        "spec_hash": compute_work_spec_hash(spec),
        "result_contract": "fixture.work-unit",
        "result_ref": f"{root}/result.json",
        "result_hash": "h_" + result_marker * 43,
        "result_schema_version": 1,
        "result_byte_count": 10,
        "output_refs": (),
        "source_refs": (),
    }
    payload["candidate_hash"] = compute_candidate_hash(payload)
    return CandidateResult.model_validate(payload)


def _submit_process(workspace: str, candidate_payload: dict, start, results) -> None:
    async def run() -> None:
        store = WorkUnitStore(
            workspace_host_path=Path(workspace),
            research_id=RESEARCH_ID,
            clock=lambda: NOW,
            monotonic=time.monotonic,
            lock_sleep=time.sleep,
            token_factory=lambda: multiprocessing.current_process().name[-1].lower().zfill(32),
            fault_hook=None,
        )
        candidate = CandidateResult.model_validate(candidate_payload)
        await asyncio.to_thread(start.wait, 5)
        try:
            commit = await store.commit_candidate(candidate, scope=("multiprocess",))
        except Exception as exc:  # serialized test evidence only
            results.put(("error", type(exc).__name__, str(exc)))
        else:
            results.put((commit.disposition.value, commit.record.record_hash, commit.record.attempt_id))

    asyncio.run(run())


def _race(tmp_path: Path, candidates: tuple[CandidateResult, CandidateResult]) -> list[tuple[str, str, str]]:
    context = multiprocessing.get_context("spawn")
    start = context.Event()
    results = context.Queue()
    processes = [
        context.Process(
            target=_submit_process,
            name=f"submit{i}",
            args=(str(tmp_path), candidate.model_dump(mode="json"), start, results),
        )
        for i, candidate in enumerate(candidates)
    ]
    for process in processes:
        process.start()
    start.set()
    observed = [results.get(timeout=10) for _ in processes]
    for process in processes:
        process.join(timeout=10)
        assert process.exitcode == 0
    return observed


def _ledger(tmp_path: Path):
    path = tmp_path / "deep-research" / RESEARCH_ID / "evidence" / "submissions.jsonl"
    data = path.read_bytes()
    assert data.endswith(b"\n")
    assert b"\r" not in data
    assert b"\n\n" not in data
    return parse_submission_ledger(data)


def test_independent_processes_race_same_candidate_to_one_record(tmp_path: Path) -> None:
    observed = _race(tmp_path, (_candidate(), _candidate()))
    assert {item[0] for item in observed} == {"appended", "replayed"}
    assert len({item[1] for item in observed}) == 1
    assert len(_ledger(tmp_path)) == 1


def test_independent_processes_race_divergent_candidates_without_partial_line(tmp_path: Path) -> None:
    observed = _race(tmp_path, (_candidate(result_marker="B"), _candidate(result_marker="C")))
    assert sum(item[0] == "appended" for item in observed) == 1
    assert sum(item[0] == "error" and item[1] == "ValueError" for item in observed) == 1
    assert len(_ledger(tmp_path)) == 1


def test_independent_processes_race_sibling_attempts_without_newest_priority_claim(tmp_path: Path) -> None:
    observed = _race(tmp_path, (_candidate(attempt_ordinal=0), _candidate(attempt_ordinal=1)))
    assert {item[0] for item in observed} == {"appended", "work_already_accepted"}
    records = _ledger(tmp_path)
    assert len(records) == 1
    assert records[0].attempt_id in {"g0_wave0_w0000_a00", "g0_wave0_w0000_a01"}
