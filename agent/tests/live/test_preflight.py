"""Credentialed lane preflight probes.

These tests intentionally fail when explicitly selected without their required
environment. They are excluded from every deterministic command.

@impl EVH-005
@impl EVH-009
"""

from __future__ import annotations

import os

import pytest

from tests.scenarios.live import preflight_live_environment

pytestmark = pytest.mark.requires_llm


def test_live_model_preflight() -> None:
    environment = preflight_live_environment(environ=os.environ, require_web=False)
    assert environment.model_provider


def test_live_web_preflight() -> None:
    environment = preflight_live_environment(environ=os.environ, require_web=True)
    assert environment.web_provider == "tavily"
