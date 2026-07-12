"""Nested checkpoint namespace derivation contract (RUI-003)."""

from __future__ import annotations

import pytest

from deerflow_deep_research.runtime.checkpoint import (
    INFRA_PROBE_CHECKPOINT_NS,
    INFRA_PROBE_GRAPH,
    CheckpointNamespaceError,
    derive_probe_thread_key,
    validate_probe_key_schema,
)

SCOPE = {"effective_user_id": "alice", "outer_thread_id": "thread-1", "probe_id": "p-abc"}


def test_same_scope_is_deterministic() -> None:
    assert derive_probe_thread_key(**SCOPE) == derive_probe_thread_key(**SCOPE)


@pytest.mark.parametrize("field", ["effective_user_id", "outer_thread_id", "probe_id"])
def test_distinct_scope_component_changes_key(field: str) -> None:
    other = {**SCOPE, field: SCOPE[field] + "-x"}
    assert derive_probe_thread_key(**SCOPE) != derive_probe_thread_key(**other)


def test_length_prefix_removes_delimiter_ambiguity() -> None:
    left = derive_probe_thread_key(effective_user_id="ab", outer_thread_id="c", probe_id="p")
    right = derive_probe_thread_key(effective_user_id="a", outer_thread_id="bc", probe_id="p")
    assert left != right


def test_key_is_domain_separated_from_outer_thread() -> None:
    key = derive_probe_thread_key(**SCOPE)
    assert key.startswith(f"deep-research/{INFRA_PROBE_GRAPH}:")
    # The nested probe key never collides with the outer lead-agent thread id.
    assert key != SCOPE["outer_thread_id"]
    assert SCOPE["outer_thread_id"] not in key.split(":", 1)[1]


@pytest.mark.parametrize("field", ["effective_user_id", "outer_thread_id", "probe_id"])
def test_empty_scope_component_is_rejected(field: str) -> None:
    bad = {**SCOPE, field: ""}
    with pytest.raises(CheckpointNamespaceError) as excinfo:
        derive_probe_thread_key(**bad)
    assert excinfo.value.code == "scope_invalid"


def test_derive_takes_no_caller_supplied_digest() -> None:
    # The digest is an internal key: the only inputs are trusted scope + opaque
    # probe id, so a caller cannot inject a precomputed checkpoint key.
    import inspect

    params = set(inspect.signature(derive_probe_thread_key).parameters)
    assert params == {"effective_user_id", "outer_thread_id", "probe_id"}


def test_checkpoint_namespace_is_a_fixed_versioned_constant() -> None:
    assert INFRA_PROBE_CHECKPOINT_NS == f"{INFRA_PROBE_GRAPH}/v1"


def test_supported_schema_accepts_current_and_rejects_unknown() -> None:
    assert validate_probe_key_schema(1) == 1
    with pytest.raises(CheckpointNamespaceError) as excinfo:
        validate_probe_key_schema(2)
    assert excinfo.value.code == "schema_unsupported"
