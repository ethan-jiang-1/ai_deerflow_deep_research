"""Full-real release acceptance control-plane contracts.

@impl EVH-004
@impl EVH-005
@impl EVH-009
"""

from __future__ import annotations

import os
import subprocess
import sys

import pytest

from tests.scenarios.release import (
    RELEASE_SCENARIO,
    ReleaseAcceptanceFailure,
    ReleaseAttempt,
    ReleaseOutcome,
    ReleasePreflightError,
    ReleaseRunner,
    new_release_invocation,
    preflight_release_environment,
)


def test_release_preflight_requires_explicit_confirmation() -> None:
    with pytest.raises(ReleasePreflightError, match="release_confirmation_missing") as caught:
        preflight_release_environment(environ={})

    assert caught.value.code == "release_confirmation_missing"


def test_release_preflight_requires_model_and_web_configuration() -> None:
    with pytest.raises(ReleasePreflightError, match="live_model_credentials_missing"):
        preflight_release_environment(environ={"RELEASE_E2E_CONFIRM": "1"})

    environment = preflight_release_environment(
        environ={
            "RELEASE_E2E_CONFIRM": "1",
            "OPENAI_API_KEY": "model-secret",
            "TAVILY_API_KEY": "web-secret",
        }
    )
    assert environment.model_provider == "openai"
    assert environment.web_provider == "tavily"


def test_release_preflight_cli_fails_without_confirmation_or_credentials() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/release_preflight.py"],
        capture_output=True,
        check=False,
        env={"PATH": os.environ.get("PATH", ""), "RELEASE_DISABLE_DOTENV": "1"},
        text=True,
    )

    assert result.returncode == 1
    assert "release_confirmation_missing" in result.stderr


def test_release_invocations_never_reuse_thread_run_research_or_checkpoint_identity() -> None:
    first = new_release_invocation()
    second = new_release_invocation()

    assert first.thread_id != second.thread_id
    assert first.run_id != second.run_id
    assert first.research_id != second.research_id
    assert first.checkpoint_key != second.checkpoint_key


def test_release_scenario_requires_normal_path_without_conditional_rerun_branches() -> None:
    assert RELEASE_SCENARIO.expected_trace == (
        "bootstrap",
        "hitl1",
        "topic_planning",
        "wave0",
        "wave1",
        "wave2_synthesis",
        "hitl2",
        "readiness",
        "final_delivery",
    )


async def test_release_runner_reports_bounded_visible_retry_and_required_terminal_artifacts() -> None:
    invocation = new_release_invocation()
    attempts = iter(
        (
            ReleaseAttempt(outcome=None, error_code="provider_timeout", wall_time_seconds=1.0),
            ReleaseAttempt(
                outcome=ReleaseOutcome(
                    invocation=invocation,
                    terminal_status="completed",
                    lifecycle_trace=RELEASE_SCENARIO.expected_trace,
                    accepted_submission_refs=("ref:accepted",),
                    artifacts=("final/report.md", "final/claim-citation-map.json"),
                    citation_bindings={"claim-1": ("ref:accepted",)},
                    contained=True,
                    cleaned_up=True,
                ),
                error_code=None,
                wall_time_seconds=2.0,
                response_shapes=(
                    {
                        "content_chars": 42,
                        "content_kind": "json_object",
                        "json_keys": ["summary"],
                        "tool_names": [],
                    },
                ),
            ),
        )
    )

    async def execute(_scenario, selected_invocation):
        assert selected_invocation == invocation
        return next(attempts)

    report = await ReleaseRunner(executor=execute, max_attempts=2).run(RELEASE_SCENARIO, invocation)

    assert report.attempt_count == 2
    assert report.retry_count == 1
    assert [attempt.error_code for attempt in report.attempts] == ["provider_timeout", None]
    assert report.attempts[1].response_shapes[0]["content_kind"] == "json_object"
    assert report.hard_invariants == {
        "terminal_completed": True,
        "lifecycle_trace_complete": True,
        "accepted_evidence_present": True,
        "report_artifacts_present": True,
        "citation_bindings_valid": True,
        "paths_contained": True,
        "cleanup_complete": True,
        "checkpoint_isolated": True,
    }


async def test_release_runner_rejects_missing_artifacts_with_stable_identity() -> None:
    invocation = new_release_invocation()

    async def execute(_scenario, _invocation):
        return ReleaseAttempt(
            outcome=ReleaseOutcome(
                invocation=invocation,
                terminal_status="completed",
                lifecycle_trace=RELEASE_SCENARIO.expected_trace,
                accepted_submission_refs=("ref:accepted",),
                artifacts=("final/report.md",),
                citation_bindings={"claim-1": ("ref:accepted",)},
                contained=True,
                cleaned_up=True,
            ),
            error_code=None,
            wall_time_seconds=1.0,
        )

    with pytest.raises(
        ReleaseAcceptanceFailure,
        match=f"scenario={RELEASE_SCENARIO.scenario_id} lane=release authenticity=full_real_pipeline",
    ) as caught:
        await ReleaseRunner(executor=execute, max_attempts=1).run(RELEASE_SCENARIO, invocation)

    assert caught.value.report.hard_invariants["report_artifacts_present"] is False
