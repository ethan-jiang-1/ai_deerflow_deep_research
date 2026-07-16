# evidence-critic-nodes Specification

> req: EVC-001, EVC-002, EVC-003, EVC-004, EVC-005

## Purpose

SourceDiagnostic and ClaimVerifier critic agent nodes — versioned structured output,
read-only evidence access, deterministic materialization, and author-critic isolation
for the Deep Research semantic quality layer.

## Requirements

### Requirement: SourceDiagnostic agent produces a typed trust and materiality assessment

The SourceDiagnostic critic SHALL accept a set of accepted `SourceRef`s (with
sandbox content read by the critic via its `read_roots`) and SHALL produce a
versioned `SourceDiagnosticResult` carrying per-source assessments: a `trust_tier`
(enumerated: `high`/`medium`/`low`/`untrusted`), a `materiality`
(enumerated: `primary`/`secondary`/`peripheral`), a `marketing_risk`
flag, and a `cross_verification_need` flag. The critic SHALL only reference source ids present
in the assigned evidence set; references to unassigned or fabricated sources SHALL
fail validation.

#### Scenario: Valid source assessment is produced
- **WHEN** SourceDiagnostic runs with assigned accepted source refs and their content
- **THEN** a typed `SourceDiagnosticResult` is written with per-source trust tier, materiality, marketing risk, and cross-verification need, referencing only assigned source ids

#### Scenario: Fabricated source reference fails validation
- **WHEN** SourceDiagnostic output references a source id not in the assigned evidence set
- **THEN** the deterministic materializer rejects the output before writing any artifact

#### Scenario: Prompt-injected source yields honest assessment
- **WHEN** a source contains directives to claim high trust or suppress risk flags
- **THEN** the critic produces a limitation entry rather than elevating trust, and the deny-by-default tool policy blocks any attempted tool call

### Requirement: ClaimVerifier agent produces typed evidence-backed claim assessment

The ClaimVerifier critic SHALL accept a set of claims and their associated accepted
evidence refs, and SHALL produce a versioned `ClaimVerifierResult` carrying per-claim
verdicts: `supported`, `weakened`, `contradicted`, or `uncertain`, each with
`support_refs`, `counter_refs`, and a `reason` string. Every referenced source SHALL
be present in the assigned evidence set; dangling refs SHALL fail validation.

#### Scenario: Claim is verified against assigned evidence
- **WHEN** ClaimVerifier runs with a claim and assigned accepted source refs
- **THEN** a typed `ClaimVerifierResult` is written with one of the four verdicts, support refs, counter refs, and a reason, all referencing only assigned source ids

#### Scenario: Dangling reference to unassigned source fails validation
- **WHEN** ClaimVerifier output references a source id not in the assigned evidence set
- **THEN** the deterministic materializer rejects the output before writing any artifact

#### Scenario: Conflicting evidence produces uncertain verdict
- **WHEN** equal-quality sources support and contradict the same claim
- **THEN** the critic returns `uncertain` with both support refs and counter refs, rather than fabricating consensus

### Requirement: Critics run as bounded read-only agent loops with no tool escalation

Each critic agent SHALL run as a bounded `create_deerflow_agent()` loop through the
runtime node-agent bridge under a read-only `ExecutionPolicy` with
`allowed_tool_names` empty, `write_roots` empty, and `read_roots` covering the
research bundle root. The critic SHALL read only from its assigned evidence and
SHALL NOT write phase, gate, ledger, or another node's artifacts. The
deny-by-default `ToolPolicyMiddleware` SHALL block any tool call — the middleware
rejects the call at the framework level; the agent cannot invoke any tool.

#### Scenario: Critic cannot call tools
- **WHEN** a critic attempts to invoke a web search, file write, or ledger mutation tool
- **THEN** the tool policy middleware blocks the call and the agent receives a tool-rejection response

#### Scenario: Critic cannot write outside its sandbox path
- **WHEN** a critic attempts to write a file outside its assigned `critic/<node_attempt_id>/` path
- **THEN** the artifact writer rejects the write and the candidate fails validation

### Requirement: Critic output uses versioned structured schema with deterministic materialization

Every critic output SHALL conform to a versioned Pydantic model (`schema_version`
field, unknown fields rejected) and SHALL be written to the sandbox by a deterministic
materializer. The `SourceDiagnosticResult` SHALL be written to
`critic/<node_attempt_id>/source-diagnostic.json`; the `ClaimVerifierResult` SHALL be
written to `critic/<node_attempt_id>/claim-verifier.json`. Downstream consumers
SHALL branch on `schema_version` for forward compatibility.

#### Scenario: Valid SourceDiagnostic output is written deterministically
- **WHEN** a SourceDiagnostic agent produces valid structured output
- **THEN** the deterministic materializer writes canonical JSON with `schema_version: 1` to `critic/<node_attempt_id>/source-diagnostic.json`

#### Scenario: Valid ClaimVerifier output is written deterministically
- **WHEN** a ClaimVerifier agent produces valid structured output
- **THEN** the deterministic materializer writes canonical JSON with `schema_version: 1` to `critic/<node_attempt_id>/claim-verifier.json`

#### Scenario: Invalid schema is rejected
- **WHEN** a critic agent produces output missing required fields or containing unknown fields
- **THEN** the materializer rejects the output and no artifact is written

### Requirement: Author-critic isolation prevents self-assessment bias

The author of evidence (Wave0 worker) and each critic SHALL use independent model
configurations, prompt templates, and agent sessions. Tests SHALL verify critic
output against fixture evidence, not against the author's self-assessment.
Critic types are distinct roles (SourceDiagnostic vs ClaimVerifier) with different
input contracts and output schemas; each is invoked independently with its own
agent session. When a downstream gate later consumes results from both critic
types and they imply different conclusions, the gate SHALL record the disagreement
as a gap rather than auto-resolving by majority vote.

#### Scenario: Critic does not share author session
- **WHEN** a critic runs after Wave0 source intake
- **THEN** the critic agent is a separate `create_deerflow_agent()` invocation with its own model, prompt, and session, not a continuation of the worker agent

#### Scenario: Different critic types produce independent assessments
- **WHEN** SourceDiagnostic and ClaimVerifier run on the same evidence set
- **THEN** each critic runs in its own agent session with its own prompt and structured-output schema, and their results are written as separate artifacts
