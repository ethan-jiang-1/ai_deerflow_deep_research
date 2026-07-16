> req: EVH-001, EVH-002, EVH-003, EVH-004, EVH-005

## ADDED Requirements

### Requirement: Eval corpus framework supports replay-based testing

The eval framework SHALL use FakeToolCallingModel/ReplayChatModel for deterministic evaluation. Cases SHALL cover quick factual, claim verification, and insufficient evidence scenarios. All eval tests SHALL be zero-API.

#### Scenario: Citation precision computed for valid refs
- **WHEN** accepted_submission_refs are all valid
- **THEN** citation_precision is 1.0

#### Scenario: Citation precision detects bad refs
- **WHEN** some refs have invalid format
- **THEN** citation_precision is less than 1.0

### Requirement: Quality metrics are pure functions

Quality metrics SHALL be pure Python functions with no model calls or I/O. They SHALL compute citation precision, must-answer coverage, and source diversity from checkpoint state.

### Requirement: Fault injection covers critical graph points

Fault injection tests SHALL cover cancel, duplicate resume, crash recovery, and timeout at key graph points. Each fault SHALL have an expected outcome.

#### Scenario: Cancel produces typed InternalCancelDecision
- **WHEN** a cancel decision is serialized and deserialized
- **THEN** the decision roundtrips correctly

### Requirement: Adversarial source tests verify isolation

Adversarial tests SHALL verify prompt-injected content cannot override routing, forge submissions, or influence gate verdicts.

#### Scenario: Route override via content is impossible
- **WHEN** external content contains route-like strings
- **THEN** the graph route is unaffected

### Requirement: Release gate combines deterministic CI with optional LLM canary

Hard CI gate SHALL run all deterministic tests. Real-LLM tests SHALL be marked @requires_llm and be optional.
