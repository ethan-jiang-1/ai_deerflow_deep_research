> req: WSN-001, WSN-002, WSN-003, WSN-004

## ADDED Requirements

### Requirement: Read-only synthesis agent produces structured findings
The synthesis agent SHALL read accepted evidence and critic verdicts and produce structured findings with priority, affected topics, backing refs, confidence, and search_required flag. The agent SHALL run under zero-tool read-only policy.

#### Scenario: Agent produces findings from accepted evidence
- **WHEN** wave2_synthesis runs after wave1 produced accepted submissions
- **THEN** structured findings are produced with backing refs to accepted sources

#### Scenario: Agent cannot call web tools
- **WHEN** the synthesis agent attempts to call a web search tool
- **THEN** the tool policy middleware blocks the call

### Requirement: Deterministic materializer writes synthesis artifacts
A deterministic materializer SHALL write findings to the sandbox as canonical JSON at `synthesis/findings.json`. A cross-topic ledger tracking relationships SHALL be written alongside.

#### Scenario: Valid findings written deterministically
- **WHEN** synthesis produces valid structured output
- **THEN** canonical JSON is written to `synthesis/findings.json`

### Requirement: Gate validates finding references
The real Wave2 gate SHALL validate that every finding reference is backed by an accepted submission. Dangling or unbacked references SHALL fail. The route map SHALL remain pass/repair/exhausted.

#### Scenario: Dangling reference fails gate
- **WHEN** a finding references a source not in accepted submissions
- **THEN** the gate routes repair

### Requirement: Mixed-graph integration
Real wave2_synthesis SHALL require full real chain through wave1. Full-fake path unchanged.

#### Scenario: Full real chain compiles
- **WHEN** recipe selects wave2_synthesis=real with full chain
- **THEN** graph compiles and preserves topology shape
