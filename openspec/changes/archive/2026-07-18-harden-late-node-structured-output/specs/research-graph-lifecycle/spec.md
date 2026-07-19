> req: REG-001

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

Real Wave2 synthesis SHALL add exactly one Wave2 route label to the normalized
topology: `exhausted -> blocked/END`. Existing labels
`evidence_needed -> targeted_evidence` and `pass -> hitl2`, plus the
`targeted_evidence -> wave2_synthesis` return edge, SHALL remain unchanged. The
exhausted edge is the typed blocked path when searchable gaps remain after the
existing Wave2 gate repair budget or fatigue contract is exhausted; no new top-level
phase or alternate bypass around synthesis is introduced.

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

#### Scenario: Real Wave2 blocked route is explicit
- **WHEN** the real Wave2 gate exhausts its bounded repair or fatigue contract while searchable gaps remain
- **THEN** the builder routes `wave2_synthesis --exhausted--> END`, normalized topology classifies the endpoint as `blocked`, and no targeted or HITL2 bypass occurs

