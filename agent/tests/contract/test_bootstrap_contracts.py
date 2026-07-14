"""Red contract tests for the bootstrap node-local contracts.

@impl BON-002
@impl PRS-003
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from deerflow_deep_research.domain.lifecycle import BootstrapRoute
from deerflow_deep_research.graph.nodes.bootstrap.contracts import (
    CONTRACTS,
    BootstrapRequest,
    BootstrapResult,
)

_MARKER_REF = "workspace/deep-research/r_" + "a" * 43 + "/request/marker.json"


class TestBootstrapContracts:
    def test_contracts_export_is_the_pair(self) -> None:
        assert CONTRACTS == (BootstrapRequest, BootstrapResult)

    def test_request_text_is_required(self) -> None:
        with pytest.raises(ValidationError):
            BootstrapRequest()  # type: ignore[call-arg]
        assert BootstrapRequest(request_text="hello").request_text == "hello"

    def test_result_route_only(self) -> None:
        result = BootstrapResult(route=BootstrapRoute.NEEDS_INPUT)
        assert result.route is BootstrapRoute.NEEDS_INPUT
        assert result.marker_ref is None

    def test_result_accepts_optional_marker_ref(self) -> None:
        result = BootstrapResult(route=BootstrapRoute.NEEDS_INPUT, marker_ref=_MARKER_REF)
        assert result.marker_ref == _MARKER_REF

    def test_result_rejects_caller_supplied_authority_field(self) -> None:
        with pytest.raises(ValidationError):
            BootstrapResult(route=BootstrapRoute.NEEDS_INPUT, research_id="r_evil")  # type: ignore[call-arg]
