> req: REG-001, REG-002, REG-005

## MODIFIED Requirements

### Requirement: One explicit topology and implementation map own every phase

The downstream package SHALL declare one normalized top-level Deep Research topology
containing `bootstrap`, `hitl1`, `topic_planning`, `wave0`, `wave1`,
`wave2_synthesis`, `targeted_evidence`, `hitl2`, `rerun`, `readiness`, and
`final_delivery`. The builder SHALL load only explicitly listed package-root
`NODE_SPEC` values and SHALL resolve every logical node through one implementation map.
Fake selection SHALL bind the permanent deterministic fake; real selection without an
explicitly available implementation SHALL fail closed before graph invocation and
SHALL NOT silently fall back to fake. Change-01 packages SHALL use one canonical pure
unavailable-real sentinel rather than divergent placeholder behavior.

Real HITL1 SHALL add exactly two HITL1 route labels to the normalized topology:
`needs_followup -> hitl1` and `exhausted -> blocked/END`. Existing HITL1 labels
`accepted -> topic_planning` and `cancel -> cancelled/END` SHALL remain unchanged.
The self-edge is the durable same-phase follow-up path for incomplete profile answers;
the exhausted edge is the typed blocked path for pre-interrupt brief-generation failure.
No new top-level phase is introduced, and no later fake phase is allowed to observe a
partially completed HITL1 profile as if it were accepted.

Real topic planning SHALL add exactly one topic-planning route label to the normalized
topology: `exhausted -> blocked/END`. The existing `topic_planning --next--> wave0`
label and the inbound `bootstrap/hitl1 -> topic_planning` and `rerun -> topic_planning`
edges SHALL remain unchanged. The exhausted edge is the typed blocked path for a
planner that fails validation or coverage after its bounded repair. topic_planning
remains a non-gated controller node that writes its own route labels and does not
import LangGraph. Real topic planning SHALL chain off the real profile: selecting
`topic_planning=real` without `hitl1=real` (which itself requires `bootstrap=real`)
SHALL fail closed before graph invocation, because the planner consumes the real
HITL1 profile constraints.

#### Scenario: Full-fake topology resolves explicitly
- **WHEN** the builder receives the default implementation map
- **THEN** all eleven stable logical nodes resolve from their public package-root `NODE_SPEC`, every top-level node is reachable from START and can reach a terminal path, and no filesystem discovery occurs

#### Scenario: Unavailable real selection fails closed
- **WHEN** an implementation map selects real for a node whose real implementation is not supplied by its owning later change
- **THEN** graph binding fails with the logical node name and `implementation_unavailable` before a checkpoint, model, sandbox tool, or node is invoked

#### Scenario: Real HITL1 follow-up and blocked routes are explicit
- **WHEN** the mixed graph selects real HITL1
- **THEN** the builder contains conditional edges for `hitl1 --needs_followup--> hitl1` and `hitl1 --exhausted--> END`, and topology validation recognizes the exhausted route as terminal `blocked`

#### Scenario: Internal component cannot become a phase accidentally
- **WHEN** a Wave dispatch/join component, HITL1 follow-up helper, or an unlisted node package is present on disk
- **THEN** the normalized top-level topology and registry omit it and the topology contract rejects any edge that exposes it as a logical phase

#### Scenario: Real topic planning blocked route is explicit
- **WHEN** the mixed graph selects real topic planning
- **THEN** the builder carries a conditional edge `topic_planning -> {next: wave0, exhausted: END}`, the `next` and inbound edges are unchanged, and topology validation recognizes the topic-planning `exhausted` route as terminal `blocked`

#### Scenario: Real topic planning without the real profile chain fails closed
- **WHEN** a recipe selects `topic_planning=real` without `hitl1=real`
- **THEN** recipe construction fails with a typed dependency error before the graph is compiled or invoked

### Requirement: Checkpoints and topology contracts remain durable and deterministic

The fake graph SHALL use a versioned research checkpoint namespace isolated from the
outer lead-agent and infra-probe namespaces. ResearchState SHALL contain only bounded
control fields, artifact refs, branch summaries, HITL correlation, consumed-response
ids, bounded profile progress, bounded topic planning data, and a bounded logical
trace, per REG-006 through REG-008; it SHALL NOT contain raw runtime authority or
large research content. File-backed SQLite SHALL recover a suspended HITL across
provider close and a fresh process. Memory and SQLite memory mode SHALL be labelled
same-process only. A committed normalized topology snapshot SHALL reject unexpected
node/edge or reachability changes. Zero-API E2E coverage SHALL include happy
completion, repair, rerun, stop, cancel, stale-response denial, consumed-response
delivery reprojection, restart resume, the real-HITL1 follow-up restart path, and the
real-topic-planning blocked path.

#### Scenario: SQLite restart resumes the same interrupt
- **WHEN** one process starts a lifecycle to HITL, closes the provider, and a fresh process resumes the same trusted user/thread/research id with a matching HumanMessage
- **THEN** the prior pending interrupt and state are recovered, resume continues from that point, and no outer lead-agent or infra-probe checkpoint is read

#### Scenario: Committed suspension survives result-delivery failure
- **WHEN** the nested HITL checkpoint commits and the action fails before the outer ToolMessage is delivered
- **THEN** retrying start from the same trusted scope and start HumanMessage reopens the same namespace and reprojects the same pending request without rerunning completed nodes

#### Scenario: Unknown skeleton schema fails closed
- **WHEN** status, resume, or cancel reads a research checkpoint whose stored `ResearchState.schema_version` is unsupported
- **THEN** it returns `schema_unsupported` before node execution or checkpoint mutation

#### Scenario: Topology drift is detected
- **WHEN** a logical node, edge, route label, or reachability property changes beyond the declared HITL1 `needs_followup`/`exhausted` and topic_planning `exhausted` routes without regenerating the approved semantic snapshot
- **THEN** the topology contract fails with the normalized difference

#### Scenario: Memory does not claim restart durability
- **WHEN** the same-process memory host revisits a lifecycle and a fresh-process capability is inspected
- **THEN** same-process actions work on the retained host but status reports restart recovery unsupported and no restart E2E claim is made

#### Scenario: Real HITL1 follow-up survives restart
- **WHEN** real HITL1 commits partial profile progress, routes `needs_followup`, and suspends with a follow-up interrupt before the provider is closed
- **THEN** a fresh process resumes the follow-up using the checkpointed profile progress and the new pending request, without relying on Python closure state

#### Scenario: Real topic planning blocked terminal is durable
- **WHEN** real topic planning fails validation or coverage after its bounded repair and routes `exhausted` with terminal `BLOCKED`
- **THEN** the checkpoint records `terminal_status=BLOCKED` and `terminal_reason=GATE_BLOCKED`, no planner-owned topic state is written, status/cancel return the terminal result idempotently, and resume returns `invalid_transition` because no interrupt is pending
