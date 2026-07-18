"""Bounded provider-shape cases and discovery disposition contracts.

@impl EVH-010
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from tests.assets.evidence import TestEvidenceClaim

MAX_CORPUS_BYTES = 256 * 1024
MAX_PAYLOAD_BYTES = 16 * 1024
MAX_PAYLOAD_DEPTH = 8
MAX_CASES = 128

CASE_ID_RE = re.compile(r"^[a-z][a-z0-9-]{2,63}$")
DISCOVERY_ID_RE = re.compile(r"^(?:LIVE|RELEASE)-\d{8}-\d{2}$")
CLAIM_ID_RE = re.compile(r"^[a-z][a-z0-9-]{2,95}$")
ERROR_CODE_RE = re.compile(r"^[a-z][a-z0-9_]{2,63}$")
DOMAIN_RE = re.compile(r"^(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$")
CREDENTIAL_KEY_RE = re.compile(r"(?i)(?:api[_-]?key|authorization|bearer|credential|password|secret|token)")
CREDENTIAL_VALUE_RE = re.compile(r"(?i)(?:sk-[a-z0-9_-]{8,}|bearer\s+[a-z0-9._~+/-]{8,})")
HOST_PATH_RE = re.compile(r"(?:/(?:Users|home)/[^/\s]+/|[A-Za-z]:\\Users\\[^\\\s]+\\)")


class FrozenJsonArray(tuple):
    """Tagged immutable JSON array, including the empty-array case."""


class FrozenJsonObject(tuple):
    """Tagged immutable JSON object, including the empty-object case."""


FrozenJson = None | bool | int | float | str | FrozenJsonArray | FrozenJsonObject | tuple["FrozenJson", ...]


class ProviderShapeExpectedKind(StrEnum):
    NORMALIZED = "normalized"
    FAIL_CLOSED = "fail_closed"


class DiscoveryDispositionKind(StrEnum):
    UNIFORM_SHAPE = "uniform_shape"
    EXISTING_REGRESSION = "existing_regression"
    PROVIDER_ONLY = "provider_only"


@dataclass(frozen=True)
class ProviderShapeSensitivity:
    synthetic_domain: str
    minimized_reviewed: bool
    contains_free_text: bool

    def __post_init__(self) -> None:
        if not isinstance(self.synthetic_domain, str) or not DOMAIN_RE.fullmatch(self.synthetic_domain):
            raise ValueError("shape_synthetic_domain_invalid")
        if not isinstance(self.minimized_reviewed, bool) or not isinstance(self.contains_free_text, bool):
            raise ValueError("shape_sensitivity_flags_invalid")
        if not self.minimized_reviewed:
            raise ValueError("shape_sensitivity_review_required")


@dataclass(frozen=True)
class ProviderShapeCase:
    case_id: str
    discovery_ids: tuple[str, ...]
    focused_node: str
    input_schema_version: int
    payload: FrozenJson
    expected_kind: ProviderShapeExpectedKind
    expected_payload: FrozenJson | None
    expected_error_code: str | None
    sensitivity: ProviderShapeSensitivity

    def __post_init__(self) -> None:
        if not isinstance(self.case_id, str) or not CASE_ID_RE.fullmatch(self.case_id):
            raise ValueError("shape_case_id_invalid")
        if (
            not isinstance(self.discovery_ids, tuple)
            or not self.discovery_ids
            or len(set(self.discovery_ids)) != len(self.discovery_ids)
            or any(not isinstance(value, str) or not DISCOVERY_ID_RE.fullmatch(value) for value in self.discovery_ids)
        ):
            raise ValueError("shape_discovery_ids_invalid")
        if self.focused_node not in {"wave0", "wave1", "wave2_synthesis"}:
            raise ValueError("shape_focused_node_invalid")
        if (
            not isinstance(self.input_schema_version, int)
            or isinstance(self.input_schema_version, bool)
            or not 1 <= self.input_schema_version <= 16
        ):
            raise ValueError("shape_input_schema_version_invalid")
        _validate_frozen_json(self.payload)
        if not _is_frozen_object(self.payload):
            raise ValueError("shape_payload_object_required")
        if _json_size(self.payload) > MAX_PAYLOAD_BYTES:
            raise ValueError("shape_payload_oversize")
        if not isinstance(self.expected_kind, ProviderShapeExpectedKind):
            raise ValueError("shape_expected_kind_invalid")
        if self.expected_kind is ProviderShapeExpectedKind.NORMALIZED:
            if (
                self.expected_payload is None
                or not _is_frozen_object(self.expected_payload)
                or self.expected_error_code is not None
            ):
                raise ValueError("shape_expected_normalized_invalid")
            _validate_frozen_json(self.expected_payload)
        elif self.expected_payload is not None or (
            not isinstance(self.expected_error_code, str) or not ERROR_CODE_RE.fullmatch(self.expected_error_code)
        ):
            raise ValueError("shape_expected_fail_closed_invalid")
        if not isinstance(self.sensitivity, ProviderShapeSensitivity):
            raise ValueError("shape_sensitivity_invalid")


@dataclass(frozen=True)
class DiscoveryDisposition:
    discovery_id: str
    kind: DiscoveryDispositionKind
    intended_case_id: str | None = None
    claim_id: str | None = None
    live_case_id: str | None = None
    rationale: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.discovery_id, str) or not DISCOVERY_ID_RE.fullmatch(self.discovery_id):
            raise ValueError("disposition_discovery_id_invalid")
        if not isinstance(self.kind, DiscoveryDispositionKind):
            raise ValueError("disposition_kind_invalid")
        supplied = {
            "intended_case_id": self.intended_case_id,
            "claim_id": self.claim_id,
            "live_case_id": self.live_case_id,
            "rationale": self.rationale,
        }
        required = {
            DiscoveryDispositionKind.UNIFORM_SHAPE: {"intended_case_id"},
            DiscoveryDispositionKind.EXISTING_REGRESSION: {"claim_id"},
            DiscoveryDispositionKind.PROVIDER_ONLY: {"live_case_id", "rationale"},
        }[self.kind]
        if {name for name, value in supplied.items() if value is not None} != required:
            raise ValueError("disposition_fields_invalid")
        if self.intended_case_id is not None and not CASE_ID_RE.fullmatch(self.intended_case_id):
            raise ValueError("disposition_case_id_invalid")
        if self.claim_id is not None and not CLAIM_ID_RE.fullmatch(self.claim_id):
            raise ValueError("disposition_claim_id_invalid")
        if self.live_case_id is not None and not CASE_ID_RE.fullmatch(self.live_case_id):
            raise ValueError("disposition_live_case_id_invalid")
        if self.rationale is not None and (
            not isinstance(self.rationale, str) or not 32 <= len(self.rationale.strip()) <= 512
        ):
            raise ValueError("disposition_rationale_invalid")


LIVE_DISCOVERY_DISPOSITIONS = (
    DiscoveryDisposition(
        discovery_id="LIVE-20260717-01",
        kind=DiscoveryDispositionKind.EXISTING_REGRESSION,
        claim_id="live-discovery-workspace-cleanup",
    ),
    DiscoveryDisposition(
        discovery_id="LIVE-20260717-02",
        kind=DiscoveryDispositionKind.EXISTING_REGRESSION,
        claim_id="live-discovery-model-construction",
    ),
    DiscoveryDisposition(
        discovery_id="LIVE-20260717-03",
        kind=DiscoveryDispositionKind.EXISTING_REGRESSION,
        claim_id="live-discovery-canary-precondition",
    ),
    DiscoveryDisposition(
        discovery_id="LIVE-20260717-04",
        kind=DiscoveryDispositionKind.EXISTING_REGRESSION,
        claim_id="live-discovery-wave0-prompt-contract",
    ),
    DiscoveryDisposition(
        discovery_id="LIVE-20260717-05",
        kind=DiscoveryDispositionKind.PROVIDER_ONLY,
        live_case_id="live-one-topic-wave0",
        rationale=(
            "Provider web-tool selection is a model decision distribution; scripted execution proves the policy path "
            "but cannot reproduce the probability of choosing the tool."
        ),
    ),
    DiscoveryDisposition(
        discovery_id="LIVE-20260717-06",
        kind=DiscoveryDispositionKind.EXISTING_REGRESSION,
        claim_id="live-discovery-tool-required",
    ),
)

RELEASE_DISCOVERY_DISPOSITIONS_01_14 = (
    DiscoveryDisposition(
        discovery_id="RELEASE-20260717-01",
        kind=DiscoveryDispositionKind.EXISTING_REGRESSION,
        claim_id="release-discovery-final-publication",
    ),
    DiscoveryDisposition(
        discovery_id="RELEASE-20260717-02",
        kind=DiscoveryDispositionKind.EXISTING_REGRESSION,
        claim_id="release-discovery-profile-budget",
    ),
    DiscoveryDisposition(
        discovery_id="RELEASE-20260717-03",
        kind=DiscoveryDispositionKind.UNIFORM_SHAPE,
        intended_case_id="shape-wave0-url-canonicalization",
    ),
    DiscoveryDisposition(
        discovery_id="RELEASE-20260717-04",
        kind=DiscoveryDispositionKind.UNIFORM_SHAPE,
        intended_case_id="shape-wave0-fetch-status-alias",
    ),
    DiscoveryDisposition(
        discovery_id="RELEASE-20260717-05",
        kind=DiscoveryDispositionKind.UNIFORM_SHAPE,
        intended_case_id="shape-wave0-limitations-list",
    ),
    DiscoveryDisposition(
        discovery_id="RELEASE-20260717-06",
        kind=DiscoveryDispositionKind.EXISTING_REGRESSION,
        claim_id="wave1-worker-ledger-success",
    ),
    DiscoveryDisposition(
        discovery_id="RELEASE-20260717-07",
        kind=DiscoveryDispositionKind.UNIFORM_SHAPE,
        intended_case_id="shape-wave1-provider-identifiers",
    ),
    DiscoveryDisposition(
        discovery_id="RELEASE-20260717-08",
        kind=DiscoveryDispositionKind.EXISTING_REGRESSION,
        claim_id="release-discovery-wave2-structured-repair",
    ),
    DiscoveryDisposition(
        discovery_id="RELEASE-20260717-09",
        kind=DiscoveryDispositionKind.UNIFORM_SHAPE,
        intended_case_id="shape-wave2-provider-field-aliases",
    ),
    DiscoveryDisposition(
        discovery_id="RELEASE-20260717-10",
        kind=DiscoveryDispositionKind.EXISTING_REGRESSION,
        claim_id="release-discovery-topic-bound",
    ),
    DiscoveryDisposition(
        discovery_id="RELEASE-20260717-11",
        kind=DiscoveryDispositionKind.UNIFORM_SHAPE,
        intended_case_id="shape-wave2-gap-priority-alias",
    ),
    DiscoveryDisposition(
        discovery_id="RELEASE-20260717-12",
        kind=DiscoveryDispositionKind.UNIFORM_SHAPE,
        intended_case_id="shape-wave0-partial-source-degradation",
    ),
    DiscoveryDisposition(
        discovery_id="RELEASE-20260717-13",
        kind=DiscoveryDispositionKind.EXISTING_REGRESSION,
        claim_id="release-discovery-synthesis-semantic-floor",
    ),
    DiscoveryDisposition(
        discovery_id="RELEASE-20260717-14",
        kind=DiscoveryDispositionKind.EXISTING_REGRESSION,
        claim_id="release-discovery-readiness-provenance",
    ),
)

RELEASE_DISCOVERY_DISPOSITIONS_15_25 = (
    DiscoveryDisposition(
        discovery_id="RELEASE-20260717-15",
        kind=DiscoveryDispositionKind.EXISTING_REGRESSION,
        claim_id="release-discovery-visible-retry-trace",
    ),
    DiscoveryDisposition(
        discovery_id="RELEASE-20260717-16",
        kind=DiscoveryDispositionKind.EXISTING_REGRESSION,
        claim_id="release-discovery-dotenv-handoff",
    ),
    DiscoveryDisposition(
        discovery_id="RELEASE-20260717-17",
        kind=DiscoveryDispositionKind.EXISTING_REGRESSION,
        claim_id="release-discovery-redacted-schema-diagnostics",
    ),
    DiscoveryDisposition(
        discovery_id="RELEASE-20260717-18",
        kind=DiscoveryDispositionKind.UNIFORM_SHAPE,
        intended_case_id="shape-wave1-source-id-ref-rewrites",
    ),
    DiscoveryDisposition(
        discovery_id="RELEASE-20260717-19",
        kind=DiscoveryDispositionKind.UNIFORM_SHAPE,
        intended_case_id="shape-wave2-description-string-gaps",
    ),
    DiscoveryDisposition(
        discovery_id="RELEASE-20260717-20",
        kind=DiscoveryDispositionKind.UNIFORM_SHAPE,
        intended_case_id="shape-wave2-sparse-findings",
    ),
    DiscoveryDisposition(
        discovery_id="RELEASE-20260717-21",
        kind=DiscoveryDispositionKind.UNIFORM_SHAPE,
        intended_case_id="shape-wave1-source-order",
    ),
    DiscoveryDisposition(
        discovery_id="RELEASE-20260717-22",
        kind=DiscoveryDispositionKind.UNIFORM_SHAPE,
        intended_case_id="shape-wave2-relation-endpoints",
    ),
    DiscoveryDisposition(
        discovery_id="RELEASE-20260717-23",
        kind=DiscoveryDispositionKind.UNIFORM_SHAPE,
        intended_case_id="shape-wave2-singular-affected-topic",
    ),
    DiscoveryDisposition(
        discovery_id="RELEASE-20260717-24",
        kind=DiscoveryDispositionKind.UNIFORM_SHAPE,
        intended_case_id="shape-wave2-alternate-relation",
    ),
    DiscoveryDisposition(
        discovery_id="RELEASE-20260717-25",
        kind=DiscoveryDispositionKind.UNIFORM_SHAPE,
        intended_case_id="shape-wave2-missing-gap-identity",
    ),
)


def validate_discovery_dispositions(
    dispositions: tuple[DiscoveryDisposition, ...],
    *,
    required_discovery_ids: set[str],
    claims: dict[str, TestEvidenceClaim],
    live_case_ids: set[str],
) -> None:
    errors: list[str] = []
    observed = {item.discovery_id for item in dispositions}
    if len(observed) != len(dispositions):
        errors.append("disposition_discovery_id_duplicate")
    if observed != required_discovery_ids:
        errors.append(
            f"disposition_inventory_mismatch: missing={sorted(required_discovery_ids - observed)} "
            f"unknown={sorted(observed - required_discovery_ids)}"
        )
    live_claims_by_discovery = {
        discovery_id
        for claim in claims.values()
        if claim.expected_selection.value == "live"
        for discovery_id in claim.discovery_ids
    }
    for item in dispositions:
        if item.kind is DiscoveryDispositionKind.EXISTING_REGRESSION:
            claim = claims.get(item.claim_id or "")
            if claim is None:
                errors.append(f"{item.discovery_id}: disposition_claim_unknown")
            elif item.discovery_id not in claim.discovery_ids:
                errors.append(f"{item.discovery_id}: disposition_claim_provenance_missing")
        elif item.kind is DiscoveryDispositionKind.PROVIDER_ONLY:
            if item.live_case_id not in live_case_ids:
                errors.append(f"{item.discovery_id}: disposition_live_case_unknown")
            if item.discovery_id not in live_claims_by_discovery:
                errors.append(f"{item.discovery_id}: disposition_live_claim_missing")
    if errors:
        raise ValueError("\n".join(errors))


def validate_provider_shape_catalog(
    dispositions: tuple[DiscoveryDisposition, ...],
    *,
    cases: tuple[ProviderShapeCase, ...],
    required_discovery_ids: set[str],
    claims: dict[str, TestEvidenceClaim],
    collected_selectors: set[str],
    live_case_ids: set[str],
) -> None:
    """Close discovery, shape-case, claim, and collected-selector provenance."""
    validate_discovery_dispositions(
        dispositions,
        required_discovery_ids=required_discovery_ids,
        claims=claims,
        live_case_ids=live_case_ids,
    )
    errors: list[str] = []
    case_ids = [case.case_id for case in cases]
    if len(set(case_ids)) != len(case_ids):
        errors.append("shape_case_id_duplicate")
    case_index = {case.case_id: case for case in cases}
    disposition_index = {item.discovery_id: item for item in dispositions}

    for disposition in dispositions:
        if disposition.kind is DiscoveryDispositionKind.EXISTING_REGRESSION:
            claim = claims.get(disposition.claim_id or "")
            if claim is not None and claim.selector not in collected_selectors:
                errors.append(f"{disposition.discovery_id}: disposition_claim_selector_uncollected")
        elif disposition.kind is DiscoveryDispositionKind.PROVIDER_ONLY:
            live_claims = [claim for claim in claims.values() if disposition.discovery_id in claim.discovery_ids]
            if len(live_claims) == 1:
                live_claim = live_claims[0]
                if f"[{disposition.live_case_id}]" not in live_claim.selector:
                    errors.append(f"{disposition.discovery_id}: disposition_live_claim_case_mismatch")
                if live_claim.selector not in collected_selectors:
                    errors.append(f"{disposition.discovery_id}: disposition_live_claim_selector_uncollected")

    for case in cases:
        unknown = set(case.discovery_ids) - required_discovery_ids
        if unknown:
            errors.append(f"{case.case_id}: shape_case_discovery_unknown: {sorted(unknown)}")
        non_uniform = {
            discovery_id
            for discovery_id in case.discovery_ids
            if discovery_id in disposition_index
            and disposition_index[discovery_id].kind is not DiscoveryDispositionKind.UNIFORM_SHAPE
        }
        if non_uniform:
            errors.append(f"{case.case_id}: shape_case_discovery_not_uniform: {sorted(non_uniform)}")
        case_claims = [claim for claim in claims.values() if f"[{case.case_id}]" in claim.selector]
        if not case_claims:
            errors.append(f"{case.case_id}: shape_case_claim_missing")
            continue
        if len(case_claims) > 1:
            errors.append(f"{case.case_id}: shape_case_claim_duplicate")
            continue
        claim = case_claims[0]
        if claim.selector not in collected_selectors:
            errors.append(f"{case.case_id}: shape_case_selector_uncollected: {claim.selector}")
        if set(claim.discovery_ids) != set(case.discovery_ids):
            errors.append(f"{case.case_id}: shape_case_claim_provenance_mismatch")

    for disposition in dispositions:
        if disposition.kind is not DiscoveryDispositionKind.UNIFORM_SHAPE:
            continue
        case = case_index.get(disposition.intended_case_id or "")
        if case is None:
            errors.append(f"{disposition.discovery_id}: shape_intended_case_unresolved")
        elif disposition.discovery_id not in case.discovery_ids:
            errors.append(f"{disposition.discovery_id}: shape_intended_case_provenance_missing")
    if errors:
        raise ValueError("\n".join(errors))


def load_provider_shape_archive(root: Path) -> tuple[ProviderShapeCase, ...]:
    """Load every bounded JSON corpus in a non-empty provider-shape archive."""
    if not isinstance(root, Path):
        raise TypeError("shape_archive_path_required")
    paths = tuple(sorted(path for path in root.glob("*.json") if path.is_file()))
    if not paths:
        raise ValueError("shape_archive_empty")
    if sum(path.stat().st_size for path in paths) > MAX_CORPUS_BYTES:
        raise ValueError("shape_archive_oversize")
    cases = tuple(case for path in paths for case in load_provider_shape_cases(path))
    if len(cases) > MAX_CASES:
        raise ValueError("shape_archive_cases_oversize")
    if len({case.case_id for case in cases}) != len(cases):
        raise ValueError("shape_case_id_duplicate")
    return cases


def load_provider_shape_cases(path: Path) -> tuple[ProviderShapeCase, ...]:
    if not isinstance(path, Path):
        raise TypeError("shape_corpus_path_required")
    raw = path.read_bytes()
    if len(raw) > MAX_CORPUS_BYTES:
        raise ValueError("shape_corpus_oversize")
    try:
        loaded = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("shape_corpus_json_invalid") from exc
    if not isinstance(loaded, list) or not 1 <= len(loaded) <= MAX_CASES:
        raise ValueError("shape_corpus_cases_invalid")
    cases = tuple(_load_case(item) for item in loaded)
    if len({case.case_id for case in cases}) != len(cases):
        raise ValueError("shape_case_id_duplicate")
    return cases


def _load_case(value: object) -> ProviderShapeCase:
    required = {
        "case_id",
        "discovery_ids",
        "focused_node",
        "input_schema_version",
        "payload",
        "expected",
        "sensitivity",
    }
    if not isinstance(value, dict) or set(value) != required:
        raise ValueError("shape_case_fields_invalid")
    expected = value["expected"]
    sensitivity = value["sensitivity"]
    if not isinstance(expected, dict) or set(expected) not in (
        {"kind", "payload"},
        {"kind", "error_code"},
    ):
        raise ValueError("shape_expected_fields_invalid")
    if not isinstance(sensitivity, dict) or set(sensitivity) != {
        "synthetic_domain",
        "minimized_reviewed",
        "contains_free_text",
    }:
        raise ValueError("shape_sensitivity_fields_invalid")
    discovery_ids = value["discovery_ids"]
    if not isinstance(discovery_ids, list):
        raise ValueError("shape_discovery_ids_invalid")
    try:
        expected_kind = ProviderShapeExpectedKind(expected["kind"])
    except (KeyError, ValueError) as exc:
        raise ValueError("shape_expected_kind_invalid") from exc
    case = ProviderShapeCase(
        case_id=value["case_id"],
        discovery_ids=tuple(discovery_ids),
        focused_node=value["focused_node"],
        input_schema_version=value["input_schema_version"],
        payload=_freeze_json(value["payload"]),
        expected_kind=expected_kind,
        expected_payload=_freeze_json(expected["payload"]) if "payload" in expected else None,
        expected_error_code=expected.get("error_code"),
        sensitivity=ProviderShapeSensitivity(**sensitivity),
    )
    _validate_shape_sensitivity(case)
    return case


def _validate_shape_sensitivity(case: ProviderShapeCase) -> None:
    for path, value in _walk_json(_thaw_json(case.payload), path="payload"):
        _validate_shape_scalar(path, value, synthetic_domain=case.sensitivity.synthetic_domain)
    if case.expected_payload is not None:
        for path, value in _walk_json(_thaw_json(case.expected_payload), path="expected"):
            _validate_shape_scalar(path, value, synthetic_domain=case.sensitivity.synthetic_domain)


def _walk_json(value: Any, *, path: str):
    if isinstance(value, dict):
        for key, item in value.items():
            child_path = f"{path}.{key}"
            yield child_path, key
            yield from _walk_json(item, path=child_path)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from _walk_json(item, path=f"{path}[{index}]")
    elif isinstance(value, str):
        yield path, value


def _validate_shape_scalar(path: str, value: str, *, synthetic_domain: str) -> None:
    field_name = path.rsplit(".", 1)[-1]
    if CREDENTIAL_KEY_RE.search(field_name) or CREDENTIAL_VALUE_RE.search(value):
        raise ValueError("shape_credential_forbidden")
    if HOST_PATH_RE.search(value):
        raise ValueError("shape_raw_host_path_forbidden")
    parsed = urlsplit(value)
    if parsed.scheme.lower() in {"http", "https"} and (parsed.hostname or "").lower() != synthetic_domain.lower():
        raise ValueError("shape_external_url_forbidden")


def _freeze_json(value: Any, *, depth: int = 0) -> FrozenJson:
    if depth > MAX_PAYLOAD_DEPTH:
        raise ValueError("shape_payload_depth_invalid")
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, list):
        return FrozenJsonArray(_freeze_json(item, depth=depth + 1) for item in value)
    if isinstance(value, dict) and all(isinstance(key, str) for key in value):
        return FrozenJsonObject((key, _freeze_json(item, depth=depth + 1)) for key, item in value.items())
    raise ValueError("shape_payload_type_invalid")


def _thaw_json(value: FrozenJson) -> Any:
    if isinstance(value, FrozenJsonObject):
        return {key: _thaw_json(item) for key, item in value}
    if isinstance(value, FrozenJsonArray):
        return [_thaw_json(item) for item in value]
    if isinstance(value, tuple):
        if all(isinstance(item, tuple) and len(item) == 2 and isinstance(item[0], str) for item in value):
            return {key: _thaw_json(item) for key, item in value}
        return [_thaw_json(item) for item in value]
    return value


def thaw_provider_shape_payload(value: FrozenJson) -> dict[str, Any]:
    thawed = _thaw_json(value)
    if not isinstance(thawed, dict):
        raise ValueError("shape_payload_object_required")
    return thawed


def _json_size(value: FrozenJson) -> int:
    return len(json.dumps(_thaw_json(value), ensure_ascii=True, separators=(",", ":")).encode())


def _is_frozen_object(value: FrozenJson) -> bool:
    return (
        not isinstance(value, FrozenJsonArray)
        and isinstance(value, tuple)
        and all(isinstance(item, tuple) and len(item) == 2 and isinstance(item[0], str) for item in value)
    )


def _validate_frozen_json(value: FrozenJson, *, depth: int = 0) -> None:
    if depth > MAX_PAYLOAD_DEPTH:
        raise ValueError("shape_payload_depth_invalid")
    if value is None or isinstance(value, (bool, int, float, str)):
        return
    if isinstance(value, FrozenJsonArray):
        for item in value:
            _validate_frozen_json(item, depth=depth + 1)
        return
    if isinstance(value, FrozenJsonObject):
        keys = tuple(item[0] for item in value)
        if len(set(keys)) != len(keys):
            raise ValueError("shape_payload_key_duplicate")
        for _key, item in value:
            _validate_frozen_json(item, depth=depth + 1)
        return
    if not isinstance(value, tuple):
        raise ValueError("shape_payload_not_frozen")
    is_object = all(isinstance(item, tuple) and len(item) == 2 and isinstance(item[0], str) for item in value)
    if is_object:
        keys = tuple(item[0] for item in value)
        if len(set(keys)) != len(keys):
            raise ValueError("shape_payload_key_duplicate")
        for _key, item in value:
            _validate_frozen_json(item, depth=depth + 1)
        return
    for item in value:
        _validate_frozen_json(item, depth=depth + 1)


__all__ = [
    "DiscoveryDisposition",
    "DiscoveryDispositionKind",
    "LIVE_DISCOVERY_DISPOSITIONS",
    "ProviderShapeCase",
    "ProviderShapeExpectedKind",
    "ProviderShapeSensitivity",
    "RELEASE_DISCOVERY_DISPOSITIONS_01_14",
    "RELEASE_DISCOVERY_DISPOSITIONS_15_25",
    "load_provider_shape_cases",
    "load_provider_shape_archive",
    "thaw_provider_shape_payload",
    "validate_discovery_dispositions",
    "validate_provider_shape_catalog",
]
