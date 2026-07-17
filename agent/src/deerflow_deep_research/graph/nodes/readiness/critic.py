"""Readiness critic — deterministic fallback; real agent loop deferred.

@impl REA-002
@impl REA-006
"""

from __future__ import annotations

from .contracts import PerQuestionVerdict, ReadinessCriticOutput


def run_readiness_critic(
    must_answer_questions: tuple[str, ...],
    _accepted_submission_refs: tuple[str, ...],
) -> ReadinessCriticOutput:
    """Deterministic fallback: mark all questions as ready_substantive.

    The real bounded agent loop (via bridge, following change 09 pattern)
    replaces this fallback. The contract and structured output schema are
    defined in contracts.py and remain unchanged when the agent is added.
    """
    per_q = (
        tuple(
            PerQuestionVerdict(
                question=q,
                verdict="ready_substantive",
                limitation_note="Assessed by deterministic fallback; full critic pending.",
            )
            for q in must_answer_questions
        )
        if must_answer_questions
        else ()
    )

    return ReadinessCriticOutput(
        schema_version=1,
        per_question=per_q,
    )


__all__ = ["run_readiness_critic"]
