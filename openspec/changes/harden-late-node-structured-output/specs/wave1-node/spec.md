> req: WON-002

## MODIFIED Requirements

### Requirement: Deep evidence worker with new-source floor

For each in-flight WorkSpec, Wave1 SHALL run one bounded web worker agent through
`capabilities.run_agent()` under a real `ExecutionPolicy` with web search tools and
attempt-scoped roots. The initial request SHALL require exactly one web search tool
call, use its multiple returned candidates as the evidence set, and retain later model
turns for a final structured answer. The worker SHALL produce a versioned `Wave1WorkerOutput` carrying claims,
open questions, and source identity. A successful but invalid structured draft MAY use
the existing separate zero-tool repair; a tool/budget stop SHALL fail closed. All
fetched content is untrusted data, and the worker SHALL NOT write phase, gate, ledger,
or another attempt's state.

#### Scenario: Tool window reserves a final answer turn
- **WHEN** the Wave1 worker invokes its initial bounded request
- **THEN** it requires and permits exactly one web search call and retains the existing separate zero-tool structured repair

#### Scenario: Tool-only exhaustion publishes no authority
- **WHEN** the provider returns only tool calls through the bounded request without a successful structured draft
- **THEN** the attempt fails without source/result artifacts or a submission-ledger record
