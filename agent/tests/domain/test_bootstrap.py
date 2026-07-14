"""Red tests for the bootstrap marker contract, store protocol, and binding validation.

@impl BON-001
@impl BON-002
"""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from deerflow_deep_research.domain.bootstrap import (
    BOOTSTRAP_MARKER_SCHEMA_VERSION,
    BootstrapBundleStoreProtocol,
    BootstrapMarker,
    validate_bootstrap_binding,
)
from deerflow_deep_research.domain.bundle import MARKER_FILENAME, marker_path
from deerflow_deep_research.domain.failure_codes import FailureCode

_RID = "r_" + "a" * 43
_DIGEST = "d_" + "b" * 43
_MID = "human-start"


def _marker(
    *,
    research_id: str = _RID,
    start_message_id: str = _MID,
    request_digest: str = _DIGEST,
    state_schema_version: int = 2,
) -> BootstrapMarker:
    return BootstrapMarker(
        research_id=research_id,
        start_message_id=start_message_id,
        request_digest=request_digest,
        state_schema_version=state_schema_version,
    )


def _checkpoint(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "research_id": _RID,
        "start_message_id": _MID,
        "request_digest": _DIGEST,
        "schema_version": 2,
    }
    base.update(overrides)
    return base


class TestBootstrapMarker:
    def test_valid_marker_is_frozen_and_extra_forbid(self) -> None:
        marker = _marker()
        assert marker.schema_version == BOOTSTRAP_MARKER_SCHEMA_VERSION == 1
        with pytest.raises(ValidationError):
            marker.research_id = "x"  # type: ignore[misc]
        with pytest.raises(ValidationError):
            BootstrapMarker.model_validate(
                {
                    "research_id": _RID,
                    "start_message_id": _MID,
                    "request_digest": _DIGEST,
                    "state_schema_version": 2,
                    "extra": "unwanted",
                }
            )

    @pytest.mark.parametrize(
        "field,value",
        [
            ("research_id", "not_a_research_id"),
            ("research_id", "r_short"),
            ("request_digest", "not_a_digest"),
            ("request_digest", "d_short"),
            ("start_message_id", ""),
            ("state_schema_version", 0),
            ("state_schema_version", 100),
        ],
    )
    def test_invalid_fields_are_rejected(self, field: str, value: object) -> None:
        with pytest.raises(ValidationError):
            _marker(**{field: value})

    def test_unsupported_marker_schema_version_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            BootstrapMarker.model_validate(
                {
                    "schema_version": 2,
                    "research_id": _RID,
                    "start_message_id": _MID,
                    "request_digest": _DIGEST,
                    "state_schema_version": 2,
                }
            )

    def test_canonical_json_round_trip_is_stable(self) -> None:
        marker = _marker()
        encoded = marker.canonical_json()
        assert isinstance(encoded, bytes)
        # Canonical: sorted keys, compact separators.
        assert encoded == json.dumps(
            {
                "schema_version": 1,
                "research_id": _RID,
                "start_message_id": _MID,
                "request_digest": _DIGEST,
                "state_schema_version": 2,
            },
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
        assert BootstrapMarker.from_canonical_json(encoded) == marker
        assert BootstrapMarker.from_canonical_json(encoded.decode("utf-8")) == marker

    @pytest.mark.parametrize("payload", ["not json", "{", "[]", "42"])
    def test_invalid_canonical_json_is_rejected(self, payload: str) -> None:
        with pytest.raises(ValueError, match="marker_json_invalid"):
            BootstrapMarker.from_canonical_json(payload)


class TestBootstrapBundleStoreProtocol:
    def test_implementer_is_recognized(self) -> None:
        class _Store:
            async def establish_bundle(self, marker: BootstrapMarker) -> None: ...

            async def read_marker(self) -> BootstrapMarker | None: ...

        assert isinstance(_Store(), BootstrapBundleStoreProtocol)

    def test_non_implementer_is_rejected(self) -> None:
        class _NotAStore:
            async def establish_bundle(self, marker: BootstrapMarker) -> None: ...

        assert not isinstance(_NotAStore(), BootstrapBundleStoreProtocol)


class TestValidateBootstrapBinding:
    def test_bound_marker_returns_none(self) -> None:
        assert validate_bootstrap_binding(_marker(), _checkpoint()) is None

    @pytest.mark.parametrize(
        "field,checkpoint_value",
        [
            ("research_id", "r_" + "z" * 43),
            ("start_message_id", "human-other"),
            ("request_digest", "d_" + "z" * 43),
        ],
    )
    def test_identity_mismatch_is_failure(self, field: str, checkpoint_value: object) -> None:
        failure = validate_bootstrap_binding(_marker(), _checkpoint(**{field: checkpoint_value}))
        assert failure is not None
        assert failure.code is FailureCode.IDENTITY_MISMATCH

    def test_state_schema_version_mismatch_is_failure(self) -> None:
        failure = validate_bootstrap_binding(_marker(), _checkpoint(schema_version=3))
        assert failure is not None
        assert failure.code is FailureCode.SCHEMA_VERSION_UNSUPPORTED

    def test_non_marker_raises_type_error(self) -> None:
        with pytest.raises(TypeError):
            validate_bootstrap_binding("not a marker", _checkpoint())  # type: ignore[arg-type]


class TestMarkerPath:
    def test_marker_path_is_under_request_subtree(self) -> None:
        assert marker_path(_RID) == f"workspace/deep-research/{_RID}/request/{MARKER_FILENAME}"
