> req: WAN-001, WAN-002, WAN-003, WAN-004, WAN-005

## ADDED Requirements

### Requirement: Real Wave0 materializes per-topic source-intake work from the planner registry

The real Wave0 controller SHALL read the planner-owned `topic_registry`/
`topic_refs` from `ResearchState` and materialize exactly one immutable
source-intake `WorkSpec` per topic through the existing work-unit controller
(`materialize_work_spec`), with `scope` binding the topic id and its must-answer
questions. The real node SHALL drive the shared work-unit fan-out/fan-in component
with those real intents and a real worker, and SHALL return the same
`node_update` + parent work-block update + `WorkUnitGateView` shape the wrapper
already consumes. No second controller, work authority, or phase cursor is
introduced.

#### Scenario: One work spec per accepted topic
- **WHEN** real Wave0 runs after real topic planning recorded a bounded topic registry
- **THEN** the controller allocates one immutable `WorkSpec` per topic with controller-assigned identity and a derived `spec_hash`, and the shared component fans out one worker per topic

#### Scenario: Real Wave0 reuses the shared work-unit component
- **WHEN** the real Wave0 node is built
- **THEN** it drives the shared allocate/dispatch/submit/refill/drain component with real per-topic intents and a real worker, and returns the parent work-block update plus the validated `WorkUnitGateView` without duplicating submit, ledger, retry, or drain authority

#### Scenario: Empty topic registry fails closed
- **WHEN** real Wave0 runs but the planner recorded no topics
- **THEN** the controller fails closed before allocating work rather than inventing fixture topics

### Requirement: A bounded web worker performs source intake under an untrusted-data discipline

For each in-flight `WorkSpec`, Wave0 SHALL run one bounded worker agent through
`capabilities.run_agent()` on the runtime node-agent bridge under a real
`ExecutionPolicy` with a non-empty `allowed_tool_names` set of web search/fetch
tools, per-tool `ToolPolicySpec` entries, and attempt-scoped read/write roots.
All fetched page, PDF, snippet, and cache content SHALL be treated as untrusted
data: it SHALL be placed in the `<untrusted-source-data>` block or referenced as a
sandbox artifact, never spliced into the trusted system prompt, and the
deny-by-default tool policy SHALL block any tool or path the worker is not
allow-listed for. The worker SHALL write only to its own
`work/<work_id>/<attempt_id>/` root and declared cache regions, and SHALL NOT
write phase, gate, ledger, or another attempt's state.

#### Scenario: Fetched content is untrusted data
- **WHEN** a worker fetches a page or snippet
- **THEN** the content is wrapped as untrusted source data or referenced as a sandbox artifact, never placed in the system prompt, and the worker cannot be directed by it to change tools, paths, phase, gate, or ledger state

#### Scenario: Adversarial source cannot escalate
- **WHEN** a fetched source contains directives to ignore rules, call a forbidden tool, or mark itself authoritative
- **THEN** the worker produces only a source limitation or rejection, the deny-by-default tool policy blocks any forbidden call, and no control authority is mutated

#### Scenario: Worker writes only its own attempt root
- **WHEN** a worker attempts to write outside its `attempt_root` or another attempt's directory
- **THEN** the artifact writer and path-containment contract reject the write and the candidate fails validation

### Requirement: A real source-intake result contract and deterministic submit validation

Change 08 SHALL register a real `wave0.source-intake` v1 result contract (frozen
model carrying canonical source URLs, source metadata, baseline facts, fetch/cache
refs, and limitations) in the generalized `(result_contract,
result_schema_version)` validation registry, alongside the existing fixture
contract. Submit validation SHALL canonicalize each source URL via
`canonicalize_source_url`, verify that cited fetch/cache content is real and
contained, check path, hash, and source identity, reject snippet-as-cache,
cross-attempt, and out-of-containment writes, and accept the candidate only as a
typed `SubmissionRecord`. Only accepted `SubmissionRecord`s SHALL count as
coverage; worker final text SHALL NOT.

#### Scenario: Valid sources become accepted evidence
- **WHEN** a worker submits a `wave0.source-intake` result with canonical, independently-fetchable sources under its attempt root
- **THEN** submit validation accepts it as a hash-chained `SubmissionRecord` and the accepted ref enters the evidence ledger

#### Scenario: Non-canonical or fabricated sources are rejected
- **WHEN** a candidate carries a non-canonical URL, a snippet presented as cached content, a path outside the attempt root, or a hash that does not match the fetched bytes
- **THEN** submit validation fails closed with a typed code and no `SubmissionRecord` is appended

#### Scenario: Duplicate URLs are deduplicated per topic
- **WHEN** two sources canonicalize to the same URL within one topic
- **THEN** submit validation counts them as one source, protecting the independent-source floor

### Requirement: A real source-floor gate with honest degraded capture

The real Wave0 gate SHALL drop the `FixtureSequenceRule`, keep the shared
`WorkUnitCompletionRule` (drain plus accepted-record coverage), and enforce a
per-topic source floor of at least N independent, deduplicated sources. Because
gate rules are pure and the `WorkUnitGateView` carries accepted-record hashes
rather than source counts, the source floor, independent-source, and dedup checks
SHALL be enforced at submit-validation time, and the gate SHALL verify that every
planned topic has an accepted record and the work is drained. When a source is
unreachable, the worker SHALL record a typed degraded capture (attempted URL,
limitation, reason) rather than fabricating success; a degraded `PASS` SHALL be
permitted only when the independent-source floor is otherwise met. The route map
SHALL remain `{PASS: pass, REPAIR: repair, BLOCKED: exhausted}`.

#### Scenario: Source floor gates coverage
- **WHEN** a topic's accepted submissions do not meet the independent-source floor
- **THEN** the gate routes `repair` (within budget) or `exhausted` and the lifecycle does not advance to Wave1

#### Scenario: Unreachable source is captured honestly
- **WHEN** a worker cannot fetch a source
- **THEN** it records a typed degraded capture, never marks an unfetched source authoritative, and the gate may pass degraded only if the floor is otherwise met

#### Scenario: Bounded repair refetches missing topics only
- **WHEN** the gate routes `repair`
- **THEN** only topics lacking accepted coverage are retried, no submission ledger entry is hand-written, and repeated failure exhausts to terminal `blocked`

### Requirement: Real Wave0 integrates into the mixed graph off the real topic chain

Real Wave0 SHALL be selectable only in the mixed implementation map and SHALL
require `bootstrap=real`, `hitl1=real`, and `topic_planning=real`, because the
worker consumes the real topic registry. Selecting `wave0=real` without the real
topic chain SHALL fail closed before graph invocation. The Wave0 topology SHALL be
unchanged (`repair`/`pass`/`exhausted`); the real gate writes the route via the
gate kernel. The full-fake Wave0 fixture path SHALL remain deterministic and
SHALL NOT construct the node-agent bridge. The lifecycle result SHALL remain
`implementation_mode=full_fake` because Wave1, synthesis, HITL2, and final
delivery remain fake.

#### Scenario: Real Wave0 requires the real topic chain
- **WHEN** a recipe selects `wave0=real` without `topic_planning=real`
- **THEN** recipe construction fails with a typed dependency error before the graph is compiled or invoked

#### Scenario: Topology is unchanged for real Wave0
- **WHEN** the mixed graph selects real Wave0
- **THEN** Wave0 keeps its `repair`/`pass`/`exhausted` routes, the gate writes the route via the gate kernel, and no top-level edge changes

#### Scenario: Full-fake Wave0 remains the deterministic fixture path
- **WHEN** the full-fake graph reaches Wave0
- **THEN** it runs the fixture work-unit path without constructing the node-agent bridge and the topology snapshot is unchanged
