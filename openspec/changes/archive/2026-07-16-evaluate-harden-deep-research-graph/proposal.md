## Why

The Deep Research graph is fully implemented (changes 00–17). The remaining gap is proving it works — not just that it runs, but that it produces correct, safe, and recoverable output. Change 18 builds the evaluation infrastructure: a replay-based eval corpus, automated quality metrics, and fault injection tests. This is the release gate for the first complete version.

## What Changes

- **Eval corpus framework**: Replay-based test harness using `FakeToolCallingModel`/`ReplayChatModel` for deterministic evaluation. Covers quick factual, claim verification, and insufficient evidence scenarios.
- **Quality metrics**: Deterministic functions to compute citation precision, must-answer coverage, and source diversity from accepted submissions and checkpoint state. Zero API.
- **Fault injection tests**: Crash/timeout/cancel/duplicate-resume at key graph points (HITL, fan-out, gate, final publish). Verify recovery or clean terminal outcome.
- **Adversarial source test**: Verify prompt-injected web content cannot gain control, forge submissions, or influence routing.
- **Release gate**: Hard CI checks (deterministic tests must pass) + optional real-LLM canary flags.

## Capabilities

- `evaluation-hardening`: Eval corpus, quality metrics, fault injection, adversarial tests, release gate. Requirement IDs: EVH-001 through EVH-005.

## Impact

- **Source**: new `agent/tests/eval/` directory (eval corpus + metrics + fault injection).
- **Typed state**: none.
- **Graph**: no topology or node changes.
- **Non-goals**: no new workflow phases. No `backend`/`frontend` changes.
