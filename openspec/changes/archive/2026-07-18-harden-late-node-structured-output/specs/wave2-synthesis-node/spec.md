> req: WSN-001, WSN-002, WSN-003

## MODIFIED Requirements

### Requirement: Read-only synthesis agent produces structured findings
The synthesis agent SHALL read accepted evidence and critic verdicts and produce one or more structured findings with priority, affected topics, backing refs, confidence, and `search_required`, plus canonical gaps with priority, affected topics, and an explicit `search_required` value. Whenever accepted evidence is non-empty, a gaps-only result SHALL fail semantic validation and use the existing one-shot zero-tool repair; gaps SHALL NOT substitute for at least one backed finding. The agent SHALL run under zero-tool read-only policy. Prompt instructions and provider-shape normalization SHALL distinguish finding follow-up advice from gap routing authority and SHALL preserve the canonical gap value without inventing it from prose.

#### Scenario: Agent produces findings from accepted evidence
- **WHEN** wave2_synthesis runs after wave1 produced accepted submissions
- **THEN** structured findings are produced with backing refs to accepted sources

#### Scenario: Searchable gap retains routing authority
- **WHEN** valid structured synthesis output marks a canonical gap `search_required=true`
- **THEN** validation preserves that value in the `GapRecord` consumed by downstream projection and routing

#### Scenario: Legacy gap remains non-searchable by default
- **WHEN** a schema-version-1 synthesis artifact omits `search_required` from a gap
- **THEN** validation accepts the gap with `search_required=false` rather than silently scheduling targeted work

#### Scenario: Accepted evidence cannot produce gaps only
- **WHEN** accepted evidence exists and the initial synthesis response has zero findings plus one or more valid gaps
- **THEN** the node performs its existing one zero-tool repair and publishes no synthesis artifact or gate preview unless the repair contains at least one backed finding

#### Scenario: Agent cannot call web tools
- **WHEN** the synthesis agent attempts to call a web search tool
- **THEN** the tool policy middleware blocks the call

### Requirement: Deterministic materializer writes synthesis artifacts
A deterministic materializer SHALL write findings, relations, gaps, summary, and every canonical `search_required` value to the sandbox as canonical JSON at `synthesis/findings.json`. The persisted artifact SHALL be the synthesis content authority. The Wave2 node SHALL derive a typed gate preview containing only bounded searchable gap ids from that validated result; it SHALL NOT put complete gap bodies in checkpoint state or permit model output to write gate authority directly.

#### Scenario: Valid findings written deterministically
- **WHEN** synthesis produces valid structured output
- **THEN** canonical JSON is written to `synthesis/findings.json`

#### Scenario: Gap routing value survives persistence
- **WHEN** synthesis materializes a gap with `search_required=true`
- **THEN** reading the canonical artifact yields the same gap identity and routing value and the typed gate preview contains that gap id

### Requirement: Gate validates finding references
The real Wave2 gate SHALL validate that every finding reference is backed by an accepted submission. Dangling or unbacked references SHALL fail. It SHALL additionally consume the typed preview derived from validated synthesis output, write the bounded searchable gap ids to the existing gate-owned `unresolved_gaps` control field, and route `evidence_needed` when that projection is non-empty and repair budget remains. A later successful synthesis with no searchable gap SHALL clear the projection and route `pass`. Repeated unresolved semantic gaps SHALL use the existing gate budget/fatigue contract and route `exhausted` to the typed blocked terminal.

#### Scenario: Dangling reference fails gate
- **WHEN** a finding references a source not in accepted submissions
- **THEN** the gate routes repair

#### Scenario: Searchable gap routes targeted evidence
- **WHEN** validated Wave2 output produces a typed preview with one or more searchable gap ids
- **THEN** the real gate records only those ids in `unresolved_gaps` and routes `evidence_needed`

#### Scenario: No searchable gap clears prior projection
- **WHEN** a later validated Wave2 output contains no `search_required=true` gap
- **THEN** the real gate clears `unresolved_gaps` and routes `pass`

#### Scenario: Repeated searchable gap exhausts convergence budget
- **WHEN** targeted evidence returns through synthesis but the same searchable gap remains after the Wave2 repair budget is spent
- **THEN** the real gate routes `exhausted` and the graph reaches the typed blocked terminal

#### Scenario: Fabricated checkpoint gap cannot route
- **WHEN** checkpoint input contains an unvalidated gap body or id that is absent from the current typed Wave2 gate preview
- **THEN** the real gate ignores it as routing authority
