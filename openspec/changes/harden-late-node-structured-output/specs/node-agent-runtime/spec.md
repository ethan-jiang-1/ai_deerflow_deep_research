> req: NOA-002, NOA-003

## MODIFIED Requirements

### Requirement: Phase-agent execution has explicit budgets

Every request-level tool-call limit SHALL be enforced cumulatively before tool
dispatch, including a model response that proposes parallel calls. If prior calls plus
the current response exceed the remaining request quota, middleware SHALL deny the
batch with a typed non-success result; the declared request limit SHALL never be
exceeded in observed dispatch accounting.

#### Scenario: Parallel response cannot cross request quota
- **WHEN** one tool call has already run under a two-call request limit and the next model response proposes two parallel calls
- **THEN** middleware rejects the response before either new call dispatches and observed request tool calls remain one
