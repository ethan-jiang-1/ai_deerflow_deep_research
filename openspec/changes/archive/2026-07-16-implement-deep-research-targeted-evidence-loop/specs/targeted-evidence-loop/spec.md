> req: TEL-001, TEL-002, TEL-003, TEL-004

## ADDED Requirements

### Requirement: Gap router converts synthesis gaps to targeted WorkSpecs
The gap router SHALL read synthesis gaps, filter for search_required=true, and SHALL produce one WorkIntent per gap with scoped search dimensions. Empty gaps SHALL pass through without error.

#### Scenario: Gaps become work intents
- **WHEN** synthesis output contains search_required gaps
- **THEN** one WorkIntent per gap is materialized

#### Scenario: Empty gaps pass through
- **WHEN** synthesis has no search_required gaps
- **THEN** the router returns empty intents and the node passes through

### Requirement: Targeted worker performs focused gap search
A bounded web worker SHALL search for evidence addressing one gap. Output SHALL include new source refs and a gap resolution status. The worker SHALL NOT modify synthesis findings directly.

#### Scenario: Worker finds evidence for a gap
- **WHEN** worker searches for evidence addressing a gap
- **THEN** new sources are recorded with backing refs and gap status is updated

### Requirement: Convergence gate enforces round budget and fatigue
The convergence gate SHALL track round count per phase and SHALL enforce a maximum round budget. Repeated failures on the same gap SHALL trigger fatigue detection. Exhausted budget SHALL route exhausted.

#### Scenario: Round budget exhausted
- **WHEN** max rounds reached without resolving all gaps
- **THEN** gate routes exhausted with remaining gaps deferred

#### Scenario: Fatigue detected on repeated failure
- **WHEN** the same gap fails resolution across multiple rounds
- **THEN** the gap is marked deferred and does not consume further budget

### Requirement: Mixed-graph integration requires full real chain
Real targeted evidence loop SHALL require full real chain through wave2_synthesis. Full-fake targeted_evidence SHALL remain deterministic. Topology SHALL be unchanged.

#### Scenario: Full real chain compiles
- **WHEN** recipe selects targeted_evidence=real with full chain through wave2_synthesis
- **THEN** graph compiles and preserves topology shape
