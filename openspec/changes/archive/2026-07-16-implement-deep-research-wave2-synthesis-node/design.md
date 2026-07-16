## Context

Changes 08-10 deliver accepted evidence with critic verdicts. Wave2 synthesis reads this accumulated knowledge and produces structured cross-topic findings. It is a single bounded agent — no work-unit controller, no fan-out.

## Goals

- Read-only agent producing structured findings from accepted evidence.
- Zero-tool policy (no web, no writes beyond synthesis artifacts).
- Deterministic materializer for findings and cross-topic ledger.
- Gate validates reference integrity and structural completeness.

## Decisions

### Decision 1: Single agent, no work units
Wave2 is a single bounded agent call, not a work-unit fan-out. It reads accumulated state and produces one set of findings.

### Decision 2: Structured output with gap detection
Output includes finding index, cross-topic relations, contradictions, and candidate gaps. Gaps are recorded with priority and affected topics.

### Decision 3: Read-only policy
`allowed_tool_names=frozenset()`, `write_roots=()`, `read_roots` covering bundle root.

### Decision 4: Real gate validates references
The real gate checks that every finding reference is backed by an accepted submission and critic verdict. Missing or dangling references fail.

## Risks

- Single model call may miss subtle cross-topic connections. Acceptable for v1; targeted-evidence loop (change 12) adds iterative refinement.
