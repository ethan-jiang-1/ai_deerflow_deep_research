from __future__ import annotations

import pytest

from deerflow_deep_research.domain.bundle import (
    BundlePathKind,
    attempt_dir,
    bundle_ref_to_virtual,
    classify_bundle_path,
    evidence_ledger_path,
    evidence_lock_path,
    evidence_staging_path,
    first_work_spec_path,
    is_audit_only,
    output_path,
    prelaunch_fs_probe_names,
    profile_path,
    relative_to_workspace_path,
    resolve_contained_path,
    result_path,
    runtime_alias_probe_path,
    runtime_fs_probe_paths,
    work_spec_path,
)
from deerflow_deep_research.domain.profile import RequestBundleStoreProtocol, ResearchProfile
from deerflow_deep_research.domain.state import ContentRef

RESEARCH_ID = "r_" + "A" * 43
WORK_ID = "g0_wave0_w0000"
ATTEMPT_ID = f"{WORK_ID}_a00"
TOKEN = "a" * 32


def test_canonical_attempt_artifact_paths_are_exact() -> None:
    root = f"workspace/deep-research/{RESEARCH_ID}/work/{WORK_ID}/{ATTEMPT_ID}"
    assert attempt_dir(RESEARCH_ID, WORK_ID, ATTEMPT_ID) == root
    assert work_spec_path(RESEARCH_ID, WORK_ID, ATTEMPT_ID) == f"{root}/work-spec.json"
    assert first_work_spec_path(RESEARCH_ID, WORK_ID) == f"{root}/work-spec.json"
    assert result_path(RESEARCH_ID, WORK_ID, ATTEMPT_ID) == f"{root}/result.json"
    assert output_path(RESEARCH_ID, WORK_ID, ATTEMPT_ID, "claims/a.json") == f"{root}/outputs/claims/a.json"


def test_ledger_lock_and_staging_paths_are_exact() -> None:
    evidence = f"workspace/deep-research/{RESEARCH_ID}/evidence"
    assert evidence_ledger_path(RESEARCH_ID) == f"{evidence}/submissions.jsonl"
    assert evidence_lock_path(RESEARCH_ID) == f"{evidence}/.submissions.lock"
    assert evidence_staging_path(RESEARCH_ID, TOKEN) == f"{evidence}/.submissions.{TOKEN}.tmp"
    with pytest.raises(ValueError, match="probe_token"):
        evidence_staging_path(RESEARCH_ID, "A" * 32)


def test_runtime_and_prelaunch_probe_names_share_exact_tokens() -> None:
    diagnostics = f"workspace/deep-research/{RESEARCH_ID}/diagnostics"
    assert runtime_alias_probe_path(RESEARCH_ID, TOKEN) == f"{diagnostics}/.work-unit-probe-{TOKEN}"
    assert runtime_fs_probe_paths(RESEARCH_ID, TOKEN) == (
        f"{diagnostics}/.work-unit-fsprobe-{TOKEN}.lock",
        f"{diagnostics}/.work-unit-fsprobe-{TOKEN}.src",
        f"{diagnostics}/.work-unit-fsprobe-{TOKEN}.dst",
    )
    assert prelaunch_fs_probe_names(TOKEN) == (
        f".deep-research-work-unit-fsprobe-{TOKEN}.lock",
        f".deep-research-work-unit-fsprobe-{TOKEN}.src",
        f".deep-research-work-unit-fsprobe-{TOKEN}.dst",
    )


def test_bundle_relative_virtual_and_workspace_relative_conversion() -> None:
    ref = result_path(RESEARCH_ID, WORK_ID, ATTEMPT_ID)
    assert bundle_ref_to_virtual(ref) == f"/mnt/user-data/{ref}"
    assert relative_to_workspace_path(ref) == f"deep-research/{RESEARCH_ID}/work/{WORK_ID}/{ATTEMPT_ID}/result.json"
    with pytest.raises(ValueError, match="bundle_ref"):
        bundle_ref_to_virtual("/tmp/host-secret")


@pytest.mark.parametrize(
    "bad",
    [
        "../result.json",
        "/result.json",
        "outputs/../result.json",
        "outputs//result.json",
        "outputs/./result.json",
        "outputs\\result.json",
    ],
)
def test_output_path_rejects_noncanonical_or_escaping_relative_paths(bad: str) -> None:
    with pytest.raises(ValueError, match="output"):
        output_path(RESEARCH_ID, WORK_ID, ATTEMPT_ID, bad)


def test_work_attempt_identity_mismatch_is_rejected() -> None:
    with pytest.raises(ValueError, match="attempt_id"):
        attempt_dir(RESEARCH_ID, WORK_ID, "g0_wave0_w0001_a00")
    with pytest.raises(ValueError, match="work_id"):
        attempt_dir(RESEARCH_ID, "loose-work", ATTEMPT_ID)


def test_containment_rejects_absolute_host_and_cross_attempt_paths() -> None:
    allowed = result_path(RESEARCH_ID, WORK_ID, ATTEMPT_ID)
    assert (
        resolve_contained_path(
            allowed,
            research_id=RESEARCH_ID,
            work_id=WORK_ID,
            attempt_id=ATTEMPT_ID,
        )
        == allowed
    )
    for path in ("/etc/passwd", f"workspace/deep-research/{RESEARCH_ID}/evidence/submissions.jsonl"):
        with pytest.raises(ValueError, match="path_not_contained"):
            resolve_contained_path(
                path,
                research_id=RESEARCH_ID,
                work_id=WORK_ID,
                attempt_id=ATTEMPT_ID,
            )


def test_probe_paths_are_audit_only_and_never_authority() -> None:
    alias = runtime_alias_probe_path(RESEARCH_ID, TOKEN)
    fs_lock, _, _ = runtime_fs_probe_paths(RESEARCH_ID, TOKEN)
    assert is_audit_only(alias)
    assert is_audit_only(fs_lock)
    assert classify_bundle_path(alias) is BundlePathKind.AUDIT
    assert classify_bundle_path(evidence_ledger_path(RESEARCH_ID)) is BundlePathKind.EVIDENCE
    assert classify_bundle_path(result_path(RESEARCH_ID, WORK_ID, ATTEMPT_ID)) is BundlePathKind.CONTENT


def test_profile_path_is_request_scoped_content() -> None:
    path = profile_path(RESEARCH_ID)
    assert path == f"workspace/deep-research/{RESEARCH_ID}/request/profile.json"
    assert classify_bundle_path(path) is BundlePathKind.CONTENT
    assert resolve_contained_path(path, research_id=RESEARCH_ID) == path
    with pytest.raises(ValueError, match="research_id"):
        profile_path("not-a-research-id")


def test_request_bundle_store_protocol_is_pure_and_runtime_checkable() -> None:
    class Store:
        async def write_profile(self, profile: ResearchProfile) -> ContentRef:
            return ContentRef(sandbox_path=profile_path(RESEARCH_ID), content_hash="h_" + "A" * 43)

    assert isinstance(Store(), RequestBundleStoreProtocol)
    assert "host" not in RequestBundleStoreProtocol.write_profile.__annotations__


@pytest.mark.parametrize("name", ["queue.json", "index.json", "status.json", "claims.queue"])
def test_dpt_control_files_are_not_registered_bundle_paths(name: str) -> None:
    path = f"workspace/deep-research/{RESEARCH_ID}/work/{name}"
    assert classify_bundle_path(path) is BundlePathKind.UNKNOWN
