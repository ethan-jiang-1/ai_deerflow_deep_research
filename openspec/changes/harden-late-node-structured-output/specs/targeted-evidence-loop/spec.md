> req: TEL-001, TEL-002

## MODIFIED Requirements

### Requirement: Gap router converts synthesis gaps to targeted WorkSpecs
The gap router SHALL read the bounded gate-owned `unresolved_gaps` id projection derived from validated canonical synthesis gaps and SHALL produce one WorkIntent per gap id with scoped search dimensions. It SHALL NOT infer routing authority from a description, a finding flag, a caller-supplied gap body, or any checkpoint field not written by the current Wave2 gate. An empty projection SHALL pass through without error.

#### Scenario: Gaps become work intents
- **WHEN** the current Wave2 gate projects ids for validated canonical `search_required=true` gaps
- **THEN** one WorkIntent per gap is materialized

#### Scenario: Empty gaps pass through
- **WHEN** the current Wave2 gate has no searchable gap ids
- **THEN** the router returns empty intents and the node passes through

#### Scenario: Descriptive text cannot schedule work
- **WHEN** gap prose asks for more research but the current Wave2 gate does not project its id
- **THEN** the router does not materialize a WorkIntent

### Requirement: Targeted worker performs focused gap search
A bounded web worker SHALL search for evidence addressing one assigned gap. The initial request SHALL require and permit exactly one web search tool call, use its multiple returned candidates as the evidence set, and retain later model turns for its structured answer. Output SHALL include new source refs and a gap resolution status, and the worker SHALL NOT modify synthesis findings directly. If the first successful agent result cannot be parsed, validated as the targeted worker schema, or bound to the assigned gap id, the node SHALL make exactly one separate repair request with tools disabled, the assigned gap identity and stable validation failure metadata, and the bounded untrusted draft. A valid repair SHALL proceed through the existing materializer, validator, and ledger submit boundary. A failed, non-successful, wrong-gap, or schema-invalid repair SHALL fail closed without result/source artifact or ledger authority.

#### Scenario: Worker finds evidence for a gap
- **WHEN** worker searches for evidence addressing a gap and returns valid structured output
- **THEN** new sources are recorded with backing refs and gap status is updated without a repair call

#### Scenario: Prose answer is repaired once without tools
- **WHEN** the initial worker uses one or two allowed tool calls but its successful final answer is prose, schema-invalid, or names a different gap
- **THEN** one zero-tool repair request may convert the bounded draft into a valid response for the same assigned gap

#### Scenario: Invalid repair publishes no authority
- **WHEN** the single repair is non-successful, malformed, schema-invalid, or names a different gap
- **THEN** the work attempt fails without publishing source artifacts, a targeted result artifact, or a submission-ledger record

#### Scenario: Repair cannot perform more research
- **WHEN** the repair request executes
- **THEN** no web or filesystem tool is exposed and no tool call is dispatched
